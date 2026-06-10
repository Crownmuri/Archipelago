from __future__ import annotations

import json
import importlib.resources as resources
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set

from BaseClasses import Location

from .ids import LocationID, AreaID, BASE_LOCATION_ID, AP_LOCATION_NAMES
from .logic.logic_tree import LogicTree
from .logic.logic_tokens import LogicTokeniser
from .logic.player_state import PlayerStateAdapter


# ============================================================
# LocationType (exact C# parity)
# ============================================================

class LocationType(Enum):
    Chest = "Chest"
    FreeStanding = "FreeStanding"
    Shop = "Shop"
    Dialogue = "Dialogue"
    Mural = "Mural"
    Pot = "Pot"
    Miniboss = "Miniboss"
    Guardian = "Guardian"
    FinalBoss = "FinalBoss"
    Puzzle = "Puzzle"
    Dissonance = "Dissonance"
    Fairy = "Fairy"
    Glossary = "Glossary"

# ============================================================
# JSON-backed definition (equivalent to JsonLocation + ctor)
# ============================================================

@dataclass
class LM2LocationDef:
    name: str
    game_id: LocationID
    location_type: LocationType
    logic: str
    tricky_logic: Optional[str]
    minimal_logic: Optional[str]
    parent_area: AreaID
    ap_id: int


# ============================================================
# Load World.json locations
# ============================================================

def _location_name_to_id(name: str) -> LocationID:
    """Convert location name to LocationID enum value."""
    if name in AP_LOCATION_NAMES:
        return AP_LOCATION_NAMES[name]
    key = name.replace(" ", "").replace("-", "")
    try:
        return LocationID[key]
    except KeyError:
        raise ValueError(f"Unknown LocationID: {key}")


def _area_string_to_id(area_str: str) -> AreaID:
    """Convert area string ID to AreaID enum value."""
    try:
        return AreaID[area_str]
    except KeyError:
        raise ValueError(f"Unknown AreaID: {area_str}")


def _load_locations() -> Dict[LocationID, LM2LocationDef]:
    """Load all locations from World.json."""
    with resources.files(__package__ + ".data").joinpath("World.json").open(
        "r", encoding="utf-8"
    ) as f:
        raw = json.load(f)

    locations: Dict[LocationID, LM2LocationDef] = {}

    for area in raw:
        parent_area_str = area["ID"]
        parent_area = _area_string_to_id(parent_area_str)

        for loc in area.get("Locations", []):
            name = loc["Name"]
            
            # Parse location ID from name (remove whitespace)
            loc_id = _location_name_to_id(name)
            
            # Parse location type
            try:
                loc_type = LocationType(loc["LocationType"])
            except (KeyError, ValueError):
                # Default to Chest if not specified or invalid
                loc_type = LocationType.Chest
            
            # Calculate AP ID
            ap_id = BASE_LOCATION_ID + loc_id.value
            
            # Create location definition
            loc_def = LM2LocationDef(
                name=name,
                game_id=loc_id,
                location_type=loc_type,
                logic=loc.get("Logic", "True"),
                tricky_logic=loc.get("TrickyLogic"),
                minimal_logic=loc.get("HardLogic"),
                parent_area=parent_area,
                ap_id=ap_id,
            )

            locations[loc_id] = loc_def

    return locations


# Global location definitions
LOCATION_DEFS: Dict[LocationID, LM2LocationDef] = _load_locations()
LOCATION_DEFS_BY_NAME: Dict[str, LM2LocationDef] = {
    loc_def.name: loc_def for loc_def in LOCATION_DEFS.values()
}
LOCATION_DEFS_BY_AP_ID: Dict[int, LM2LocationDef] = {
    loc_def.ap_id: loc_def for loc_def in LOCATION_DEFS.values()
}
AP_LOCATION_DEFS = {loc_id: display for display, loc_id in AP_LOCATION_NAMES.items()}

# ============================================================
# Archipelago Location (C# Location parity)
# ============================================================

