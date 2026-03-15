from __future__ import annotations

import os
import zipfile
from typing import Dict, List, Tuple

from BaseClasses import Region, ItemClassification, Tutorial, CollectionState
from worlds.AutoWorld import World, WebWorld
from worlds.generic.Rules import set_rule, add_rule
from Options import Accessibility

from .options import LM2Options
from .ids import ItemID, LocationID, BASE_ITEM_ID, BASE_LOCATION_ID, ITEM_MAP, GUARDIAN_ANKHS_ITEMS, LOGIC_FLAG_LOCATION_IDS
from .items import (
    create_item, build_item_pool, apply_starting_inventory,
    ITEM_DEFS, AP_FILLER, AP_FILLER_NAMES, FILLER_DISTRIBUTION
)
from .locations import (
    AreaID, create_locations, LOCATION_DEFS, LocationType,
    LOCATION_DEFS_BY_AP_ID, LOCATION_DEFS_BY_NAME, LM2LocationDef,
    AP_LOCATION_DEFS
)
from .regions import create_regions
from .rules import set_rules
from .randomizer import LM2RandomizerCore
from .seed import write_seed_file

GAME_NAME = "La-Mulana 2"


# =============================================================================
# Web World (optional, minimal)
# =============================================================================

class LaMulana2WebWorld(WebWorld):
    game = GAME_NAME
    theme = "ruins"
    tutorials = []


# =============================================================================
# Main World
# =============================================================================

