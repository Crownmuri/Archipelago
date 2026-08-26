from __future__ import annotations

from http.client import CONFLICT
import random
from typing import Dict, List, Optional, Tuple, NamedTuple
from collections import Counter

from BaseClasses import Item, CollectionState, ItemClassification, LocationProgressType  #

from . import _log

from .ids import (
    AreaID, 
    ItemID, 
    LocationID,
    ExitID,
    MANTRA_ITEMS, 
    MANTRA_LOCATIONS, 
    ORIGINAL_SHOPS,
    ORIGINAL_SHOP_ITEMS,
    ORIGINAL_SHOP_PRICES,
    get_item_name_from_id,
    SHOP_ITEM_IDS,
    SHOP_WRITE_ORDER,
    DISSONANCE_IDS,
    BASE_ITEM_ID,
    GUARDIAN_ANKHS_LOCATIONS,
    GUARDIAN_ANKHS_ITEMS,
    LOGIC_FLAG_LOCATION_IDS,
    LOGIC_FLAG_ITEM_IDS,
    AP_ITEM_PLACEHOLDER,
    GLOSSARY_ITEM_IDS,
    AMMO_ITEM_IDS,
    FILLER_ITEM_IDS,
)
from .items import (
    build_item_pool,
    apply_starting_inventory,
    get_game_item_id,
    create_item,
    create_filler_item,
    create_logic_flag_item,
    get_starting_item_ids,
    build_pre_filler,
    AP_FILLER,
    INTERNAL_POOL_BY_REWARD,
    INTERNAL_ID_TO_REWARD,
    LM2Item,
)
from .locations import (
    create_locations,
    LM2Location,
    LocationType,
    is_shop_location,
    is_mural_location,
    is_chest_location,
    is_guardian_location,
    is_miniboss_location,
    get_locations_of_type,
    get_unplaced_locations_of_type
)
from .regions import (
    AREA_DEFS,
    ExitType,
    LM2Entrance
)
from .entrances import EntrancePair, SoulGatePair
from .logic.player_state import PlayerStateAdapter

class ShopEntry(NamedTuple):
    location_id: LocationID
    item_id: ItemID
    price_multiplier: int

