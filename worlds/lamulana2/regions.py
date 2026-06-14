from __future__ import annotations

import json
import importlib.resources as resources
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


from BaseClasses import Region, Entrance

from . import _log
from .ids import AreaID, ExitID
from .logic.logic_tree import LogicTree
from .logic.logic_tokens import LogicTokeniser
from .logic.player_state import PlayerStateAdapter


# ============================================================
# ExitType (parity with C# enum)
# ============================================================

class ExitType(Enum):
    LeftDoor = "LeftDoor"
    RightDoor = "RightDoor"
    DownLadder = "DownLadder"
    UpLadder = "UpLadder"
    Gate = "Gate"
    SoulGate = "SoulGate"
    OneWay = "OneWay"
    Pyramid = "Pyramid"
    Corridor = "Corridor"
    Internal = "Internal"
    PrisonExit = "PrisonExit"
    PrisonGate = "PrisonGate"
    Start = "Start"
    Elevator = "Elevator"
    Altar = "Altar"
    SpiralGate = "SpiralGate"


# ============================================================
# JSON-backed area / exit definitions
# ============================================================

@dataclass
class LM2ExitDef:
    name: str
    game_id: ExitID | None
    parent_area: AreaID
    connecting_area: AreaID
    logic: str
    tricky_logic: Optional[str]
    minimal_logic: Optional[str]
    exit_type: ExitType

@dataclass
class LM2AreaDef:
    game_id: AreaID                
    name: str
    is_backside: bool
    exits: List[LM2ExitDef]

# ============================================================
# Helper function
# ============================================================

def _area_string_to_id(area_str: str) -> AreaID:
    """Convert area string ID to AreaID enum value."""
    try:
        return AreaID[area_str]
    except KeyError:
        raise ValueError(f"Unknown AreaID: {area_str}")


# ============================================================
# Load World.json areas + exits
# ============================================================

def _load_areas() -> Dict[AreaID, LM2AreaDef]:  
    with resources.files(__package__ + ".data").joinpath("World.json").open(
        "r", encoding="utf-8"
    ) as f:
        raw = json.load(f)

    areas: Dict[AreaID, LM2AreaDef] = {}  

    for area in raw:
        area_id_str = area["ID"]
        area_id = _area_string_to_id(area_id_str) 

        exits: List[LM2ExitDef] = []

        for ex in area.get("Exits", []):
            connecting_area_str = ex["ConnectingAreaID"]
            connecting_area = _area_string_to_id(connecting_area_str)
            
            # Convert game_id string to ExitID enum if it exists
            game_id_str = ex.get("ID")
            if game_id_str:
                game_id = ExitID[game_id_str]  # Convert string to ExitID enum
            else:
                game_id = None
            
            exits.append(
                LM2ExitDef(
                    name=ex.get("Name") or f"{area_id_str}->{connecting_area_str}",
                    game_id=game_id,  # Now an ExitID enum or None
                    parent_area=area_id,
                    connecting_area=connecting_area,
                    logic=ex.get("Logic", "True"),
                    tricky_logic=ex.get("TrickyLogic"),
                    minimal_logic=ex.get("HardLogic"),
                    exit_type=ExitType(ex["ConnectionType"]),
                )
            )

        areas[area_id] = LM2AreaDef( 
            game_id=area_id,
            name=area["Name"],
            is_backside=area.get("IsBackside", False),
            exits=exits,
        )

    return areas

AREA_DEFS: Dict[AreaID, LM2AreaDef] = _load_areas() 

# ============================================================
# Archipelago Entrance Wrapper
# ============================================================

class LM2Entrance(Entrance):
    """
    Archipelago Entrance with LM2 logic support.

    IMPORTANT:
    - self.game_exit_id is the LM2 ExitID (seed writer)
    """

    def __init__(self, player, name, parent_region, exit_def):
        super().__init__(player, name, parent_region)

        # Convert string game_id to ExitID enum
        if exit_def.game_id:
            self.game_exit_id = exit_def.game_id or ExitID.None_
        else:
            self.game_exit_id = ExitID.None_

        self.exit_type = exit_def.exit_type
        self.parent_area = exit_def.parent_area
        self.connecting_area = exit_def.connecting_area

        # Resolve player's logic_difficulty tier so we can pick the right
        # logic string up front. Same fallback as LM2Location.
        try:
            world = parent_region.multiworld.worlds[player]
        except Exception:
            world = None

        level = 0
        if world is not None:
            opt = getattr(world.options, "logic_difficulty", None)
            level = int(opt.value if hasattr(opt, "value") else (opt or 0))

        if level >= 2 and exit_def.minimal_logic:
            chosen_logic = exit_def.minimal_logic
        elif level >= 2 and exit_def.tricky_logic:
            chosen_logic = exit_def.tricky_logic
        elif level == 1 and exit_def.tricky_logic:
            chosen_logic = exit_def.tricky_logic
        else:
            chosen_logic = exit_def.logic

        self._original_logic = chosen_logic

        tokens = LogicTokeniser(chosen_logic).tokenise()
        self._logic_tree = LogicTree.parse(tokens)

        # For soul gate logic
        self._additional_logic = []

        # For checking state to prevent infinite recursion
        self.checking = False

        if world is not None:
            try:
                self._compiled_rule = self._logic_tree.compile(world)
                self._world = world      # cache for recompilation in append_logic_string
            except Exception:
                self._compiled_rule = None
                self._world = None
        else:
            self._compiled_rule = None
            self._world = None

    def disconnect(self) -> None:
        """Disconnect this entrance from its current region."""
        # In Archipelago, set connected_region to None
        self.connected_region = None

    def append_logic_string(self, logic_string: str) -> None:
        self._original_logic = f"({self._original_logic}) {logic_string}"

        tokens = LogicTokeniser(self._original_logic).tokenise()
        self._logic_tree = LogicTree.parse(tokens)

        if self._world is not None:
            self._compiled_rule = self._logic_tree.compile(self._world)
        else:
            self._compiled_rule = None
    
    def can_access(self, state) -> bool:
        if self._compiled_rule is not None:
            # Fast path: parent-area check via AP region graph, then compiled rule.
            world = self._world
            if world is not None:
                regions_by_area = getattr(world, 'regions_by_area_id', None)
                if regions_by_area:
                    region = regions_by_area.get(self.parent_area)
                    if region is not None and not state.can_reach(region, "Region", self.player):
                        return False
            return self._compiled_rule(state)

        # Slow path
        lm2_state = PlayerStateAdapter(
            state,
            self.player,
            self.parent_region.multiworld,
            self.parent_region.multiworld.worlds[self.player].options
        )
        if lm2_state.starting_area is None:
            world = self.parent_region.multiworld.worlds[self.player]
            lm2_state.starting_area = getattr(world, 'starting_area', None)
        return self.can_access_with_adapter(lm2_state)

    def can_access_with_adapter(self, lm2_state) -> bool:
        if self._compiled_rule is not None:
            return (
                lm2_state.can_reach(self.parent_area)
                and self._compiled_rule(lm2_state.state)
            )
        return (
            lm2_state.can_reach(self.parent_area)
            and self._logic_tree.evaluate(lm2_state)
        )