class LM2Location(Location):
    """
    Parity with LaMulana2Randomizer.Location

    Differences vs AP:
    - AP handles item assignment
    - We keep ItemID separately for seed writing
    """

    game = "La-Mulana 2"

    def __init__(self, world, loc_def: LM2LocationDef):
        super().__init__(
            player=world.player,
            name=AP_LOCATION_DEFS.get(loc_def.game_id, loc_def.name),
            address=loc_def.ap_id,
        )

        # Store world reference
        self.world = world

        # --- C# fields ---
        self.game_location_id: LocationID = loc_def.game_id
        self.location_type: LocationType = loc_def.location_type
        self.parent_area: AreaID = loc_def.parent_area

        self.is_locked: bool = False
        self.random_placement: bool = False

        self._base_logic_string: str = loc_def.logic
        self._tricky_logic_string: Optional[str] = loc_def.tricky_logic
        self._minimal_logic_string: Optional[str] = loc_def.minimal_logic
        self._logic_tree = None
        self._compiled_rule = None

        # Select the active logic string based on the player's logic_difficulty
        # tier (normal=0, tricky=1, minimal=2). Fallback order:
        #   minimal -> tricky -> base
        #   tricky  -> base
        level = 0
        if world is not None:
            opt = getattr(world.options, "logic_difficulty", None)
            level = int(opt.value if hasattr(opt, "value") else (opt or 0))

        self._logic_string = self._select_logic_for_level(level)

        # Store original logic string for reference (matches the chosen tier
        # so _rebuild_combined_logic re-applies on top of it).
        self._original_logic = self._logic_string

        # For additional logic strings
        self._additional_logic = []

        self.build_logic_tree()

    # --------------------------------------------------------
    # Logic (exact C# behavior)
    # --------------------------------------------------------

    def build_logic_tree(self):
        tokens = LogicTokeniser(self._logic_string).tokenise()
        self._logic_tree = LogicTree.parse(tokens)
        # Compile to a native closure so fill checks skip adapter construction
        # for the common case (Has/OrbCount/SkullCount/CanReach/etc.)
        if self.world is not None:
            self._compiled_rule = self._logic_tree.compile(self.world)
        else:
            self._compiled_rule = None


    def _select_logic_for_level(self, level: int) -> str:
        """
        Pick the logic string for the given LogicDifficulty tier.

        Fallback:
            minimal (2) -> minimal_logic, else tricky_logic, else base
            tricky  (1) -> tricky_logic,  else base
            normal  (0) -> base
        """
        if level >= 2:
            if self._minimal_logic_string:
                return self._minimal_logic_string
            if self._tricky_logic_string:
                return self._tricky_logic_string
            return self._base_logic_string
        if level == 1:
            if self._tricky_logic_string:
                return self._tricky_logic_string
            return self._base_logic_string
        return self._base_logic_string

    def apply_logic_difficulty(self, level: int):
        """
        Re-select the active logic string for the given LogicDifficulty tier
        and rebuild the logic tree. Any append_logic_string additions are
        preserved on top of the newly selected tier.
        """
        self._logic_string = self._select_logic_for_level(level)
        self._original_logic = self._logic_string
        self._rebuild_combined_logic()

    def append_logic_string(self, extra: str):
        """
        Append additional logic to the location.
        Returns True if logic was added, False if it was already present.
        """
        # Check if we're already adding this exact logic string
        if extra in self._additional_logic:
            return False
    
        # Store additional logic separately
        self._additional_logic.append(extra)
    
        # Rebuild combined logic tree
        self._rebuild_combined_logic()
        return True

    def _rebuild_combined_logic(self):
        if not self._additional_logic:
            self._logic_string = self._original_logic
        else:
            combined = f"({self._original_logic})"
            for logic in self._additional_logic:
                combined = f"({combined} {logic})"
            self._logic_string = combined

        tokens = LogicTokeniser(self._logic_string).tokenise()
        self._logic_tree = LogicTree.parse(tokens)
        if self.world is not None:
            self._compiled_rule = self._logic_tree.compile(self.world)
        else:
            self._compiled_rule = None

    # --------------------------------------------------------
    # Reachability
    # --------------------------------------------------------

    def can_access(self, state) -> bool:
        world = self.world

        if self._compiled_rule is not None:
            # Fast path: check parent-area reachability via AP's region graph
            # directly (no PlayerStateAdapter allocation).
            regions_by_area = getattr(world, 'regions_by_area_id', None)
            if regions_by_area:
                region = regions_by_area.get(self.parent_area)
                if region is not None and not state.can_reach(region, "Region", self.player):
                    return False
            return self._compiled_rule(state)

        # Slow path: full adapter (only hit when compile() returned None,
        # which shouldn't happen after construction but is kept for safety)
        lm2_state = PlayerStateAdapter(
            state, self.player, world.multiworld,
            world.multiworld.worlds[self.player].options
        )
        if lm2_state.starting_area is None:
            lm2_state.starting_area = getattr(world, 'starting_area', None)
        return self.can_access_with_adapter(lm2_state)


    def can_access_with_adapter(self, lm2_state: PlayerStateAdapter) -> bool:
        if self._compiled_rule is not None:
            return (
                lm2_state.can_reach(self.parent_area)
                and self._compiled_rule(lm2_state.state)
            )
        return (
            lm2_state.can_reach(self.parent_area)
            and self._logic_tree.evaluate(lm2_state)
        )


    def can_reach(self, state) -> bool:
        """
        Archipelago compatibility method - delegates to LM2's can_access.
        """
        return self.can_access(state)

    def can_collect(self, state) -> bool:
        if self._compiled_rule is not None:
            return self._compiled_rule(state)

        world = self.world
        lm2_state = PlayerStateAdapter(
            state, self.player, world.multiworld,
            world.multiworld.worlds[self.player].options
        )
        if lm2_state.starting_area is None:
            lm2_state.starting_area = getattr(world, 'starting_area', None)
        return self.can_collect_with_adapter(lm2_state)

    def can_collect_with_adapter(self, lm2_state: PlayerStateAdapter) -> bool:
        if self._compiled_rule is not None:
            return self._compiled_rule(lm2_state.state)
        return self._logic_tree.evaluate(lm2_state)

    # --------------------------------------------------------
    # Placement hooks (Randomiser.cs parity)
    # --------------------------------------------------------

    def place_item(self, random_placement: bool = False):
        """
        Mirrors Location.PlaceItem(Item, bool)

        AP already assigns the item object; we only track flags.
        """
        self.random_placement = random_placement

