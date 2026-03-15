from __future__ import annotations

from http.client import CONFLICT
import random
from typing import Dict, List, Tuple, NamedTuple
from collections import Counter

from BaseClasses import Item, CollectionState, ItemClassification, LocationProgressType  #

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
    LOGIC_FLAG_LOCATION_IDS,
    LOGIC_FLAG_ITEM_IDS,
    AP_ITEM_PLACEHOLDER,
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
    ExitType
)
from .entrances import (
    EntranceRandomizer
)
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
    
        self._place_mantras()
    
        if not self.options.random_research:
            self._place_research()
    
        if not self.options.random_dissonance:
            self._place_dissonance()
    
        # Fix logic
        self._fix_nibiru_logic()
        self._fix_fdc_logic()
        self._fix_spiral_gate_logic()
        self._fix_ankh_logic()
    
        # Randomize entrances
        self._randomize_entrances()

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
                        print(f"[DEBUG] Removed {item_name} (ID: {item_id}) from pool")
                        return True
                except:
                    continue
    
        # If not found by ID, try to remove any item with the same name
        # This is important for Ankh Jewels which have the same name but different IDs
        for pool_item in list(mw.itempool):
            if pool_item.player == player and pool_item.name == item_name:
                mw.itempool.remove(pool_item)
                print(f"[DEBUG] Removed {item_name} from pool (by name, ID mismatch)")
                return True
    
        print(f"[DEBUG] Warning: Could not remove {item_name} (ID: {item_id}) from pool")
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
    # Entrances
    # ============================================================

    def _randomize_entrances(self):
        if not (
            self.world.options.horizontal_entrances
            or self.world.options.vertical_entrances
            or self.world.options.gate_entrances
            or self.world.options.soul_gate_entrances
            or self.world.options.full_random_entrances
        ):
            return

        entrances = []
        for region in self.multiworld.regions:
            if region.player != self.player:
                continue
            for e in region.exits:
                if hasattr(e, "game_exit_id"):
                    entrances.append(e)

        er = EntranceRandomizer(self.rng, entrances, self.world)
        self.entrance_pairs = er.randomize()
        self.soul_gate_pairs = er.soul_gate_pairs

    # ============================================================
    # Logic Checks
    # ============================================================

    def _place_logic_flags(self):
        """
        Place non-shuffled logic flag items (bosses, puzzles) at their vanilla locations.
        """
        print(f"[DEBUG] === START _place_logic_flags() ===")
        mw = self.multiworld
        player = self.player

        logic_flags = LOGIC_FLAG_LOCATION_IDS
        print(f"[DEBUG] Need to place/verify {len(logic_flags)} logic flags")
    
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
                print(f"[DEBUG] Placed '{expected_item_name}' at {loc.name} for player {player}")
            else:
                # Verify the item is collectible in state
                print(f"[DEBUG] Location {loc.name} already has correct item '{expected_item_name}' for player {player}")
    
        print(f"[DEBUG] === END _place_logic_flags() ===")

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

    def _fix_fdc_logic(self):
        """C# parity: if FDCForBacksides, add FDC requirement to non-internal exits that lead to a backside area."""
        if not self.options.require_fdc:
            return

        for region in self.multiworld.regions:
            if region.player != self.player:
                continue

            for exit in region.exits:
                # Must be an LM2Entrance
                if not hasattr(exit, "exit_type") or not hasattr(exit, "connecting_area"):
                    continue

                # C#: exit.ExitType != ExitType.Internal
                if exit.exit_type == ExitType.Internal:
                    continue

                # C#: GetArea(exit.ConnectingAreaID).IsBackside
                dest_area_def = AREA_DEFS.get(exit.connecting_area)
                if not dest_area_def or not dest_area_def.is_backside:
                    continue

                # C#: exit.AppendLogicString(" and Has(Future Development Company)")
                exit.append_logic_string("and Has(Future Development Company)")

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
        print(f"[DEBUG] Total guardians: {total_guardians}")

        # ── Branch A: guardian-specific mode ────────────────────────────────
        if self.options.guardian_specific_ankhs:
            for loc in guardian_locations:
                ankh_name = GUARDIAN_ANKHS_LOCATIONS.get(loc.game_location_id)
                if ankh_name is None:
                    # Fallback: unknown guardian keeps generic single-jewel gate
                    loc.append_logic_string("and AnkhCount(1)")
                    print(f"[DEBUG] {loc.name}: no specific ankh mapping, fell back to AnkhCount(1)")
                    continue
                loc.append_logic_string(f"and Has({ankh_name})")
                print(f"[DEBUG] {loc.name}: requires {ankh_name}")
            return  # nothing more to do in this mode

        # ── Branch B: vanilla cumulative mode ───────────────────────────────
        guardian_groups = []

        # Create a state that ignores guardians for grouping
        state_adapter = PlayerStateAdapter(
            self.multiworld.state.copy(),
            self.player,
            self.multiworld,
            self.options
        )
        state_adapter.set_starting_area(self.starting_area)
        state_adapter.ignore_guardians = True

        # C# parity: Collect ALL items (Items), not just itempool.
        for it in self.multiworld.itempool:
            if it.player == self.player:
                state_adapter.state.collect(it, True)
                state_adapter._collect_item_name(it.name)

        for loc in self.locations.values():
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

        print(f"[DEBUG] Maximum Ankh requirement: {ankhs_required}/{total_guardians}")

        for i, group in enumerate(guardian_groups):
            print(f"[DEBUG] Guardian group {i+1} ({len(group)} guardians, "
                  f"need {sum(len(g) for g in guardian_groups[:i+1])} ankhs):")
            for guardian in group:
                print(f"[DEBUG]   - {guardian.name}")

    # ============================================================
    # Shop randomization
    # ============================================================

    def _place_starting_shop_items(self):
        """
        C# parity: always place Weights + starting subweapon ammo into the starting shop,
        even when ShopPlacement is Original.
        """
        print("[DEBUG] Placing starting shop items (weights/ammo)")

        mw = self.multiworld

        def safe_remove(game_item_id: ItemID, name: str) -> None:
            try:
                self._remove_item_from_pool(game_item_id, name)
            except Exception:
                pass

        if self.starting_area == AreaID.VoD:
            # Always place Weights in Nebur Shop 1
            neburs_shop1 = self.locations.get(LocationID.NeburShop1)
            if neburs_shop1 and neburs_shop1.item is None:
                safe_remove(ItemID.Weights, "Weights")
                mw.push_item(neburs_shop1, create_item(self.world, "Weights"), collect=False)
                neburs_shop1.locked = True

            # Always place starting subweapon ammo in Nebur Shop 2 (if subweapon start)
            if self.starting_weapon > ItemID.Katana:
                neburs_shop2 = self.locations.get(LocationID.NeburShop2)
                if neburs_shop2 and neburs_shop2.item is None:
                    ammo_item_id = self._get_ammo_for_weapon(self.starting_weapon)
                    ammo_name = get_item_name_from_id(ammo_item_id)
                    safe_remove(ammo_item_id, ammo_name)
                    mw.push_item(neburs_shop2, create_item(self.world, ammo_name, game_id=ammo_item_id), collect=False)
                    neburs_shop2.locked = True
        else:
            # Non-VoD start: place Weights in StartingShop1
            starting_shop1 = self.locations.get(LocationID.StartingShop1)
            if starting_shop1 and starting_shop1.item is None:
                safe_remove(ItemID.Weights, "Weights")
                mw.push_item(starting_shop1, create_item(self.world, "Weights"), collect=False)
                # starting_shop1.locked = True

            # Place starting subweapon ammo in StartingShop2 (if subweapon start)
            if self.starting_weapon > ItemID.Katana:
                starting_shop2 = self.locations.get(LocationID.StartingShop2)
                if starting_shop2 and starting_shop2.item is None:
                    ammo_item_id = self._get_ammo_for_weapon(self.starting_weapon)
                    ammo_name = get_item_name_from_id(ammo_item_id)
                    safe_remove(ammo_item_id, ammo_name)
                    mw.push_item(starting_shop2, create_item(self.world, ammo_name, game_id=ammo_item_id), collect=False)
                    # starting_shop2.locked = True
        
            #starting_shop3 = self.locations.get(LocationID.StartingShop3)
            #if starting_shop3 and starting_shop3.item is None:
            #    self._remove_item_from_pool(ItemID.Weights, "Weights")
            #    weights_item = create_item(self.world, "Weights")
            #    mw.push_item(starting_shop3, weights_item, collect=False)
            #    # starting_shop3.locked = True
            #    print(f"[DEBUG] Placed Weights at Starting Shop 3")

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

        # Collect shop locations
        shop_locations = [
            loc for loc in self.locations.values()
            if loc.location_type == LocationType.Shop and not loc.locked
        ]

        if placement == self.options.shop_placement.option_random:
            hiner3 = next((l for l in shop_locations if l.game_location_id == LocationID.HinerShop3), None)
            if hiner3:
                hiner3.locked = True
        elif placement == self.options.shop_placement.option_at_least_one:
            for loc in shop_locations:
                if loc.name.endswith("3"):
                    loc.locked = True

        open_slots = [l for l in shop_locations if not l.locked and l.item is None]
        if len(open_slots) < free_slots:
            print(f"[ERROR] Not enough open shop slots: {len(open_slots)} < {free_slots}")
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
            print("[ERROR] No shop-only item ids available for randomized shops")
            return False

        # Candidate pool ids: one of each + free_slots random picks (with replacement)
        candidate_ids: List[ItemID] = list(shop_only_ids)
        for _ in range(free_slots):
            candidate_ids.append(self.rng.choice(shop_only_ids))

        self.rng.shuffle(candidate_ids)

        # Choose exactly free_slots items from the candidate pool
        chosen_ids = candidate_ids[:free_slots]

        # Create items
        chosen: List[Item] = []
        for iid in chosen_ids:
            name = get_item_name_from_id(iid)
            chosen.append(create_item(self.world, name, game_id=iid))

        print(f"[DEBUG] Randomized shops (parity): placing {len(chosen)} items into {len(open_slots)} open slots")

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

        # C# parity pricing pass
        self._adjust_shop_prices(placed_items)

        return True

    def _place_shop_items_original(self):
        """
        Place original shop items if shop_placement is Original.
        """
        placement = self.options.shop_placement.value

        if placement != self.options.shop_placement.option_original:
            print(f"[DEBUG] Shop placement is {placement}, not placing original shops")
            return

        print("[DEBUG] Placing original shop items")

        if (self.starting_area == AreaID.VoD) and (self.starting_weapon > ItemID.Katana):
            try:
                self._remove_item_from_pool(ItemID.Map1, "Map")
                print("[DEBUG] C# parity: removed Map1 because NeburShop2 is used by starting ammo")
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
                print(f"[DEBUG] {loc.name} already has {loc.item.name}, skipping")
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
                print(f"[ERROR] Failed to get name for ItemID {item_id}: {e}")
                continue

            item = create_item(self.world, item_name, game_id=item_id)

            mw.push_item(loc, item, collect=False)
            loc.locked = True

            self.shop_entries.append(ShopEntry(loc_id, item_id, price_multiplier))
            placed_items_info.append((item_name, loc.name))
            print(f"[DEBUG] Placed {item_name} (ID: {item_id}) at {loc.name}")

        # C# parity: for non-VoD starts, place Weights in StartingShop2 (melee only) and StartingShop3
        if self.starting_area != AreaID.VoD:
            if self.starting_weapon <= ItemID.Katana:
                starting_shop2 = self.locations.get(LocationID.StartingShop2)
                if starting_shop2 and starting_shop2.item is None:
                    mw.push_item(starting_shop2, create_item(self.world, "Weights"), collect=False)
                    starting_shop2.locked = True
                    print(f"[DEBUG] Placed Weights at Starting Shop 2 (melee start)")

            starting_shop3 = self.locations.get(LocationID.StartingShop3)
            if starting_shop3 and starting_shop3.item is None:
                mw.push_item(starting_shop3, create_item(self.world, "Weights"), collect=False)
                starting_shop3.locked = True
                print(f"[DEBUG] Placed Weights at Starting Shop 3")


    def _adjust_shop_prices(self, shop_items):
        """
        Assign shop prices based on which sphere the item becomes reachable in.
        mirroring the C# AdjustShopPrices() logic but halved for AP
        (players buy more in multiworld so prices are kept lower).
        C# range: multiplier 5-9  (sphere 1 = 5, sphere 5+ = 9)
        AP range:  multiplier 4-8  (scaled on total amount of spheres)
        """
        entry_index = {}
        for i, entry in enumerate(self.shop_entries):
            entry_index[entry.location_id] = i

        if not entry_index:
            return

        # Collect all spheres first so we know the total count for scaling.
        spheres = list(self.multiworld.get_spheres())
        total_spheres = max(len(spheres), 1)

        min_mult = 4
        max_mult = 8

        assigned = set()

        for sphere_idx, sphere in enumerate(spheres):
            # Linear interpolation across the full sphere range
            t = sphere_idx / (total_spheres - 1) if total_spheres > 1 else 0.0
            multiplier = round(min_mult + t * (max_mult - min_mult))

            for location in sphere:
                if location.player != self.player:
                    continue
                loc_id = getattr(location, "game_location_id", None)
                if loc_id is None or loc_id not in entry_index or loc_id in assigned:
                    continue

                item = location.item
                if item is None or item.classification != ItemClassification.progression:
                    continue

                assigned.add(loc_id)
                i = entry_index[loc_id]
                old = self.shop_entries[i]
                self.shop_entries[i] = ShopEntry(
                    location_id=old.location_id,
                    item_id=old.item_id,
                    price_multiplier=multiplier
                )

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
                    print(f"[ERROR] Missing mantra mural location id: {mural_loc_id}")
                    return False

                if loc.item is not None:
                    print(f"[ERROR] Mantra mural already filled: {loc.name} -> {loc.item.name}")
                    return False

                name = get_item_name_from_id(mantra_item_id)
                item = create_item(self.world, name, game_id=mantra_item_id)

                mw.push_item(loc, item, collect=False)
                loc.locked = True

            return True

        if placement_mode == self.options.mantra_placement.option_only_murals:
            mural_locations = get_unplaced_locations_of_type(self.locations, LocationType.Mural)

            if len(mural_locations) < len(MANTRA_ITEMS):
                print(f"[ERROR] Not enough mural locations ({len(mural_locations)}) for mantras ({len(MANTRA_ITEMS)})")
                return False

            if len(mantra_items) != len(MANTRA_ITEMS):
                print(f"[WARN] Found {len(mantra_items)} mantra items in AP pool, expected {len(MANTRA_ITEMS)}")

            self.rng.shuffle(mural_locations)
            self.rng.shuffle(mantra_items)

            if len(mantra_items) > len(mural_locations):
                print("[ERROR] More mantras to place than mural locations")
                return False

            # Place all mantras
            for loc, item in zip(mural_locations, mantra_items):
                mw.push_item(loc, item, collect=False)
                loc.locked = True

                # Remove from AP pool so it can't be placed elsewhere
                if item in mw.itempool:
                    mw.itempool.remove(item)

            return True

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
                    print(f"[WARN] Research location {loc_id} missing, skipping")
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
                    print(f"[WARN] Could not find research {research_itemid} in item pool")
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
        
            # --- SHOP & DIALOGUE HANDLING ---
            # Since you're patching the display in BepInEx, we use FakeItem01 as a
            # consistent carrier. This keeps shops decoupled from NPCMoney pools.
            if category == LocationType.Shop:
                category = LocationType.FreeStanding

            # 3. PREFERRED REWARD MATCH
            # Try to match the exact reward type (e.g., AP 30 Coins -> internal 30 Coin ID)
            pool = INTERNAL_POOL_BY_REWARD.get((category, item_id), [])
            if pool:
                return pool.pop(0)

            # 4. DYNAMIC OVERFLOW
            # If the preferred pool is empty, search all other pools in the SAME category.
            # This allows a '30 Coin' request to take a '10 Coin' or '1 Weight' internal ID.
            for (pool_cat, _), sub_pool in INTERNAL_POOL_BY_REWARD.items():
                if pool_cat == category and sub_pool:
                    return sub_pool.pop(0)

            # 5. FINAL FALLBACK
            # If the entire category distribution is exhausted, use FakeItem01.
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
            print(f"[FILL] {loc.name} <- {filler.name} class={filler.classification}")
            self.multiworld.push_item(loc, filler, collect=False)


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
            
            # Skip locations with ID >= Ratatoskr1 (253)
            if loc.game_location_id >= LocationID.Ratatoskr1:
                continue
            
            # Get the game item ID — use unique AP placeholder for items belonging to other players
            if loc.item.player != self.player:
                item_id = ap_map.get(loc.game_location_id, AP_ITEM_PLACEHOLDER)
            else:
                try:
                    item_id = get_game_item_id(loc.item)
                except KeyError:
                    print(f"[WARN] Skipping item {loc.item.name} at {loc.name} - no game ID")
                    continue
            
            # Skip logic-only items
            if item_id in LOGIC_FLAG_ITEM_IDS:
                continue

            # Skip ItemID.None_ (0) - these shouldn't be written to seed
            if item_id == ItemID.None_:
                continue
            
            # Skip shop locations (handled separately)
            if is_shop_location(loc):
                continue

            # TRANSLATE AP TRASH TO INTERNAL UNIQUE IDs HERE:
            item_id = self._get_unique_filler_id(item_id, loc)

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
            
            # Skip locations with ID >= Ratatoskr1
            if loc_id >= LocationID.Ratatoskr1:
                continue
            
            # Get item ID — use unique AP placeholder for items belonging to other players
            if loc.item.player != self.player:
                item_id = ap_map.get(loc_id, AP_ITEM_PLACEHOLDER)
            else:
                try:
                    item_id = get_game_item_id(loc.item)
                except:
                    continue
            
            # Skip ItemID.None
            if item_id == ItemID.None_:
                continue

            # TRANSLATE AP TRASH TO INTERNAL UNIQUE IDs HERE:
            item_id = self._get_unique_filler_id(item_id, loc)
            
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

        foreign_loc_ids = sorted(
            (int(loc_id) for loc_id, loc in self.locations.items()
             if loc.item is not None and loc.item.player != self.player),
        )

        self._cached_ap_placeholder_map = {
            LocationID(loc_id): AP_ITEM_PLACEHOLDER + idx + 1
            for idx, loc_id in enumerate(foreign_loc_ids)
        }
        return self._cached_ap_placeholder_map

    def get_starting_items(self) -> List[ItemID]:
        """
        Seed writer helper.
        """
        return get_starting_item_ids(self.world)

    def get_cursed_locations(self) -> List[LocationID]:
        return self.cursed_locations

    def get_entrance_pairs(self) -> List[Tuple[int, int]]:
        """
        Returns entrance pairs for seed writing.
        Converts ExitID enum values to integers.
        """
        result = []
        for pair in self.entrance_pairs:
            result.append((
                int(pair.from_exit),  # Convert ExitID to int
                int(pair.to_exit)     # Convert ExitID to int
            ))
        return result

    def get_soul_gate_pairs(self) -> List[Tuple[int, int, int]]:
        """
        Returns soul gate pairs for seed writing.
        Converts ExitID enum values to integers.
        """
        result = []
        for pair in self.soul_gate_pairs:
            result.append((
                int(pair.gate1),      # Convert ExitID to int
                int(pair.gate2),      # Convert ExitID to int
                pair.soul_amount      # Already an int
            ))
        return result