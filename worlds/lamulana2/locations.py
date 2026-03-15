from __future__ import annotations

import json
import importlib.resources as resources
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

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
    Miniboss = "Miniboss"
    Guardian = "Guardian"
    FinalBoss = "FinalBoss"
    Puzzle = "Puzzle"
    Dissonance = "Dissonance"
    Fairy = "Fairy"

# ============================================================
# JSON-backed definition (equivalent to JsonLocation + ctor)
# ============================================================

@dataclass
class LM2LocationDef:
    name: str
    game_id: LocationID
    location_type: LocationType
    logic: str
    hard_logic: Optional[str]
    parent_area: AreaID
    ap_id: int


# ============================================================
# Load World.json locations
# ============================================================

def _location_name_to_id(name: str) -> LocationID:
    """Convert location name to LocationID enum value."""
    key = name.replace(" ", "")
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
                hard_logic=loc.get("HardLogic"),
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

        self._logic_string: str = loc_def.logic
        self._hard_logic_string: Optional[str] = loc_def.hard_logic
        self._logic_tree = None
        self._compiled_rule = None
        
        # Store original logic string for reference
        self._original_logic = loc_def.logic
        
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


    def use_hard_logic(self):
        """
        Equivalent to C# UseHardLogic()
        """
        if self._hard_logic_string:
            self._logic_string = self._hard_logic_string
            self.build_logic_tree()

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