# ============================================================
# Factory
# ============================================================

def create_locations(world) -> Dict[LocationID, LM2Location]:
    """
    Create all LM2 locations for the player.
    """
    result: Dict[LocationID, LM2Location] = {}

    for loc_id, loc_def in LOCATION_DEFS.items():
        loc = LM2Location(world, loc_def)
        result[loc_id] = loc

    return result


# ============================================================
# Convenience filters (used by randomizer)
# ============================================================

def is_shop_location(loc: LM2Location) -> bool:
    """Check if location is a shop."""
    return loc.location_type == LocationType.Shop


def is_mural_location(loc: LM2Location) -> bool:
    """Check if location is a mural (for mantra placement)."""
    return loc.location_type == LocationType.Mural


def is_guardian_location(loc: LM2Location) -> bool:
    """Check if location is a guardian boss."""
    return loc.location_type == LocationType.Guardian


def is_miniboss_location(loc: LM2Location) -> bool:
    """Check if location is a miniboss."""
    return loc.location_type == LocationType.Miniboss


def is_chest_location(loc: LM2Location) -> bool:
    """Check if location is a chest."""
    return loc.location_type == LocationType.Chest


def is_pot_location(loc: LM2Location) -> bool:
    """Check if location is a pot."""
    return loc.location_type == LocationType.Pot


def is_dissonance_location(loc: LM2Location) -> bool:
    """Check if location is a dissonance check."""
    return loc.location_type == LocationType.Dissonance


def get_locations_of_type(locations: Dict[LocationID, LM2Location], 
                          loc_type: LocationType) -> list[LM2Location]:
    """Get all locations of a specific type."""
    return [loc for loc in locations.values() if loc.location_type == loc_type]


def get_unplaced_locations_of_type(locations: Dict[LocationID, LM2Location],
                                   loc_type: LocationType) -> list[LM2Location]:
    """Get all unplaced locations of a specific type."""
    return [
        loc for loc in locations.values()
        if loc.location_type == loc_type and loc.item is None and not loc.is_locked
    ]


# ============================================================
# AreaID → display name (collapses sub-areas to broad regions
# for AP location_name_groups). Areas without locations
# (Cliff, Start) are still mapped — they drop out naturally.
# ============================================================