class LaMulana2World(World):
    game = GAME_NAME
    web = LaMulana2WebWorld()
    options_dataclass = LM2Options
    topology_present = True

    # -------------------------------------------------------------------------
    # AP ID maps (pure AP-facing)
    # -------------------------------------------------------------------------

    item_name_to_id: Dict[str, int] = {
        item_def.name: item_def.ap_id
        for item_def in ITEM_DEFS
    }
    item_name_to_id.update({
        name: BASE_ITEM_ID + item_id.value
        for name, item_id in ITEM_MAP.items()
    })
    # Pin progressives to their base IDs explicitly
    item_name_to_id["Progressive Whip"]    = BASE_ITEM_ID + ItemID.Whip1.value
    item_name_to_id["Progressive Shield"]  = BASE_ITEM_ID + ItemID.Shield1.value
    item_name_to_id["Progressive Beherit"] = BASE_ITEM_ID + ItemID.ProgressiveBeherit1.value

    # Pin multi-ID same-label families to a single AP ID
    # Currently using unique labels for every item below -- not implemented.
    #item_name_to_id["Sacred Orb"] = BASE_ITEM_ID + ItemID.SacredOrb0.value
    #item_name_to_id["Ankh Jewel"] = BASE_ITEM_ID + ItemID.AnkhJewel1.value
    #item_name_to_id["Crystal Skull"] = BASE_ITEM_ID + ItemID.CrystalSkull1.value
    #item_name_to_id["Kosugi Research Papers"] = BASE_ITEM_ID + ItemID.Research1.value

    for _ankh_item_id, _ankh_specific_name in GUARDIAN_ANKHS_ITEMS.items():
        item_name_to_id[_ankh_specific_name] = BASE_ITEM_ID + _ankh_item_id.value

    # Register Coin/Weight filler items so the AP server can display their names
    for _filler_name, _filler_id in AP_FILLER:
        item_name_to_id[_filler_name] = BASE_ITEM_ID + _filler_id.value

    location_name_to_id: Dict[str, int] = {
        AP_LOCATION_DEFS.get(loc_id, loc_def.name): loc_def.ap_id
        for loc_id, loc_def in LOCATION_DEFS.items()
        if loc_id not in LOGIC_FLAG_LOCATION_IDS
    }

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def generate_early(self) -> None:
        """
        Called before any item or location creation.
        Resolve options that affect world structure.
        """
        super().generate_early()

        # Resolve starting area
        self.starting_area = self._choose_starting_area()

        # Add starting shop locations if not starting in Village
        if self.starting_area != AreaID.VoD:
            self._create_starting_shop_locations()

        # Resolve starting weapon
        self.starting_weapon = self._choose_starting_weapon()

        # Add starting weapon to precollected items
        starting_weapon_name = self._get_weapon_name(self.starting_weapon)
        if starting_weapon_name:
            self.multiworld.push_precollected(
                create_item(self, starting_weapon_name)
            )

        apply_starting_inventory(self)

    def create_regions(self) -> None:
        regions = create_regions(self)
        self.regions_by_area_id = regions
        all_locations = create_locations(self)

        included_locations = {}

        for key, loc in all_locations.items():
            if not self._should_include_location(loc):
                continue

            region = regions[loc.parent_area]
            region.locations.append(loc)
            loc.parent_region = region

            included_locations[key] = loc

        self.locations = included_locations

    def create_items(self) -> None:
        """
        Create the item pool.
        Called by AP after create_regions, before setting rules.
        """
        # Build the base item pool
        pool = build_item_pool(self)
        
        # Add items to multiworld's item pool
        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        """
        Set access rules for locations and completion condition.
        This is THE critical method that makes AP understand LM2's logic.
        """
        # First, do any special pre-placements
        self.randomizer = LM2RandomizerCore(self)
        self.randomizer.setup_preplaced_items()
        
        # Set access rules using our logic trees
        set_rules(self)

    def pre_fill(self) -> None:
        mw = self.multiworld
        player = self.player

        # Count fillable locations for this player
        locations = [
            loc for loc in mw.get_unfilled_locations(player)
            if loc.player == player
        ]

        # Count items for this player
        items = [
            item for item in mw.itempool
            if item.player == player
        ]

        missing = len(locations) - len(items)

        if missing > 0:
            from .items import build_pre_filler
            for _ in range(missing):
                mw.itempool.append(build_pre_filler(self))

    def generate_basic(self) -> None:
        """
        Called after set_rules, before AP's fill algorithm.
        This is where we can do final setup before AP fills items.
        """
        # Nothing needed here - AP will handle the fill
        pass

    def post_fill(self) -> None:
        """
        Called after AP has filled all items.
        Do any post-processing here.
        """
        # Fix filler items with proper location type 
        self.randomizer._fix_empty_locations()

    def fill_slot_data(self) -> dict:
        """
        Return data to be sent to the client.
        This is used by the game client to apply the randomization.
        """
        # Collect shop entries
        shop_entries = []
        for entry in self.randomizer.shop_entries:
            shop_entries.append({
                "location": int(entry.location_id),
                "item": int(entry.item_id),
                "price": entry.price_multiplier
            })

        return {
            "starting_area": int(self.starting_area),
            "starting_weapon": int(self.starting_weapon),
            "cursed_locations": [int(loc_id) for loc_id in self.randomizer.cursed_locations],
            "shop_entries": shop_entries,
            "entrance_pairs": self.randomizer.get_entrance_pairs(),
            "soul_gate_pairs": self.randomizer.get_soul_gate_pairs(),
            "guardian_specific_ankhs": int(self.options.guardian_specific_ankhs),
        }

    def write_spoiler(self, spoiler_handle):
        """Write spoiler log information."""
        spoiler_data = self.get_spoiler_log_data()
        
        # Write header
        spoiler_handle.write(f"\nLa-Mulana 2 Randomizer Spoiler Log\n")
        spoiler_handle.write(f"=" * 80 + "\n")
        spoiler_handle.write(f"Seed: {spoiler_data['seed']}\n")
        spoiler_handle.write(f"Player: {spoiler_data['player']}\n\n")
        
        # Write settings
        spoiler_handle.write(f"Settings:\n")
        spoiler_handle.write(f"-" * 40 + "\n")
        spoiler_handle.write(f"Starting Area: {spoiler_data['starting_area']}\n")
        spoiler_handle.write(f"Starting Weapon: {spoiler_data['starting_weapon']}\n")
        spoiler_handle.write(f"Starting Items: {', '.join(spoiler_data['starting_items']) if spoiler_data['starting_items'] else 'None'}\n\n")
        
        # Write cursed locations
        if spoiler_data['cursed_locations']:
            spoiler_handle.write(f"Cursed Locations ({len(spoiler_data['cursed_locations'])}):\n")
            spoiler_handle.write(f"-" * 40 + "\n")
            for loc in sorted(spoiler_data['cursed_locations']):
                spoiler_handle.write(f"  {loc}\n")
            spoiler_handle.write("\n")
        
        # Write entrances  
        exit_name: Dict[int, str] = {}
        for e in self.multiworld.get_entrances(self.player):
            if hasattr(e, "game_exit_id"):
                try:
                    exit_name[int(e.game_exit_id)] = e.name
                except Exception:
                    pass

        def _exit_label(x: int) -> str:
            return exit_name.get(int(x), f"Exit {int(x)}")

        # ----------------------------------------------------------------------
        # Entrances (original-rando style)
        # ----------------------------------------------------------------------
        if spoiler_data["entrances"]:
            spoiler_handle.write('Entrances:\n')
            spoiler_handle.write('-' * 40 + '\n')

            # spoiler_data["entrances"] is List[Tuple[int,int]]
            pairs = sorted(spoiler_data["entrances"], key=lambda p: (_exit_label(p[0]), _exit_label(p[1])))

            for a, b in pairs:
                spoiler_handle.write(f'  "{_exit_label(a)}": "{_exit_label(b)}"\n')
            spoiler_handle.write("\n")

        # ----------------------------------------------------------------------
        # Soul Gates (grouped by soul amount, original-rando style)
        # ----------------------------------------------------------------------
        if spoiler_data["soul_gates"]:
            spoiler_handle.write('Soul Gates:\n')
            spoiler_handle.write('-' * 40 + '\n')

            # spoiler_data["soul_gates"] is List[Tuple[int,int,int]] -> (gate1, gate2, souls)
            by_cost: Dict[int, List[Tuple[int, int]]] = {}
            for g1, g2, cost in spoiler_data["soul_gates"]:
                by_cost.setdefault(int(cost), []).append((int(g1), int(g2)))

            for cost in sorted(by_cost.keys()):
                spoiler_handle.write(f'  "{cost}":\n')
                # Print both directions like the original JSON mapping
                for g1, g2 in sorted(by_cost[cost], key=lambda p: (_exit_label(p[0]), _exit_label(p[1]))):
                    spoiler_handle.write(f'    "{_exit_label(g1)}": "{_exit_label(g2)}"\n')
                    spoiler_handle.write(f'    "{_exit_label(g2)}": "{_exit_label(g1)}"\n')
            spoiler_handle.write("\n")

        # ----------------------------------------------------------------------
        # IBMain post-endgame escape route to Cliff
        # ----------------------------------------------------------------------
        escape_line = getattr(self, 'ibmain_escape_spoiler', None)
        if escape_line:
            spoiler_handle.write('IBMain Escape Route:\n')
            spoiler_handle.write('-' * 40 + '\n')
            # Strip the "[ER] SPOILER — " prefix for the file
            clean = escape_line.replace('[ER] SPOILER — ', '').replace('[ER] SPOILER: ', '')
            spoiler_handle.write(f'  {clean}\n')
            spoiler_handle.write("\n")

        # Write all locations
        spoiler_handle.write(f"\nAll Locations:\n")
        spoiler_handle.write(f"=" * 80 + "\n")
        
        all_locations = []
        for loc in self.multiworld.get_locations(self.player):
            if loc.item and loc.item.player == self.player and hasattr(loc, 'game_location_id'):
                all_locations.append((loc.game_location_id.value, loc.name, loc.item.name))
        
        # Sort by LocationID
        all_locations.sort(key=lambda x: x[0])
        
        for _, loc_name, item_name in all_locations:
            spoiler_handle.write(f"{loc_name:40} -> {item_name}\n")

    def get_spoiler_log_data(self) -> dict:
        """Collect spoiler log data."""
        return {
            "seed": self.multiworld.seed,
            "player": self.player,
            "starting_area": self.starting_area.name if hasattr(self.starting_area, 'name') else str(self.starting_area),
            "starting_weapon": self._get_weapon_name(self.starting_weapon),
            "starting_items": [item.name for item in self.multiworld.precollected_items[self.player]],
            "cursed_locations": [loc.name for loc in self.multiworld.get_locations(self.player) if hasattr(loc, 'game_location_id') and loc.game_location_id in self.randomizer.cursed_locations],
            "entrances": self.randomizer.get_entrance_pairs(),
            "soul_gates": self.randomizer.get_soul_gate_pairs()
        }
    
    # -------------------------------------------------------------------------

    def generate_output(self, output_directory: str) -> None:
        """
        Write the LM2 seed file (per-player, Archipelago-style name).
        Always ends with .lm2r.
        """
        import os

        mw = self.multiworld
        player = self.player

        # Prefer Archipelago's standard output naming if available
        out_base = None
        get_base = getattr(mw, "get_out_file_name_base", None)
        if callable(get_base):
            try:
                out_base = get_base(player)
            except Exception:
                out_base = None

        # Fallback: construct something stable + readable
        if not out_base:
            # seed_name is what AP uses for file output naming (often "AP_<seed>..." already),
            # but if yours is plain, we prefix "AP_" for consistency.
            seed_name = getattr(mw, "seed_name", None) or str(getattr(mw, "seed", "seed"))
            try:
                player_name = mw.get_player_name(player)  # common AP helper
            except Exception:
                player_name = str(getattr(mw, "player_name", {}).get(player, f"Player{player}"))

            out_base = f"AP_{seed_name}_P{player}_{player_name}"

        # Ensure extension is exactly .lm2r
        seed_path = os.path.join(output_directory, f"{out_base}.lm2r")

        write_seed_file(
            path=seed_path,
            starting_weapon=self.randomizer.starting_weapon,
            starting_area=self.randomizer.starting_area,
            settings=self.options,
            starting_items=self.randomizer.get_starting_items(),
            item_placements=self.randomizer.get_item_placements(),
            shop_placements=self.randomizer.get_shop_placements(),
            cursed_locations=self.randomizer.get_cursed_locations(),
            entrance_pairs=self.randomizer.get_entrance_pairs(),
            soul_gate_pairs=self.randomizer.get_soul_gate_pairs(),
        )

        print(f"[LM2] Seed file written to {seed_path}")

    # =============================================================================
    # Helpers
    # =============================================================================

    def _should_include_location(self, loc) -> bool:
        """Determine if a location should be included in the pool."""
        """
        from .locations import is_shop_location, is_mural_location
        
        # Skip shops if using original placement
        if is_shop_location(loc) and self.options.shop_placement.value == 0:
            return False

        if is_mural_location(loc) and self.options.mantra_placement.value == 0:
            return False
        
        # Skip research if not enabled
        if "Research" in loc.name and not self.options.random_research:
            return False
        """
        # Skip starting shops if we're starting in Village (they're in the base game)
        if self.starting_area == AreaID.VoD and "Starting Shop" in loc.name:
            return False
        
        return True

    def _create_starting_shop_locations(self):
        """Create starting shop locations if not starting in Village."""
        starting_shop_names = ["[RANDO] Starting Shop 1", "[RANDO] Starting Shop 2", "[RANDO] Starting Shop 3"]
        starting_shop_ids = [LocationID.StartingShop1, LocationID.StartingShop2, LocationID.StartingShop3]
        
        for name, loc_id in zip(starting_shop_names, starting_shop_ids):
            ap_id = BASE_LOCATION_ID + loc_id.value
            
            loc_def = LM2LocationDef(
                name=name,
                game_id=loc_id,
                location_type=LocationType.Shop,
                logic="True",
                hard_logic=None,
                parent_area=self.starting_area,
                ap_id=ap_id,
            )
            
            LOCATION_DEFS[loc_id] = loc_def
            LOCATION_DEFS_BY_NAME[name] = loc_def
            LOCATION_DEFS_BY_AP_ID[ap_id] = loc_def
            self.location_name_to_id[name] = ap_id

    def _choose_starting_area(self) -> AreaID:
        """Choose starting area based on options."""
        choices: List[AreaID] = []
        
        if self.options.start_village_of_departure:
            choices.append(AreaID.VoD)
        if self.options.start_roots_of_yggdrasil:
            choices.append(AreaID.RoY)
        if self.options.start_annwfn:
            choices.append(AreaID.AnnwfnMain)
        if self.options.start_immortal_battlefield:
            choices.append(AreaID.IBMain)
        if self.options.start_icefire_treetop:
            choices.append(AreaID.ITLeft)
        if self.options.start_divine_fortress:
            choices.append(AreaID.DFMain)
        if self.options.start_shrine_of_the_frost_giants:
            choices.append(AreaID.SotFGGrail)
        if self.options.start_takamagahara_shrine:
            choices.append(AreaID.TSLeft)
        if self.options.start_valhalla:
            choices.append(AreaID.ValhallaMain)
        if self.options.start_dark_star_lords_mausoleum:
            choices.append(AreaID.DSLMMain)
        if self.options.start_ancient_chaos:
            choices.append(AreaID.ACTablet)
        if self.options.start_hall_of_malice:
            choices.append(AreaID.HoMTop)
        
        if not choices:
            return AreaID.VoD
        
        return self.multiworld.random.choice(choices)

    # -------------------------------------------------------------------------

    def _choose_starting_weapon(self) -> ItemID:
        """Choose starting weapon based on options."""
        choices: List[ItemID] = []
        
        if self.options.start_leather_whip:
            choices.append(ItemID.Whip1)
        if self.options.start_knife:
            choices.append(ItemID.Knife)
        if self.options.start_rapier:
            choices.append(ItemID.Rapier)
        if self.options.start_axe:
            choices.append(ItemID.Axe)
        if self.options.start_katana:
            choices.append(ItemID.Katana)
        if self.options.start_shuriken:
            choices.append(ItemID.Shuriken)
        if self.options.start_rolling_shuriken:
            choices.append(ItemID.RollingShuriken)
        if self.options.start_earth_spear:
            choices.append(ItemID.EarthSpear)
        if self.options.start_flare:
            choices.append(ItemID.Flare)
        if self.options.start_caltrops:
            choices.append(ItemID.Caltrops)
        if self.options.start_chakram:
            choices.append(ItemID.Chakram)
        if self.options.start_bomb:
            choices.append(ItemID.Bomb)
        if self.options.start_pistol:
            choices.append(ItemID.Pistol)
        if self.options.start_claydoll_suit:
            choices.append(ItemID.ClaydollSuit)
        
        if not choices:
            return ItemID.Whip1
        
        return self.multiworld.random.choice(choices)

    def _get_weapon_name(self, weapon_id: ItemID) -> str:
        """Get the name of a weapon from its ID."""
        weapon_map = {
            ItemID.Whip1: "Progressive Whip",
            ItemID.Knife: "Knife",
            ItemID.Rapier: "Rapier",
            ItemID.Axe: "Axe",
            ItemID.Katana: "Katana",
            ItemID.Shuriken: "Shuriken",
            ItemID.RollingShuriken: "Rolling Shuriken",
            ItemID.EarthSpear: "Earth Spear",
            ItemID.Flare: "Flare",
            ItemID.Caltrops: "Caltrops",
            ItemID.Chakram: "Chakram",
            ItemID.Bomb: "Bomb",
            ItemID.Pistol: "Pistol",
            ItemID.ClaydollSuit: "Claydoll Suit",
        }
        return weapon_map.get(weapon_id, "Progressive Whip")

    def get_filler_item_name(self) -> str:
        """
        Called by AP when it needs to generate a filler item for this world.
        We use our FILLER_DISTRIBUTION to ensure that even 'extra' items 
        added by the server follow our intended rarity (e.g. rare 100 Coins).
        """
        # Create a weighted list of names to pick from
        # e.g. ["1 Coin", "1 Coin", "10 Coins", "10 Coins", "10 Coins" ...]
        weights = [name for name, count in FILLER_DISTRIBUTION for _ in range(count)]
        
        # self.random is the seed-synced random provided by AutoWorld
        return self.random.choice(weights)