class LM2RandomizerCore:
    """
    Python parity layer for Randomiser.cs

    Responsibilities:
    This version replicates vanilla LM2 behavior:
    - Shuffle items once globally
    - Place with logic checks (assumed fill for required, random for non-required)
    - Validate completion
    - Signal regeneration if invalid
    """

    def __init__(self, world):
        self.world = world
        self.multiworld = world.multiworld
        self.player = world.player
        self.options = world.options

        # ---  World values ---
        self.starting_weapon = world.starting_weapon
        self.starting_area = world.starting_area

        # --- Quality of Life ---
        self.starting_money = self.options.starting_money.value
        self.starting_weights = self.options.starting_weights.value
        self.item_chest_color = self.options.item_chest_color.value
        self.filler_chest_color = self.options.filler_chest_color.value
        self.ap_chest_color = self.options.ap_chest_color.value


        # --- Containers ---
        self.locations: Dict[LocationID, LM2Location] = {}
        self.shop_entries: list = []
        self.cursed_locations: List[LocationID] = []
        self.entrance_pairs = []
        self.soul_gate_pairs = []
        self._filler_id_cache: Dict[LocationID, ItemID] = {}

        # Use a different seed for each attempt by adding attempt number
        # We'll get this from the world if available
        if hasattr(world, 'generation_attempt'):
            seed = world.multiworld.seed + world.generation_attempt
        else:
            seed = world.multiworld.seed
    
        self.rng = random.Random(seed)

    # ============================================================
    # Entry point
    # ============================================================

    def setup_preplaced_items(self):
        """
        Place items that must be in specific spots BEFORE AP fills.
        Called from World.set_rules().
        """
        self.locations = self.world.locations
    
        # Place logic flags (bosses, puzzles, etc.)
        self._place_logic_flags()
    
        # Handle special mechanics  
        self._randomize_cursed_chests()
        self._choose_echidna_type()

        # Place starting shop items 
        self._place_starting_shop_items()
    
        # Original placements if applicable
        if self.options.shop_placement.value == 0:  # original
            self._place_shop_items_original()
        else:
            self._place_shop_items_random()
    
        # only_murals placement is deferred to place_mantras_post_er() (pre_fill)
        self._place_mantras()

        if not self.options.random_research:
            self._place_research()
    
        if not self.options.random_dissonance:
            self._place_dissonance()
    
        # Fix logic
        self._fix_nibiru_logic()
        self._fix_spiral_gate_logic()
        # Branch A (guardian_specific_ankhs) is topology-independent — each
        # guardian just needs its own jewel — so it can run here. Branch B's
        # cumulative AnkhCount is derived from reachability and MUST wait until
        # after connect_entrances: soul gates read
        # "GuardianKills(N) or Setting(Random Soul Gates)", so with random soul
        # gate values every gate is unconditionally open at set_rules time and
        # the real requirement is only injected during ER. Grouping here would
        # see an ungated world, put all 9 guardians in one group and stamp
        # AnkhCount(9) on each. See fix_ankh_logic_post_er().
        if self.options.guardian_specific_ankhs:
            self._fix_ankh_logic()

    def _remove_item_from_pool(self, item_id: ItemID, item_name: str) -> bool:
        """
        Remove an item from the pool, handling cases where multiple items have the same name.
        Returns True if removed, False if not found.
        """
        mw = self.multiworld
        player = self.player
    
        # First try to remove by exact ID
        for pool_item in list(mw.itempool):
            if pool_item.player == player:
                try:
                    pool_item_id = get_game_item_id(pool_item)
                    if pool_item_id == item_id:
                        mw.itempool.remove(pool_item)
                        _log(f"[DEBUG] Removed {item_name} (ID: {item_id}) from pool")
                        return True
                except:
                    continue
    
        # If not found by ID, try to remove any item with the same name
        # This is important for Ankh Jewels which have the same name but different IDs
        for pool_item in list(mw.itempool):
            if pool_item.player == player and pool_item.name == item_name:
                mw.itempool.remove(pool_item)
                _log(f"[DEBUG] Removed {item_name} from pool (by name, ID mismatch)")
                return True
    
        _log(f"[DEBUG] Warning: Could not remove {item_name} (ID: {item_id}) from pool")
        return False

    def _place_available_at_start(self, items_copy: List[Item]) -> bool:
        """
        Place items that are set to AvailableAtStart (if any)
        """
        # Currently, our options don't have AvailableAtStart, only Starting
        # This is a parity issue with the C# version
        # For now, we'll just return True
        return True

    # ============================================================
    # Logic Checks
    # ============================================================

    def _place_logic_flags(self):
        """
        Place non-shuffled logic flag items (bosses, puzzles) at their vanilla locations.
        """
        mw = self.multiworld
        player = self.player

        logic_flags = LOGIC_FLAG_LOCATION_IDS
    
        for loc_id, expected_item_name in logic_flags.items():
            if loc_id not in self.locations:
                continue
    
            loc = self.locations[loc_id]
        
            # Always ensure the location has the correct item with correct player ID
            needs_update = False
        
            if loc.item is None:
                needs_update = True
            elif loc.item.name != expected_item_name:
                needs_update = True
            elif loc.item.player != player:
                needs_update = True
        
            if needs_update:
                loc.item = None
                flag_item = create_logic_flag_item(self.world, expected_item_name)
                flag_item.player = player  # CRITICAL!
                loc.event = True   # must be set BEFORE push_item for AP event handling
                loc.address = None
                mw.push_item(loc, flag_item, collect=False)
                loc.locked = True
    
    def _can_reach_location(self, location: LM2Location, state: CollectionState) -> bool:
        """
        Check if a location is reachable in the given state.
    
        Args:
            location: The location to check
            state: The collection state to evaluate
        
        Returns:
            bool: True if the location is reachable
        """
        return location.can_access(state)

    def _fix_nibiru_logic(self):
        """Fix Nibiru logic based on required skulls setting."""
        nibiru_diss = self.locations.get(LocationID.DissonanceNibiru)
        if nibiru_diss:
            req = self.options.required_skulls
            if hasattr(req, "value"):
                req = req.value
            nibiru_diss.append_logic_string(f" and SkullCount({int(req)})")

    def _choose_echidna_type(self):
        """Choose Echidna type based on settings."""
        # In C#, this sets Settings.ChosenEchidna based on random or fixed
        # We don't have this option in our Python version yet, so just pass
        pass

    # Tower of Oannes rooms are backside areas without a Holy Grail tablet and
    # are very easy to die in. The temporary save point that makes them
    # survivable needs Hand Scanner + Totem Pole, so arriving there without both
    # is out of logic. Internal exits count too: the gate is the room itself,
    # not the area boundary (Right-B is only ever entered through internal
    # exits).
    OANNES_CHECKPOINT_AREAS = frozenset({
        AreaID.TowerOfOannesLeftA,
        AreaID.TowerOfOannesLeftC,
        AreaID.TowerOfOannesRightB,
    })

    def _fix_spiral_gate_logic(self):
        # Match Randomiser.cs behavior for SpiralGate exit
        entrances = self.multiworld.get_entrances(self.player)
        spiral_gates = [e for e in entrances if hasattr(e, "exit_type") and str(e.exit_type) == "ExitType.SpiralGate"]

        for e in spiral_gates:
            # Avoid double-appending if generation retries
            s = getattr(e, "_original_logic", "")
            if "GuardianKills(" in s or "IsDead(Anu)" in s:
                continue

            if self.options.random_dissonance:
                e.append_logic_string(" and GuardianKills(5)")
            else:
                e.append_logic_string(" and IsDead(Anu)")

    def _fix_ankh_logic(self):
        """
        Add Ankh requirements to guardian locations to prevent softlocks.
        C# parity with Randomiser.cs::FixAnkhLogic(), extended for
        guardian_specific_ankhs mode.

        Two branches:
        ─ guardian_specific_ankhs ON
            Each guardian location simply requires Has("Ankh Jewel (BossName)").
            No cumulative grouping needed — each boss needs exactly its own
            jewel, so there is no generic-pool-drain softlock risk.

        ─ guardian_specific_ankhs OFF  (vanilla behavior, unchanged)
            Flood-fill grouping assigns cumulative AnkhCount(N) so the player
            cannot lock themselves out by spending jewels at inaccessible ankhs.
        """
        guardian_locations = [
            loc for loc in self.locations.values()
            if loc.location_type == LocationType.Guardian
        ]
        total_guardians = len(guardian_locations)
        _log(f"[DEBUG] Total guardians: {total_guardians}")

        # ── Branch A: guardian-specific mode ────────────────────────────────
        if self.options.guardian_specific_ankhs:
            for loc in guardian_locations:
                ankh_name = GUARDIAN_ANKHS_LOCATIONS.get(loc.game_location_id)
                if ankh_name is None:
                    # Fallback: unknown guardian keeps generic single-jewel gate
                    loc.append_logic_string("and AnkhCount(1)")
                    _log(f"[DEBUG] {loc.name}: no specific ankh mapping, fell back to AnkhCount(1)")
                    continue
                loc.append_logic_string(f"and Has({ankh_name})")
                _log(f"[DEBUG] {loc.name}: requires {ankh_name}")
            return  # nothing more to do in this mode

        # ── Branch B: vanilla cumulative mode ───────────────────────────────
        guardian_groups = []

        # Create a state that ignores guardians for grouping.
        # PlayerStateAdapter holds the state via weakref, so we must keep a
        # strong local reference alive for the duration of this function —
        # otherwise the copy is GC'd and state_adapter.state returns None.
        state_copy = self.multiworld.state.copy()
        state_adapter = PlayerStateAdapter(
            state_copy,
            self.player,
            self.multiworld,
            self.options
        )
        state_adapter.set_starting_area(self.starting_area)
        state_adapter.ignore_guardians = True
        state_adapter.force_tree_eval = True

        # C# parity: Collect ALL items (Items), not just itempool.
        for it in self.multiworld.itempool:
            if it.player == self.player:
                state_adapter.state.collect(it, True)
                state_adapter._collect_item_name(it.name)

        # NO logic-flag event may be seeded here — not guardians, and not
        # minibosses or puzzle completions either. C# builds this state from
        # `Items` (the item POOL), which holds no flags at all; every flag is
        # earned by the flood-fill below as its location becomes reachable.
        #
        # Seeding them hands each guardian its prerequisites for free: Anu needs
        # IsDead(Ki sikil lil la ke), Aten Ra needs IsDead(Sekhmet), Echidna the
        # two HoM paths, Jormungand needs Cetus, Kujata needs Ixtab, Vritra needs
        # Vucub Caquix. Pre-granted, all nine guardians are reachable in pass 1,
        # collapse into ONE group, and each gets AnkhCount(9) — which deadlocks
        # against the Ankh Jewel that vanilla Hiner Shop 4 sells behind
        # GuardianKills(3).
        #
        # Items pre-placed at REAL locations (shops, mantras, research,
        # dissonance) ARE collected: those were still in C#'s pool at this point,
        # and the port has already removed them from multiworld.itempool.
        for loc in self.locations.values():
            if loc.address is None:
                continue  # event / logic-flag location — earn it in the flood-fill
            if loc.item is not None and loc.item.player == self.player:
                state_adapter.state.collect(loc.item, True)
                state_adapter._collect_item_name(loc.item.name)

        # Collect precollected items
        for it in self.multiworld.precollected_items[self.player]:
            state_adapter.state.collect(it, True)
            state_adapter._collect_item_name(it.name)

        required_locations = [
            loc for loc in self.locations.values()
            if loc.item is not None and loc.item.classification == ItemClassification.progression
        ]

        # Outer loop: up to 9 guardian progression steps
        for _ in range(9):
            guardians_in_step = []

            # Inner flood-fill
            while True:
                reachable = []
                for loc in required_locations:
                    if loc.game_location_id.value in state_adapter.collected_locations:
                        continue
                    if loc.can_access_with_adapter(state_adapter):
                        reachable.append(loc)

                if not reachable:
                    break

                for loc in reachable:
                    if loc.location_type == LocationType.Guardian:
                        guardians_in_step.append(loc)
                        state_adapter.collect_location(loc)
                    else:
                        if loc.item is not None:
                            state_adapter.state.collect(loc.item, True)
                            state_adapter._collect_item_name(loc.item.name)
                        state_adapter.collect_location(loc)

                state_adapter.remove_false_checked_areas_and_entrances()

            if guardians_in_step:
                guardian_groups.append(guardians_in_step)

            # C# parity: collect guardian items after grouping
            for g in guardians_in_step:
                if g.item is not None:
                    state_adapter.state.collect(g.item, True)
                    state_adapter._collect_item_name(g.item.name)

            # Advance the Guardians counter once per step
            state_adapter._collect_item_name("Guardians")

        # Apply cumulative AnkhCount requirements
        ankhs_required = 0
        for group in guardian_groups:
            ankhs_required += len(group)
            for guardian in group:
                guardian.append_logic_string(f" and AnkhCount({ankhs_required})")

        _log(f"[DEBUG] Maximum Ankh requirement: {ankhs_required}/{total_guardians}")

        for i, group in enumerate(guardian_groups):
            _log(f"[DEBUG] Guardian group {i+1} ({len(group)} guardians, "
                  f"need {sum(len(g) for g in guardian_groups[:i+1])} ankhs):")
            for guardian in group:
                _log(f"[DEBUG]   - {guardian.name}")

    # ============================================================
    # Shop randomization
    # ============================================================

    def _plando_reserved_location_names(self) -> set:
        """
        Location names targeted by item plando.

        The custom shop fill runs during World.set_rules(), long before AP runs
        item plando (Main.distribute_planned_blocks). If the shop fill claimed a
        slot first, a plando placement into that shop would silently fail. So we
        leave any plando-targeted location open for AP to fill later.
        """
        reserved: set = set()
        try:
            blocks = self.world.options.plando_items.value
        except Exception:
            return reserved
        for block in blocks or []:
            for name in getattr(block, "locations", None) or []:
                reserved.add(name)
        return reserved

    def _place_starting_shop_items(self):
        """
        C# parity: always place Weights + starting subweapon ammo into the starting shop,
        even when ShopPlacement is Original.
        """
        _log("[DEBUG] Placing starting shop items (weights/ammo)")

        mw = self.multiworld
        reserved = self._plando_reserved_location_names()

        def safe_remove(game_item_id: ItemID, name: str) -> None:
            try:
                self._remove_item_from_pool(game_item_id, name)
            except Exception:
                pass

        if self.starting_area == AreaID.VoD:
            # Always place Weights in Nebur Shop 1
            neburs_shop1 = self.locations.get(LocationID.NeburShop1)
            if neburs_shop1 and neburs_shop1.item is None and neburs_shop1.name not in reserved:
                safe_remove(ItemID.Weights, "Weights")
                mw.push_item(neburs_shop1, create_item(self.world, "Weights"), collect=False)
                neburs_shop1.locked = True

            # Always place starting subweapon ammo in Nebur Shop 2 (if subweapon start)
            if self.starting_weapon > ItemID.Katana:
                neburs_shop2 = self.locations.get(LocationID.NeburShop2)
                if neburs_shop2 and neburs_shop2.item is None and neburs_shop2.name not in reserved:
                    ammo_item_id = self._get_ammo_for_weapon(self.starting_weapon)
                    ammo_name = get_item_name_from_id(ammo_item_id)
                    safe_remove(ammo_item_id, ammo_name)
                    mw.push_item(neburs_shop2, create_item(self.world, ammo_name, game_id=ammo_item_id), collect=False)
                    neburs_shop2.locked = True
        else:
            # Non-VoD start: place Weights in StartingShop1
            starting_shop1 = self.locations.get(LocationID.StartingShop1)
            if starting_shop1 and starting_shop1.item is None and starting_shop1.name not in reserved:
                safe_remove(ItemID.Weights, "Weights")
                mw.push_item(starting_shop1, create_item(self.world, "Weights"), collect=False)
                starting_shop1.locked = True

            # Place starting subweapon ammo in StartingShop2 (if subweapon start)
            if self.starting_weapon > ItemID.Katana:
                starting_shop2 = self.locations.get(LocationID.StartingShop2)
                if starting_shop2 and starting_shop2.item is None and starting_shop2.name not in reserved:
                    ammo_item_id = self._get_ammo_for_weapon(self.starting_weapon)
                    ammo_name = get_item_name_from_id(ammo_item_id)
                    safe_remove(ammo_item_id, ammo_name)
                    mw.push_item(starting_shop2, create_item(self.world, ammo_name, game_id=ammo_item_id), collect=False)
                    starting_shop2.locked = True
        
            #starting_shop3 = self.locations.get(LocationID.StartingShop3)
            #if starting_shop3 and starting_shop3.item is None:
            #    self._remove_item_from_pool(ItemID.Weights, "Weights")
            #    weights_item = create_item(self.world, "Weights")
            #    mw.push_item(starting_shop3, weights_item, collect=False)
            #    # starting_shop3.locked = True
            #    _log(f"[DEBUG] Placed Weights at Starting Shop 3")

    def _place_shop_items_random(self) -> bool:
        """
        Full parity with C#:
          - shops are filled ONLY from shop-only items (GetAndRemoveShopOnlyItems)
          - candidate pool = (one of each shop item) + (free_slots random picks with replacement)
          - choose free_slots from that candidate pool
        """
        placement = self.options.shop_placement.value
        mw = self.multiworld

        if placement == self.options.shop_placement.option_original:
            return True

        # Slot count (same as your current logic)
        free_slots = 24
        if self.starting_weapon > ItemID.Katana:
            free_slots -= 1
        if self.starting_area != AreaID.VoD:
            free_slots += 3

        # Collect shop locations. Skip any slot targeted by item plando so it
        # stays open for AP's later plando placement (see
        # _plando_reserved_location_names).
        reserved = self._plando_reserved_location_names()
        shop_locations = [
            loc for loc in self.locations.values()
            if loc.location_type == LocationType.Shop and not loc.locked
            and loc.name not in reserved
        ]

        if placement == self.options.shop_placement.option_shuffled:
            hiner3 = next((l for l in shop_locations if l.game_location_id == LocationID.HinerShop3), None)
            if hiner3:
                hiner3.locked = True
        elif placement == self.options.shop_placement.option_at_least_one:
            for loc in shop_locations:
                if loc.name.endswith("3"):
                    loc.locked = True

        open_slots = [l for l in shop_locations if not l.locked and l.item is None]
        if len(open_slots) < free_slots:
            _log(f"[ERROR] Not enough open shop slots: {len(open_slots)} < {free_slots}")
            return False

        order_index = {lid: i for i, lid in enumerate(SHOP_WRITE_ORDER)}
        open_slots.sort(key=lambda l: order_index.get(l.game_location_id, 9999))

        # Build shop-only candidate pool (C# CreateRandomShopPool)
        from .items import build_shop_item_ids
        shop_only_ids = list(build_shop_item_ids(self.world))

        # Don't duplicate the preplaced starting ammo (VoD + subweapon start)
        if self.starting_weapon > ItemID.Katana:
            try:
                starting_ammo = self._get_ammo_for_weapon(self.starting_weapon)
                shop_only_ids = [iid for iid in shop_only_ids if iid != starting_ammo]
            except Exception:
                pass

        # C# would crash if shop_only_ids empty; we should guard
        if not shop_only_ids:
            _log("[ERROR] No shop-only item ids available for randomized shops")
            return False

        # Candidate pool ids: one of each + free_slots random picks (with replacement)
        chosen_ids: List[ItemID] = list(shop_only_ids)
        remaining = max(0, free_slots - len(chosen_ids))
        for _ in range(remaining):
            chosen_ids.append(self.rng.choice(shop_only_ids))

        self.rng.shuffle(chosen_ids)

        # Create items
        chosen: List[Item] = []
        for iid in chosen_ids:
            name = get_item_name_from_id(iid)
            chosen.append(create_item(self.world, name, game_id=iid))

        _log(f"[DEBUG] Randomized shops (parity): placing {len(chosen)} items into {len(open_slots)} open slots")

        # Price multipliers + AP placeholder
        LOWEST_PRICE_MULTIPLIER = 1

        def price_multiplier_for(item: Item) -> int:
            try:
                iid = get_game_item_id(item)
            except Exception:
                return LOWEST_PRICE_MULTIPLIER
            if iid is None:
                return LOWEST_PRICE_MULTIPLIER
            if iid in SHOP_ITEM_IDS:
                return 10
            for _, (vanilla_item_id, vanilla_price) in ORIGINAL_SHOPS.items():
                if vanilla_item_id == iid:
                    return vanilla_price
            return 10

        # Place into shops (no prog-first ordering; C# is just randomised shop pool)
        # If you *want* to keep prog-first, it will diverge from C# behavior.
        self.rng.shuffle(open_slots)

        placed_items: List[Item] = []
        for item in chosen:
            if not open_slots:
                break
            loc = open_slots.pop()
            mw.push_item(loc, item, collect=False)
            loc.locked = True
            placed_items.append(item)

            try:
                iid = get_game_item_id(item)
            except Exception:
                iid = -1

            self.shop_entries.append(ShopEntry(
                location_id=loc.game_location_id,
                item_id=iid,
                price_multiplier=price_multiplier_for(item)
            ))

        return True

    def _place_shop_items_original(self):
        """
        Place original shop items if shop_placement is Original.
        """
        placement = self.options.shop_placement.value

        if placement != self.options.shop_placement.option_original:
            _log(f"[DEBUG] Shop placement is {placement}, not placing original shops")
            return

        _log("[DEBUG] Placing original shop items")

        if (self.starting_area == AreaID.VoD) and (self.starting_weapon > ItemID.Katana):
            try:
                self._remove_item_from_pool(ItemID.Map1, "Map")
                _log("[DEBUG] C# parity: removed Map1 because NeburShop2 is used by starting ammo")
            except Exception:
                pass

        mw = self.multiworld
        player = self.player

        placed_items_info = []

        for loc_id, (item_id, price_multiplier) in ORIGINAL_SHOPS.items():
            if loc_id not in self.locations:
                continue

            loc = self.locations[loc_id]

            # Skip if already filled
            if loc.item is not None:
                _log(f"[DEBUG] {loc.name} already has {loc.item.name}, skipping")
                continue

            if item_id in ORIGINAL_SHOP_ITEMS:
                item_name = get_item_name_from_id(item_id)

                # SPECIAL HANDLING:
                # If we're placing Shield3 (Angel Shield) in a shop, but the pool uses "Progressive Shield",
                # asking to remove ID 78 will fail. We must ask to remove "Progressive Shield".
                if item_id == ItemID.Shield3:
                    if not self._remove_item_from_pool(ItemID.None_, "Progressive Shield"):
                        self._remove_item_from_pool(item_id, item_name)
                else:
                    self._remove_item_from_pool(item_id, item_name)

            # Get item name
            try:
                item_name = get_item_name_from_id(item_id)
            except ValueError as e:
                _log(f"[ERROR] Failed to get name for ItemID {item_id}: {e}")
                continue

            # Ankh Jewels need the boss-specific name when guardian_specific_ankhs
            # is on, otherwise the pool's "Ankh Jewel (Boss)" gets removed by ID
            # and is replaced with a generic "Ankh Jewel"
            if (item_name == "Ankh Jewel"
                    and getattr(self.options, "guardian_specific_ankhs", False)):
                specific = GUARDIAN_ANKHS_ITEMS.get(item_id)
                if specific:
                    ap_item = LM2Item(
                        name=specific,
                        classification=ItemClassification.progression,
                        code=BASE_ITEM_ID + item_id.value,
                        player=self.player,
                    )
                    ap_item.lm2_game_id = item_id
                    mw.push_item(loc, ap_item, collect=False)
                    loc.locked = True
                    self.shop_entries.append(ShopEntry(loc_id, item_id, price_multiplier))
                    placed_items_info.append((specific, loc.name))
                    _log(f"[DEBUG] Placed {specific} (ID: {item_id}) at {loc.name}")
                    continue

            item = create_item(self.world, item_name, game_id=item_id)

            mw.push_item(loc, item, collect=False)
            loc.locked = True

            self.shop_entries.append(ShopEntry(loc_id, item_id, price_multiplier))
            placed_items_info.append((item_name, loc.name))
            _log(f"[DEBUG] Placed {item_name} (ID: {item_id}) at {loc.name}")

        # C# parity: for non-VoD starts, place Weights in StartingShop2 (melee only) and StartingShop3
        if self.starting_area != AreaID.VoD:
            if self.starting_weapon <= ItemID.Katana:
                starting_shop2 = self.locations.get(LocationID.StartingShop2)
                if starting_shop2 and starting_shop2.item is None:
                    mw.push_item(starting_shop2, create_item(self.world, "Weights"), collect=False)
                    starting_shop2.locked = True
                    _log(f"[DEBUG] Placed Weights at Starting Shop 2 (melee start)")

            starting_shop3 = self.locations.get(LocationID.StartingShop3)
            if starting_shop3 and starting_shop3.item is None:
                mw.push_item(starting_shop3, create_item(self.world, "Weights"), collect=False)
                starting_shop3.locked = True
                _log(f"[DEBUG] Placed Weights at Starting Shop 3")


    # Price tag for the optional expensive slot, in coins.
    EXPENSIVE_SHOP_PRICE = 1000

    # Buying it needs either the Harp to drop the price to 50 or
    # Ganesha's Talisman plus the Money Fairy to farm the coins.
    EXPENSIVE_SHOP_LOGIC = (
        "and (Has(Harp) or (Has(Ganesha's Talisman) and Has(Money Fairy)))"
    )

    def pick_expensive_shop_slot_post_er(self) -> None:
        """
        Choose the 1000-coin shop slot and gate it, from World.pre_fill().

        Runs before fill so the logic gate is in place while items are placed;
        the price itself is stamped later in _adjust_shop_prices(), once the
        slot's item is actually known.
        """
        self.expensive_shop_location = None
        if not getattr(self.options, "include_expensive_shop_item", False):
            return

        # The gate has to be stamped before fill, excluding ammo/filler/weights
        skip_ids = AMMO_ITEM_IDS | FILLER_ITEM_IDS | {ItemID.Weights}
        candidates = []
        for loc_id, loc in self.locations.items():
            if not is_shop_location(loc):
                continue
            item = loc.item
            if item is not None:
                try:
                    if get_game_item_id(item) in skip_ids:
                        continue
                except Exception:
                    continue
            candidates.append((loc_id, loc))

        if not candidates:
            _log("[DEBUG] Expensive shop item: no eligible slot")
            return

        # With vanilla shops, use the originally expensive Enga Musica:
        chosen = None
        if self.options.shop_placement == self.options.shop_placement.option_original:
            chosen = next(
                ((lid, loc) for lid, loc in candidates
                 if lid == LocationID.BTKShop3),
                None,
            )
            if chosen is None:
                _log("[DEBUG] Expensive shop item: BTK Shop 3 not eligible, "
                     "falling back to a random slot")

        loc_id, loc = chosen if chosen is not None else self.rng.choice(candidates)
        loc.append_logic_string(self.EXPENSIVE_SHOP_LOGIC)
        self.expensive_shop_location = loc_id
        _log(f"[DEBUG] Expensive shop slot: {loc.name} "
             f"({self.EXPENSIVE_SHOP_PRICE} coins)")

    def _adjust_shop_prices(self):
        """
        Assign shop prices based on which sphere the item becomes reachable in.
        mirroring the C# AdjustShopPrices() logic but halved for AP
        (players buy more in multiworld so prices are kept lower).
        C# range: multiplier 5-9  (sphere 1 = 5, sphere 5+ = 9)
        AP range:  multiplier 4-8  (scaled on total amount of spheres)
        """
        ap_map = self._get_ap_placeholder_map()
        for loc_id, loc in self.locations.items():
            if not is_shop_location(loc) or loc.item is None:
                continue
            if any(e.location_id == loc_id for e in self.shop_entries):
                continue
            if loc.item.player != self.player:
                item_id = ap_map.get(loc_id, AP_ITEM_PLACEHOLDER)
            else:
                try:
                    item_id = get_game_item_id(loc.item)
                except Exception:
                    continue
            self.shop_entries.append(ShopEntry(loc_id, item_id, 5))

        entry_index = {}
        for i, entry in enumerate(self.shop_entries):
            entry_index[entry.location_id] = i

        # Pass 1 -- fixed prices. Ammo stays at vanilla (ShopPrice x 10) and
        # weights are static mod-side; neither is worth scaling by sphere.
        fixed = set()
        for i, entry in enumerate(self.shop_entries):
            if entry.item_id in AMMO_ITEM_IDS:
                fixed.add(entry.location_id)
                self.shop_entries[i] = ShopEntry(entry.location_id, entry.item_id, 10)
            elif entry.item_id == ItemID.Weights or entry.item_id in FILLER_ITEM_IDS:
                fixed.add(entry.location_id)

        # Expensive slot: the mod computes price as ShopPrice x
        # Multiplier, and an AP placeholder has no ItemDB entry so its
        # ShopPrice defaults to 10 -- hence 1500 / 10. A real item's ShopPrice
        # varies, so this lands on the intended number only for AP items until
        # the mod takes an absolute price.
        expensive_loc = getattr(self, "expensive_shop_location", None)

        if not entry_index:
            return

        # Ranking the distinct sphere numbers that actually contain shop slots
        # spreads the range across the shops that exist: the first-reachable
        # shops get min, the last-reachable get max, and ties (all the sphere-0
        # shops) price identically.
        spheres = list(self.multiworld.get_spheres())

        shop_spheres = sorted({
            idx for idx, sphere in enumerate(spheres)
            for location in sphere
            if location.player == self.player
            and getattr(location, "game_location_id", None) in entry_index
            and getattr(location, "game_location_id", None) not in fixed
        })
        rank_of = {sphere_idx: rank for rank, sphere_idx in enumerate(shop_spheres)}
        last_rank = max(len(shop_spheres) - 1, 1)

        # ShopPrice x multiplier is the mod's formula, and an AP placeholder
        # has no ItemDB entry so its ShopPrice defaults to 10 -- these bounds
        # put a foreign item at 50 in the earliest shops and 100 in the latest.
        min_mult = 5
        max_mult = 10

        assigned = set()

        for sphere_idx, sphere in enumerate(spheres):
            if sphere_idx not in rank_of:
                continue
            t = rank_of[sphere_idx] / last_rank
            multiplier = round(min_mult + t * (max_mult - min_mult))

            for location in sphere:
                if location.player != self.player:
                    continue
                loc_id = getattr(location, "game_location_id", None)
                if loc_id is None or loc_id not in entry_index or loc_id in assigned:
                    continue
                if loc_id in fixed:
                    continue

                # Pass 2 -- rank scaling. Every non-fixed shop slot is priced,
                # whoever the item belongs to and whatever its classification:
                # what is being priced is how deep into the seed the slot
                # unlocks, which is equally true of a foreign item or one of
                # our own "useful" ones. Restricting this to progression left
                # half the shops sitting at the backfill default.
                if location.item is None:
                    continue

                assigned.add(loc_id)
                i = entry_index[loc_id]
                old = self.shop_entries[i]
                self.shop_entries[i] = ShopEntry(
                    location_id=old.location_id,
                    item_id=old.item_id,
                    price_multiplier=multiplier
                )

        if expensive_loc is not None and expensive_loc in entry_index:
            loc = self.locations.get(expensive_loc)
            final_item = loc.item if loc is not None else None
            try:
                final_id = get_game_item_id(final_item) if final_item else None
            except Exception:
                final_id = None
            if final_id is not None and final_id in (
                    AMMO_ITEM_IDS | FILLER_ITEM_IDS | {ItemID.Weights}):
                _log("[DEBUG] Expensive shop slot ended up holding filler/ammo; "
                     "leaving it at the normal price")
                expensive_loc = None
        if expensive_loc is not None and expensive_loc in entry_index:
            i = entry_index[expensive_loc]
            old = self.shop_entries[i]
            self.shop_entries[i] = ShopEntry(
                location_id=old.location_id,
                item_id=old.item_id,
                price_multiplier=self.EXPENSIVE_SHOP_PRICE // 10,
            )
            _log(f"[DEBUG] Expensive shop slot priced: {old.location_id} "
                 f"-> multiplier {self.EXPENSIVE_SHOP_PRICE // 10}")

    def _get_ammo_for_weapon(self, weapon_id: ItemID) -> ItemID:
        """Get the corresponding ammo item for a starting weapon."""
        ammo_map = {
            ItemID.Shuriken: ItemID.ShurikenAmmo,
            ItemID.RollingShuriken: ItemID.RollingShurikenAmmo,
            ItemID.EarthSpear: ItemID.EarthSpearAmmo,
            ItemID.Flare: ItemID.FlareAmmo,
            ItemID.Caltrops: ItemID.CaltropsAmmo,
            ItemID.Chakram: ItemID.ChakramAmmo,
            ItemID.Bomb: ItemID.BombAmmo,
            ItemID.Pistol: ItemID.PistolAmmo,
        }
        return ammo_map.get(weapon_id, ItemID.None_)

    # ============================================================
    # Mantra Placement
    # ============================================================

    def _place_mantras(self) -> bool:
        """
        Place mantras during the preplaced phase (AP-fill friendly).

        Removed:
          - items_copy parameter
          - reliance on an external pool copy

        Behavior preserved:
          - option_original: do not place; remove mantra items from AP pool
          - option_only_murals: place mantra items into mural locations; lock; remove from AP pool
        """
        placement_mode = self.options.mantra_placement.value
        mw = self.multiworld
        player = self.player

        def is_mantra_item(item: Item) -> bool:
            try:
                iid = get_game_item_id(item)
            except Exception:
                return False
            return iid in MANTRA_ITEMS and item.player == player

        # Collect mantra items from the real AP pool
        mantra_items = [it for it in list(mw.itempool) if is_mantra_item(it)]

        if placement_mode == self.options.mantra_placement.option_original:
            # In original mode, items.py does NOT create mantra items in the pool.
            # Therefore we must preplace them directly on their vanilla mural locations.
            for mural_loc_id, mantra_item_id in MANTRA_LOCATIONS.items():
                loc = self.locations.get(mural_loc_id)
                if loc is None:
                    _log(f"[ERROR] Missing mantra mural location id: {mural_loc_id}")
                    return False

                if loc.item is not None:
                    _log(f"[ERROR] Mantra mural already filled: {loc.name} -> {loc.item.name}")
                    return False

                name = get_item_name_from_id(mantra_item_id)
                item = create_item(self.world, name, game_id=mantra_item_id)

                mw.push_item(loc, item, collect=False)
                loc.locked = True

            return True

        return True

    def fix_fdc_logic_post_er(self) -> None:
        """
        C# parity: Randomiser.FixFDCLogic(), run from World.pre_fill().

        MainViewModel calls FixAnkhLogic() then FixFDCLogic()
        after PlaceEntrances(), which is the order pre_fill mirrors.

        * backside      -> FDC, non-internal exits only.
        * Oannes rooms  -> FDC + Hand Scanner + Totem Pole, ANY exit type.
        """
        if not self.options.require_fdc:
            return

        # Without oannesanity the checkpoint rooms hold no checks and Totem Pole
        # stays filler -- Has() ignores non-progression items, so stamping that
        # gate would close those rooms permanently for nothing.
        gate_checkpoints = bool(self.options.oannesanity)

        for exit_ in self.multiworld.get_entrances(self.player):
            if not isinstance(exit_, LM2Entrance):
                continue

            dest_area = exit_.destination_area
            if dest_area is None:
                continue

            need_checkpoint = (gate_checkpoints
                               and dest_area in self.OANNES_CHECKPOINT_AREAS)

            # C#: exit.ExitType != ExitType.Internal
            #     and GetArea(exit.ConnectingAreaID).IsBackside
            dest_area_def = AREA_DEFS.get(dest_area)
            need_backside = (exit_.exit_type != ExitType.Internal
                             and dest_area_def is not None
                             and dest_area_def.is_backside)

            if not (need_checkpoint or need_backside):
                continue

            # C#: exit.AppendLogicString(" and Has(Future Development Company)")
            clause = "and Has(Future Development Company)"
            if need_checkpoint:
                clause += " and Has(Hand Scanner) and Has(Totem Pole)"
            exit_.append_logic_string(clause)

    def fix_ankh_logic_post_er(self) -> None:
        """
        Cumulative AnkhCount grouping, run from World.pre_fill() so the entrance
        graph and the soul gate kill requirements are final. See the note in
        setup_preplaced_items() for why this cannot run at set_rules time.
        """
        if self.options.guardian_specific_ankhs:
            return  # Branch A already applied during set_rules
        self._fix_ankh_logic()

    def place_mantras_post_er(self) -> bool:
        """
        only_murals placement, run from World.pre_fill() so the entrance graph
        (structural ER + soul gate values) is final.

        C# parity with Randomiser.cs::RandomiseWithChecks(): for each mantra,
        rebuild the state from scratch out of the items still in the pool
        (minus the mantras not yet placed) and then sphere-sweep, collecting
        items off locations only once those locations are actually reachable.
        That is the same semantics AP's own accessibility sweep and the ER
        validator use, so a placement accepted here stays valid downstream.
        """
        if self.options.mantra_placement.value != self.options.mantra_placement.option_only_murals:
            return True

        mw = self.multiworld
        player = self.player

        def is_mantra_item(item: Item) -> bool:
            try:
                iid = get_game_item_id(item)
            except Exception:
                return False
            return iid in MANTRA_ITEMS and item.player == player

        mantra_items = [it for it in list(mw.itempool) if is_mantra_item(it)]
        if not mantra_items:
            _log("[WARN] only_murals: no mantra items in the AP pool, nothing to place")
            return True

        mural_locations = get_unplaced_locations_of_type(self.locations, LocationType.Mural)
        if len(mural_locations) < len(mantra_items):
            _log(f"[ERROR] Not enough mural locations ({len(mural_locations)}) "
                 f"for mantras ({len(mantra_items)})")
            return False

        def sweep_state(pending_names: set) -> CollectionState:
            """
            State with every pool item except the mantras still awaiting
            placement, then a sphere-sweep collecting placed items from
            locations as they become reachable (C# GetStateWithItems).
            """
            state = CollectionState(mw)  # collects precollected items itself
            for item in mw.itempool:
                if item.player == player and item.name not in pending_names:
                    state.collect(item, True)
            state.stale[player] = True

            remaining = [loc for loc in mw.get_locations(player)
                         if loc.parent_region is not None and loc.item is not None]
            while True:
                sphere = []
                for n in range(len(remaining) - 1, -1, -1):
                    try:
                        if remaining[n].can_reach(state):
                            sphere.append(remaining.pop(n))
                    except Exception:
                        pass
                if not sphere:
                    break
                for loc in sphere:
                    if loc.item is not None and loc.item.player == player:
                        state.collect(loc.item, True, loc)
                state.stale[player] = True
            return state

        def undo(placements):
            for loc, item in placements:
                loc.item = None
                loc.locked = False
                item.location = None

        # Assumed fill, the same algorithm AP uses for its own progression
        # placement. The previous forward-greedy loop ("take the next mantra,
        # drop it in any currently-reachable mural") could paint itself into a
        # corner -- a mantra that gates the only remaining mural had to be
        # placed before it, and reshuffling the order 15 times only sometimes
        # stumbled onto a working sequence.
        #
        # fill_restrictive walks the items in reverse against a state that
        # assumes every not-yet-placed mantra is already held, and can SWAP an
        # already-placed item out when it hits a dead end.
        from Fill import fill_restrictive

        base = CollectionState(self.multiworld)
        for item in mw.itempool:
            if item.player == player and not is_mantra_item(item):
                base.collect(item, prevent_sweep=True)

        remaining_items = list(mantra_items)
        remaining_locs = list(mural_locations)
        self.rng.shuffle(remaining_locs)
        try:
            fill_restrictive(
                mw, base, remaining_locs, remaining_items,
                single_player_placement=True, lock=True,
                name="LM2 only_murals mantras",
            )
        except Exception as exc:
            _log(f"[ERROR] only_murals fill_restrictive failed: {exc!r}")
            return False

        if remaining_items:
            _log(f"[ERROR] only_murals: {len(remaining_items)} mantra(s) could "
                 f"not be placed at a reachable mural")
            return False

        for item in mantra_items:
            if item in mw.itempool:
                mw.itempool.remove(item)
        return True


    # ============================================================
    # Research Placement
    # ============================================================

    def _place_research(self):
        """Place Research items in their vanilla locations if RandomResearch is False."""
        if not self.options.random_research:
            # Map of vanilla Research locations to items
            research_locations = {
                LocationID.ResearchAnnwfn: ItemID.Research1,
                LocationID.ResearchIBTopLeft: ItemID.Research2,
                LocationID.ResearchIBTopRight: ItemID.Research3,
                LocationID.ResearchIBTent1: ItemID.Research4,
                LocationID.ResearchIBTent2: ItemID.Research5,
                LocationID.ResearchIBTent3: ItemID.Research6,
                LocationID.ResearchIBPit: ItemID.Research7,
                LocationID.ResearchIBLeft: ItemID.Research8,
                LocationID.ResearchIT: ItemID.Research9,
                LocationID.ResearchDSLM: ItemID.Research10,
            }
        
            mw = self.multiworld
            player = self.player
        
            for loc_id, research_itemid in research_locations.items():
                if loc_id not in self.locations:
                    _log(f"[WARN] Research location {loc_id} missing, skipping")
                    continue

                loc = self.locations[loc_id]
            
                # Find the Research item in the pool
                found = None
                for item in list(mw.itempool):
                    try:
                        if get_game_item_id(item) == research_itemid and item.player == player:
                            found = item
                            break
                    except Exception:
                        continue

                if not found:
                    _log(f"[WARN] Could not find research {research_itemid} in item pool")
                    continue

                mw.itempool.remove(found)
                mw.push_item(loc, found, collect=False)
                loc.locked = True

    # ============================================================
    # Dissonance Placement
    # ============================================================

    def _place_dissonance(self):
        """Handle Dissonance location placement based on RandomDissonance setting."""
        if not self.options.random_dissonance:
            # Place Dissonance as logic flags at vanilla locations
            dissonance_locs = DISSONANCE_IDS
        
            for loc_id in dissonance_locs:
                if loc_id not in self.locations:
                    continue
            
                loc = self.locations[loc_id]
                # IMPORTANT: Use create_logic_flag_item with name "Dissonance"
                flag_item = create_logic_flag_item(self.world, "Dissonance")
                loc.event = True   # must be set BEFORE push_item
                loc.address = None
                self.multiworld.push_item(loc, flag_item, collect=False)
                loc.locked = True
        else:
            # When random_dissonance is True, Dissonance items are in the pool
            # Just unlock the locations so they can receive any item       
            pass

    # ============================================================
    # Cursed Chests
    # ============================================================

    def _randomize_cursed_chests(self):
        """
        Cursed chest randomization (unchanged from original)
        """
        # Universal Tracker regen: the cursed set is RNG-selected at generation
        # time and cannot be reproduced from options alone (UT does not replay
        # the server's RNG state). Replay the exact set recorded in slot_data so
        # the '... and Has(Mulana Talisman)' logic append matches the real seed;
        # otherwise UT would treat a cursed chest as freely accessible.
        ut_data = self.world._ut_passthrough()
        if ut_data is not None:
            self._apply_ut_cursed_locations(ut_data)
            return

        if not self.options.random_cursed_chests:
            default_cursed = [
                LocationID.FlameTorcChest,
                LocationID.GiantsFluteChest,
                LocationID.DestinyTabletChest,
                LocationID.PowerBandChest,
            ]
        
            for loc_id in default_cursed:
                if loc_id in self.locations:
                    loc = self.locations[loc_id]
                    if loc.append_logic_string("and Has(Mulana Talisman)"):
                        self.cursed_locations.append(loc_id)
        else:
            count = self.options.cursed_chests.value
            chest_locations = get_locations_of_type(self.locations, LocationType.Chest)
            cursed = self.rng.sample(chest_locations, min(count, len(chest_locations)))
        
            for loc in cursed:
                if loc.append_logic_string("and Has(Mulana Talisman)"):
                    self.cursed_locations.append(loc.game_location_id)

    def _apply_ut_cursed_locations(self, ut_data: dict):
        """Replay the server-recorded cursed set (UT regen path).

        slot_data["cursed_locations"] holds the exact LocationIDs that were
        cursed at generation time. Append the Mulana Talisman requirement to
        each so UT's logic matches the real seed.
        """
        for raw in ut_data.get("cursed_locations") or []:
            try:
                loc_id = LocationID(int(raw))
            except (TypeError, ValueError):
                continue
            loc = self.locations.get(loc_id)
            if loc is None:
                continue
            if loc.append_logic_string("and Has(Mulana Talisman)"):
                self.cursed_locations.append(loc_id)

    # ============================================================
    # Fill empty locations with filler
    # ============================================================

    def _get_unique_filler_id(self, item_id: ItemID, loc: LM2Location) -> ItemID:
            # 1. Ignore non-filler items (e.g. standard progression/tools)
            ap_filler_ids = {fid for _, fid in AP_FILLER}
            if item_id not in ap_filler_ids:
                return item_id

            # 2. Determine the functional category
            category = loc.location_type

            # --- Hijack: Use FakeItem for Shops ---
            if category == LocationType.Shop:
                category = LocationType.FreeStanding

            # --- Hijack: Use ChestWeight for Dissonance ---
            if category == LocationType.Dissonance:
                category = LocationType.Chest

            # Use per-instance pool copy (created in precompute_filler_ids)
            pool = self._local_pool

            # 3. Pick an internal ID that matches the AP reward type.
            #    This ensures the internal ID's reward always agrees with
            #    the AP item name — no fragile post-hoc sync needed.
            key = (category, item_id)
            matching_pool = pool.get(key, [])

            if matching_pool:
                chosen = self.rng.choice(matching_pool)
                matching_pool.remove(chosen)
                return chosen

            # 4. Matching sub-pool exhausted — fall back to any available
            #    internal ID in this category and sync the AP item to match.
            available = []
            for (pool_cat, _), sub_pool in pool.items():
                if pool_cat == category:
                    available.extend(sub_pool)

            if available:
                chosen = self.rng.choice(available)
                for (pool_cat, _), sub_pool in pool.items():
                    if pool_cat == category and chosen in sub_pool:
                        sub_pool.remove(chosen)
                        break

                # Sync AP item name/code to match the chosen internal ID
                reward = INTERNAL_ID_TO_REWARD.get(chosen)
                if reward and loc.item is not None:
                    reward_name, reward_ap_id = reward
                    loc.item.name = reward_name
                    loc.item.code = BASE_ITEM_ID + int(reward_ap_id)

                return chosen

            # 5. FINAL FALLBACK — entire category exhausted
            return ItemID.Weights

    def _fix_empty_locations(self):
        """
        Post-fill pass: ensure every LM2-owned *unfilled* location has some item.

        We intentionally **do not** rewrite existing filler items anymore.
        Instead, we keep AP's Coin/Weight filler items in-place so they can be
        granted consistently both cross-world (as normal AP items) and in-world.

        Location-type-specific *seed encoding* for Coin/Weight filler is handled
        later in get_item_placements()/get_shop_placements() so the binary seed
        always contains item IDs that are valid for that location type.
        """
        for loc in self.multiworld.get_locations(self.player):
            if loc.locked:
                continue
            if loc.item is not None:
                continue

            filler = build_pre_filler(self.world)
            _log(f"[FILL] {loc.name} <- {filler.name} class={filler.classification}")
            self.multiworld.push_item(loc, filler, collect=False)


    # ============================================================
    # Filler ID pre-computation (must run in post_fill, before
    # the thread pool that runs generate_output + write_multidata
    # concurrently — otherwise loc.item mutations race with the
    # multidata builder reading location.item.code)
    # ============================================================

    def precompute_filler_ids(self):
        """Assign unique internal filler IDs for every location and sync
        ``loc.item`` when the fallback path changes the reward type.

        Must be called from ``post_fill()`` so that mutations to
        ``loc.item.name`` / ``loc.item.code`` are visible to
        ``write_multidata()``, which runs concurrently with
        ``generate_output()`` in the AP thread pool.
        """
        self._filler_id_cache: Dict[LocationID, ItemID] = {}

        # Deep-copy the global pool so each world instance gets its own
        # supply and multi-world games don't share a depleted pool.
        self._local_pool: Dict[tuple, list] = {
            k: list(v) for k, v in INTERNAL_POOL_BY_REWARD.items()
        }

        # --- Non-shop locations first (same iteration order as
        #     get_item_placements so the RNG and pool consumption
        #     stay deterministic) ---
        for loc in self.locations.values():
            if loc.item is None:
                continue
            if loc.game_location_id == LocationID.None_:
                continue
            # Skip logic-flag/boss locations (253-399), allow sanities
            if LocationID.Ratatoskr1 <= loc.game_location_id < 400:
                continue
            if loc.item.player != self.player:
                continue
            if is_shop_location(loc):
                continue

            try:
                item_id = get_game_item_id(loc.item)
            except KeyError:
                continue

            if item_id in LOGIC_FLAG_ITEM_IDS:
                continue
            if item_id == ItemID.None_:
                continue

            translated = self._get_unique_filler_id(item_id, loc)
            if translated != item_id:
                self._filler_id_cache[loc.game_location_id] = translated

        # --- Shop locations second (same order as get_shop_placements) ---
        for loc_id, loc in self.locations.items():
            if not is_shop_location(loc):
                continue
            if loc.item is None:
                continue
            if loc_id == LocationID.None_:
                continue
            # Skip logic-flag/boss locations (253-399), allow sanities
            if LocationID.Ratatoskr1 <= loc_id < 400:
                continue
            if loc.item.player != self.player:
                continue

            try:
                item_id = get_game_item_id(loc.item)
            except Exception:
                continue

            if item_id == ItemID.None_:
                continue

            translated = self._get_unique_filler_id(item_id, loc)
            if translated != item_id:
                self._filler_id_cache[loc_id] = translated

    # ============================================================
    # Seed writer extraction API
    # ============================================================

    def get_item_placements(self) -> List[Tuple[LocationID, ItemID]]:
        """
        Returns final item placements for seed writing.
        Matches C# logic: location.ID < LocationID.Ratatoskr1 && location.ID != LocationID.None && location.Item.ID != ItemID.None
        """
        result: List[Tuple[LocationID, ItemID]] = []
        ap_map = self._get_ap_placeholder_map()

        for loc in self.locations.values():
            if loc.item is None:
                continue

            # Skip LocationID.None (0) - though this should never happen
            if loc.game_location_id == LocationID.None_:
                continue

            # Skip logic-flag/boss locations (253-399), allow sanities
            if LocationID.Ratatoskr1 <= loc.game_location_id < 400:
                continue

            # Get the game item ID — use unique AP placeholder for items belonging to other players
            if loc.item.player != self.player:
                item_id = ap_map.get(loc.game_location_id, AP_ITEM_PLACEHOLDER)
            else:
                try:
                    item_id = get_game_item_id(loc.item)
                except KeyError:
                    _log(f"[WARN] Skipping item {loc.item.name} at {loc.name} - no game ID")
                    continue
                # Own glossary ROM / pot filler: route through the per-location placeholder
                # so the location's AP mechanism (NPC/Kataribe, mural, chest, …) fires the
                # check + sold-out.
                if loc.game_location_id in ap_map:
                    item_id = ap_map[loc.game_location_id]

            # Skip logic-only items
            if item_id in LOGIC_FLAG_ITEM_IDS:
                continue

            # Skip ItemID.None_ (0) - these shouldn't be written to seed
            if item_id == ItemID.None_:
                continue

            # Skip shop locations (handled separately)
            if is_shop_location(loc):
                continue

            # Use pre-computed filler ID (assigned in post_fill)
            item_id = self._filler_id_cache.get(loc.game_location_id, item_id)

            result.append((loc.game_location_id, item_id))

        return result

    def get_shop_placements(self) -> List[Tuple[LocationID, ItemID, int]]:
        """
        Returns shop placements for seed writing.
        Gets items from actual placed locations, not just shop_entries.
        """
        result: List[Tuple[LocationID, ItemID, int]] = []
        ap_map = self._get_ap_placeholder_map()

        # Look at all locations
        for loc_id, loc in self.locations.items():
            # Skip if not a shop
            if not is_shop_location(loc):
                continue

            # Skip if no item
            if loc.item is None:
                continue

            # Skip LocationID.None
            if loc_id == LocationID.None_:
                continue

            # Skip logic-flag/boss locations (253-399), allow sanities
            if LocationID.Ratatoskr1 <= loc_id < 400:
                continue

            # Get item ID — use unique AP placeholder for items belonging to other players
            if loc.item.player != self.player:
                item_id = ap_map.get(loc_id, AP_ITEM_PLACEHOLDER)
            else:
                try:
                    item_id = get_game_item_id(loc.item)
                except:
                    continue
                # Own glossary ROM / pot filler at a shop has no sold-out/check flag of its
                # own — route it through the per-location placeholder so the shop's sheet-31
                # mechanism fires the check + marks sold-out (server echoes the real item).
                if loc_id in ap_map:
                    item_id = ap_map[loc_id]

            # Skip ItemID.None
            if item_id == ItemID.None_:
                continue

            # Use pre-computed filler ID (assigned in post_fill)
            item_id = self._filler_id_cache.get(loc_id, item_id)

            # Get price - look in shop_entries first, then use default
            price_mult = 5
            for entry in self.shop_entries:
                if entry.location_id == loc_id:
                    price_mult = entry.price_multiplier
                    break

            result.append((loc_id, item_id, price_mult))

        # Sort by location ID
        result.sort(key=lambda x: x[0])

        return result

    def _get_ap_placeholder_map(self) -> dict:
        """
        Build (and cache) a mapping of LocationID → unique AP placeholder ItemID
        for every location in this world that contains an item from a different player.

        IDs are assigned as AP_ITEM_PLACEHOLDER + 1, +2, ... in ascending
        LocationID order so the mapping is deterministic across runs.  The C#
        plugin recognises any value in [AP_ITEM_PLACEHOLDER, BASE_ITEM_ID) as an
        AP placeholder and uses `id - AP_ITEM_PLACEHOLDER` as a unique flag index
        (sheet 31) to track collection state independently per location.
        """
        if hasattr(self, '_cached_ap_placeholder_map'):
            return self._cached_ap_placeholder_map

        # Foreign items + our own glossary ROMs / pot filler (ANY location type). The
        # latter have no per-item sold-out/check flag, so they ride the same sheet-31
        # placeholder mechanism used for foreign items — the location's AP machinery
        # (shop, NPC/Kataribe, mural, chest, …) fires the check and the server echoes
        # the real ROM back → DeliverGlossaryRom. (Chip/freestanding/scan glossary also
        # works via the scout-based MonsterChipGlossaryPatch; the echo is idempotent.)
        relevant_loc_ids = sorted(
            (int(loc_id) for loc_id, loc in self.locations.items()
             if loc.item is not None and (
                 loc.item.player != self.player
                 or self._is_glosspot_own(loc))),
        )

        self._cached_ap_placeholder_map = {
            LocationID(loc_id): AP_ITEM_PLACEHOLDER + idx + 1
            for idx, loc_id in enumerate(relevant_loc_ids)
        }
        return self._cached_ap_placeholder_map

    def _is_glosspot_own(self, loc) -> bool:
        """This player's glossary ROM (2000-2251) or pot filler (1001-1307), any location."""
        if loc.item is None or loc.item.player != self.player:
            return False
        code = getattr(loc.item, "code", None)
        if not isinstance(code, int):
            return False
        gid = code - BASE_ITEM_ID
        return (2000 <= gid <= 2251) or (1001 <= gid <= 1307)

    def get_starting_items(self) -> List[ItemID]:
        """
        Seed writer / slot_data helper.

        Returns the union of LM2-derived starters (Random X: Starting options)
        and AP `start_inventory` precollected items, minus the starting weapon
        (the C# mod handles the weapon via its own slot_data field).

        precollected_items already contains both sources by the time this is
        called: apply_starting_inventory pushes the LM2-derived starters in,
        and AP core pushes start_inventory entries in.
        """
        starting_weapon_id = int(self.starting_weapon)
        seen: set[int] = set()
        result: List[ItemID] = []

        for item in self.world.multiworld.precollected_items[self.world.player]:
            try:
                game_id = get_game_item_id(item)
            except KeyError:
                continue
            game_id_int = int(game_id)
            if game_id_int == starting_weapon_id:
                continue
            if game_id_int in seen:
                continue
            seen.add(game_id_int)
            result.append(game_id)

        return result

    def get_cursed_locations(self) -> List[LocationID]:
        return self.cursed_locations

    def get_entrance_pairs(self) -> List[Tuple[int, int]]:
        """
        Returns entrance pairs for seed writing.
        Converts ExitID enum values to integers.

        AP Generic ER stores pairs on the world object (_er_pairs).
        The legacy self.entrance_pairs list remains as a fallback for
        non-ER seeds.
        """
        # Prefer pairs recorded by AP Generic ER in connect_entrances
        er_pairs = getattr(self.world, '_er_pairs', None)
        if er_pairs:
            return [
                (int(p.from_exit), int(p.to_exit))
                for p in er_pairs
                if p.from_exit is not None and p.to_exit is not None
            ]
        # Legacy fallback (non-ER seed or manual pairs)
        return [
            (int(pair.from_exit), int(pair.to_exit))
            for pair in self.entrance_pairs
        ]

    def get_soul_gate_pairs(self) -> List[Tuple[int, int, int]]:
        """
        Returns soul gate pairs for seed writing.
        Converts ExitID enum values to integers.
        """
        sg_pairs = getattr(self.world, '_sg_pairs', None) or self.soul_gate_pairs
        return [
            (int(p.gate1), int(p.gate2), p.soul_amount)
            for p in sg_pairs
        ]