AREA_DISPLAY_NAME: Dict[AreaID, str] = {
    AreaID.VoD: "Village of Departure",
    AreaID.VoDLadder: "Village of Departure",
    AreaID.InfernoCavern: "Inferno Cavern",
    AreaID.GateofGuidance: "Gate of Guidance",
    AreaID.GateofGuidanceLeft: "Gate of Guidance",
    AreaID.MausoleumofGiants: "Mausoleum of Giants",
    AreaID.MausoleumofGiantsRubble: "Mausoleum of Giants",
    AreaID.EndlessCorridor: "Endless Corridor",
    AreaID.GateofIllusion: "Gate of Illusion",
    AreaID.RoY: "Roots of Yggdrasil",
    AreaID.RoYTopLeft: "Roots of Yggdrasil",
    AreaID.RoYTopRight: "Roots of Yggdrasil",
    AreaID.RoYTopMiddle: "Roots of Yggdrasil",
    AreaID.RoYMiddle: "Roots of Yggdrasil",
    AreaID.RoYBottom: "Roots of Yggdrasil",
    AreaID.RoYBottomLeft: "Roots of Yggdrasil",
    AreaID.AnnwfnMain: "Annwfn",
    AreaID.AnnwfnOneWay: "Annwfn",
    AreaID.AnnwfnSG: "Annwfn",
    AreaID.AnnwfnPoison: "Annwfn",
    AreaID.AnnwfnRight: "Annwfn",
    AreaID.IBBifrost: "Immortal Battlefield",
    AreaID.IBTop: "Immortal Battlefield",
    AreaID.IBTopLeft: "Immortal Battlefield",
    AreaID.IBCetusLadder: "Immortal Battlefield",
    AreaID.IBMain: "Immortal Battlefield",
    AreaID.IBRight: "Immortal Battlefield",
    AreaID.IBBottom: "Immortal Battlefield",
    AreaID.IBLeft: "Immortal Battlefield",
    AreaID.IBLeftSG: "Immortal Battlefield",
    AreaID.IBBattery: "Immortal Battlefield",
    AreaID.IBDinosaur: "Immortal Battlefield",
    AreaID.IBMoon: "Immortal Battlefield",
    AreaID.IBLadder: "Immortal Battlefield",
    AreaID.IBBoat: "Immortal Battlefield",
    AreaID.Cavern: "Cavern",
    AreaID.Cliff: "Cliff",
    AreaID.AltarLeft: "Altar",
    AreaID.AltarRight: "Altar",
    AreaID.ITEntrance: "Icefire Treetop",
    AreaID.ITBottom: "Icefire Treetop",
    AreaID.ITSinmara: "Icefire Treetop",
    AreaID.ITLeft: "Icefire Treetop",
    AreaID.ITRight: "Icefire Treetop",
    AreaID.ITRightLeftLadder: "Icefire Treetop",
    AreaID.ITVidofnir: "Icefire Treetop",
    AreaID.DFEntrance: "Divine Fortress",
    AreaID.DFRight: "Divine Fortress",
    AreaID.DFMain: "Divine Fortress",
    AreaID.DFTop: "Divine Fortress",
    AreaID.SotFGMain: "Shrine of the Frost Giants",
    AreaID.SotFGGrail: "Shrine of the Frost Giants",
    AreaID.SotFGTop: "Shrine of the Frost Giants",
    AreaID.SotFGBalor: "Shrine of the Frost Giants",
    AreaID.SotFGBlood: "Shrine of the Frost Giants",
    AreaID.SotFGBloodTez: "Shrine of the Frost Giants",
    AreaID.SotFGLeft: "Shrine of the Frost Giants",
    AreaID.GotD: "Gate of the Dead",
    AreaID.GotDWedjet: "Gate of the Dead",
    AreaID.TSEntrance: "Takamagahara Shrine",
    AreaID.TSMain: "Takamagahara Shrine",
    AreaID.TSLeft: "Takamagahara Shrine",
    AreaID.TSNeck: "Takamagahara Shrine",
    AreaID.TSNeckEntrance: "Takamagahara Shrine",
    AreaID.TSBottom: "Takamagahara Shrine",
    AreaID.TSBlood: "Takamagahara Shrine",
    AreaID.HL: "Heaven's Labyrinth",
    AreaID.HLGate: "Heaven's Labyrinth",
    AreaID.HLSpun: "Heaven's Labyrinth",
    AreaID.HLCog: "Heaven's Labyrinth",
    AreaID.ValhallaMain: "Valhalla",
    AreaID.ValhallaTop: "Valhalla",
    AreaID.ValhallaTopRight: "Valhalla",
    AreaID.DSLMMain: "Dark Star Lord's Mausoleum",
    AreaID.DSLMTop: "Dark Star Lord's Mausoleum",
    AreaID.DSLMPyramid: "Dark Star Lord's Mausoleum",
    AreaID.Nibiru: "Nibiru",
    AreaID.ACBottom: "Ancient Chaos",
    AreaID.ACWind: "Ancient Chaos",
    AreaID.ACTablet: "Ancient Chaos",
    AreaID.ACMain: "Ancient Chaos",
    AreaID.ACBlood: "Ancient Chaos",
    AreaID.HoMTop: "Hall of Malice",
    AreaID.HoM: "Hall of Malice",
    AreaID.HoMAwoken: "Hall of Malice",
    AreaID.EPDEntrance: "Eternal Prison Doom",
    AreaID.EPDMain: "Eternal Prison Doom",
    AreaID.EPDTop: "Eternal Prison Doom",
    AreaID.EPDHel: "Eternal Prison Doom",
    AreaID.EPG: "Eternal Prison Gloom",
    AreaID.SpiralHell: "Spiral Hell",
}