# ============================================================
# ER helper functions
# ============================================================

def _shuffleable_exits(world) -> list:
    """
    Return all LM2Entrance objects that should be shuffled given current options.

    This is the single source of truth for which exits enter the ER pool.
    Exits with logic='False' are structurally disabled and never shuffled.
    """
    opts = world.options
    shuffle_types: set = set()

    if opts.full_random_entrances:
        shuffle_types = {
            ExitType.LeftDoor, ExitType.RightDoor,
            ExitType.UpLadder, ExitType.DownLadder,
            ExitType.Gate,
        }
        if opts.unique_transitions:
            shuffle_types |= {ExitType.OneWay, ExitType.Pyramid,
                               ExitType.Start, ExitType.Altar}
    else:
        if opts.horizontal_entrances:
            shuffle_types |= {ExitType.LeftDoor, ExitType.RightDoor}
        if opts.vertical_entrances:
            shuffle_types |= {ExitType.UpLadder, ExitType.DownLadder}
        if opts.gate_entrances:
            shuffle_types.add(ExitType.Gate)
        if opts.unique_transitions:
            shuffle_types |= {ExitType.OneWay, ExitType.Pyramid,
                               ExitType.Start, ExitType.Altar}

    from .entrances import INCLUDE_DESPITE_FALSE, DLC_EXIT_IDS

    include_dlc = bool(getattr(opts, "include_dlc_entrances", False))

    result = []
    for region in world.multiworld.get_regions(world.player):
        for exit_ in region.exits:
            if not isinstance(exit_, LM2Entrance):
                continue
            if exit_.exit_type not in shuffle_types:
                continue
            # DLC exits only enter the ER pool when the player opts in (owns the DLC).
            if not include_dlc and exit_.game_exit_id in DLC_EXIT_IDS:
                continue
            logic = (exit_._original_logic or '').strip().lower()
            # Skip logic=False exits UNLESS they are in INCLUDE_DESPITE_FALSE.
            # Some exits are False in vanilla because they are one-directional
            # in the base game, but the C# randomizer still shuffles them as
            # normal two-way exits.  In ER, when paired with a new partner,
            # the player can traverse them in the new direction.
            if logic == 'false' and exit_.game_exit_id not in INCLUDE_DESPITE_FALSE:
                continue
            result.append(exit_)
    return result


# ============================================================
# Region creation
# ============================================================

def create_regions(world):
    """
    Create all LM2 regions and vanilla exits.

    Called from World.create_regions().
    """
    regions: Dict[AreaID, Region] = {}  

    # --- Create regions ---
    for area_id, area_def in AREA_DEFS.items():
        region = Region(
            name=area_def.name,
            player=world.player,
            multiworld=world.multiworld,
        )
        region.game_area_id = area_id  
        regions[area_id] = region  
        world.multiworld.regions.append(region)

    # --- Create exits ---
    for area_id, area_def in AREA_DEFS.items():
        parent_region = regions[area_id]

        for exit_def in area_def.exits:
            entrance = LM2Entrance(
                player=world.player,
                name=exit_def.name,
                parent_region=parent_region,
                exit_def=exit_def,
            )
            parent_region.exits.append(entrance)

            entrance.access_rule = entrance.can_access

            entrance.connect(regions[exit_def.connecting_area])

    # =======================================================
    # FIX: Create and Connect the "Menu" Region
    # =======================================================
    
    # 1. Create the Menu region
    menu_region = Region("Menu", world.player, world.multiworld)
    world.multiworld.regions.append(menu_region)

    # 2. Create the "Start Game" entrance
    start_entrance = Entrance(world.player, "Start Game", menu_region)
    menu_region.exits.append(start_entrance)

    # 3. Connect Menu -> Your Starting Area
    # world.starting_area was set in generate_early (AreaID enum)
    start_node = regions[world.starting_area]
    start_entrance.connect(start_node)

    return regions