# Area-display-name → tuple of alias group names. Each alias becomes a
# parallel group with the same members, so e.g. !hint_location ANN and
# !hint_location Annwfn resolve identically.
AREA_ALIASES: Dict[str, tuple[str, ...]] = {
    "Village of Departure": ("VOD",),
    "Inferno Cavern": ("IC",),
    "Gate of Guidance": ("GOG",),
    "Mausoleum of Giants": ("MOG",),
    "Endless Corridor": ("EC",),
    "Gate of Illusion": ("GOI",),
    "Roots of Yggdrasil": ("ROY",),
    "Annwfn": ("ANN",),
    "Immortal Battlefield": ("IB",),
    "Icefire Treetop": ("IT",),
    "Divine Fortress": ("DF",),
    "Shrine of the Frost Giants": ("SOTFG", "SFG"),
    "Gate of the Dead": ("GOTD",),
    "Takamagahara Shrine": ("TS",),
    "Heaven's Labyrinth": ("HL",),
    "Valhalla": ("VAL",),
    "Dark Star Lord's Mausoleum": ("DSLM",),
    "Nibiru": ("NIB",),
    "Ancient Chaos": ("AC",),
    "Hall of Malice": ("HOM",),
    "Eternal Prison Doom": ("EPD",),
    "Eternal Prison Gloom": ("EPG",),
    "Spiral Hell": ("SH",),
}


def build_location_name_groups() -> Dict[str, Set[str]]:
    """
    Build location_name_groups for AP hinting.

    Skips logic-flag locations (events, not registered as real AP locations).
    Empty groups (e.g. Cliff/Start, which have no locations) are dropped.
    """
    from .ids import LOGIC_FLAG_LOCATION_IDS

    groups: Dict[str, Set[str]] = {
        "Dissonance": set(),
        "Bosses": set(),
        "Murals": set(),
        "Shops": set(),
    }

    for loc_id, loc_def in LOCATION_DEFS.items():
        if loc_id in LOGIC_FLAG_LOCATION_IDS:
            continue

        ap_name = AP_LOCATION_DEFS.get(loc_id, loc_def.name)

        if loc_def.location_type == LocationType.Dissonance:
            groups["Dissonance"].add(ap_name)
        elif loc_def.location_type == LocationType.Guardian:
            groups["Bosses"].add(ap_name)
        elif loc_def.location_type == LocationType.Mural:
            groups["Murals"].add(ap_name)
        elif loc_def.location_type == LocationType.Shop:
            groups["Shops"].add(ap_name)

        area_name = AREA_DISPLAY_NAME.get(loc_def.parent_area)
        if area_name:
            groups.setdefault(area_name, set()).add(ap_name)

    # Player-created starting shops live outside LOCATION_DEFS but are
    # always added to location_name_to_id. Per-area assignment is skipped
    # because parent_area depends on the player's resolved starting_area.
    groups["Shops"].update({
        "[RANDO] Starting Shop 1",
        "[RANDO] Starting Shop 2",
        "[RANDO] Starting Shop 3",
    })

    # Mirror each area group under its abbreviated alias(es) so players
    # can hint with shorthand (e.g. !hint_location ANN == Annwfn).
    for full_name, aliases in AREA_ALIASES.items():
        members = groups.get(full_name)
        if not members:
            continue
        for alias in aliases:
            groups[alias] = set(members)

    return {name: members for name, members in groups.items() if members}