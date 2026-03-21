from __future__ import annotations

import json
import importlib.resources as resources
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Dict, List, Optional


from BaseClasses import Region, Entrance

from .ids import AreaID, ExitID
from .logic.logic_tree import LogicTree
from .logic.logic_tokens import LogicTokeniser
from .logic.player_state import PlayerStateAdapter

try:
    from entrance_rando import randomize_entrances as _randomize_entrances_fn
    _ER_AVAILABLE = True
except ImportError:
    _ER_AVAILABLE = False
    _randomize_entrances_fn = None

# EntranceType lives in BaseClasses (not entrance_rando).
try:
    from BaseClasses import EntranceType
    _ER_TWO_WAY = EntranceType.TWO_WAY
    _ER_ONE_WAY  = EntranceType.ONE_WAY
except (ImportError, AttributeError):
    # Very old AP builds without EntranceType — use integer fallback.
    # TWO_WAY=0, ONE_WAY=1 matches the enum ordering in all known versions.
    _ER_TWO_WAY = 0
    _ER_ONE_WAY  = 1


# ============================================================
# ER grouping (controls which exit types can pair with which)
# ============================================================

class LM2ERGroup(IntEnum):
    HORIZONTAL = 0   # LeftDoor + RightDoor combined — any horiz exits pair freely
    VERTICAL   = 1   # UpLadder + DownLadder combined — any vert exits pair freely
    GATE       = 2
    UNIQUE     = 3   # OneWay, Pyramid, Start, Altar

    # Keep direction aliases for documentation clarity
    LEFT_DOOR   = 0
    RIGHT_DOOR  = 0
    UP_LADDER   = 1
    DOWN_LADDER = 1


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
        self._original_logic = exit_def.logic
        
        tokens = LogicTokeniser(exit_def.logic).tokenise()
        self._logic_tree = LogicTree.parse(tokens)
        
        # For soul gate logic
        self._additional_logic = []
        
        # For checking state to prevent infinite recursion
        self.checking = False

        try:
            world = parent_region.multiworld.worlds[player]
            self._compiled_rule = self._logic_tree.compile(world)
            self._world = world          # cache for recompilation in append_logic_string
        except Exception:
            self._compiled_rule = None
            self._world = None

        # ── AP Generic ER attributes ──────────────────────────────────────
        # These are read by entrance_rando.randomize_entrances.
        # randomization_type is set later in disconnect_shuffleable_exits
        # (we cannot set it here because we do not know option state yet).
        # Default to None; the ER infrastructure ignores entrances whose
        # randomization_type is None when building the candidate pool.
        if _ER_AVAILABLE:
            self.randomization_type = None   # set by disconnect_shuffleable_exits
            self.randomization_group = _exit_type_to_er_group(exit_def.exit_type)
        # ─────────────────────────────────────────────────────────────────
    
    def disconnect(self) -> None:
        """Disconnect this entrance from its current region."""
        # In Archipelago, set connected_region to None
        self.connected_region = None

    # ── AP Generic ER constraint hooks ────────────────────────────────────

    def can_connect_to(self, target, dead_end: bool, er_state) -> bool:
        """
        Hard structural constraints for AP Generic ER.

        Signature matches entrance_rando.py:
          can_connect_to(self, target_entrance, dead_end, er_state)

        These are the same rules the old EntranceRandomizer enforced,
        now expressed as per-entrance predicates so entrance_rando can
        apply them during construction rather than in a post-hoc check.
        """
        src = self.game_exit_id
        tgt_id = _er_target_exit_id(target)

        # fP00Left must not self-loop with fP00Right (Cavern)
        if src == ExitID.fP00Left and tgt_id == ExitID.fP00Right:
            return False
        if src == ExitID.fP00Right and tgt_id == ExitID.fP00Left:
            return False

        # fP01Left (altar) must not self-loop with fP01Right
        if src == ExitID.fP01Left and tgt_id == ExitID.fP01Right:
            return False
        if src == ExitID.fP01Right and tgt_id == ExitID.fP01Left:
            return False

        # fP02Left (Cliff) must not connect to fL08Right (inaccessible)
        if src == ExitID.fP02Left and tgt_id == ExitID.fL08Right:
            return False

        # fL11GateN (Gate of Illusion north) must not loop with fL11GateY0
        if src == ExitID.fL11GateN and tgt_id == ExitID.fL11GateY0:
            return False
        if src == ExitID.fL11GateY0 and tgt_id == ExitID.fL11GateN:
            return False

        # One-way downs must not connect to fL05Up (both inaccessible —
        # creates a permanently unreachable two-exit island).
        if src in {ExitID.f02Down, ExitID.f03Down2} and tgt_id == ExitID.fL05Up:
            return False

        return super().can_connect_to(target, dead_end, er_state)

    def is_valid_source_transition(self, er_state) -> bool:
        """
        Exclude exits whose vanilla logic is 'False' — these are permanently
        disabled and should never be randomized sources.
        """
        logic = (self._original_logic or '').strip().lower()
        if logic == 'false':
            return False
        return super().is_valid_source_transition(er_state)
    
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

def _exit_type_to_er_group(exit_type: ExitType) -> int:
    """Map an ExitType to an LM2ERGroup integer for AP Generic ER grouping.

    LeftDoor and RightDoor both map to HORIZONTAL (same group) so that any
    horizontal exit can pair with any other horizontal exit's ER target.
    This is necessary because after filtering logic=False exits the counts
    of left-doors and right-doors may not be equal (e.g. fP01Left is False
    but fP01Right is True), and strict LEFT↔RIGHT matching would leave one
    exit stranded with no valid target.

    The same logic applies to UpLadder/DownLadder → VERTICAL.
    """
    _MAP = {
        ExitType.LeftDoor:   LM2ERGroup.HORIZONTAL,
        ExitType.RightDoor:  LM2ERGroup.HORIZONTAL,
        ExitType.UpLadder:   LM2ERGroup.VERTICAL,
        ExitType.DownLadder: LM2ERGroup.VERTICAL,
        ExitType.Gate:       LM2ERGroup.GATE,
        ExitType.OneWay:     LM2ERGroup.UNIQUE,
        ExitType.Pyramid:    LM2ERGroup.UNIQUE,
        ExitType.Start:      LM2ERGroup.UNIQUE,
        ExitType.Altar:      LM2ERGroup.UNIQUE,
    }
    return int(_MAP.get(exit_type, LM2ERGroup.UNIQUE))


def _er_target_exit_id(target) -> 'ExitID':
    """
    Resolve an ER target entrance back to the ExitID of the source exit.

    In coupled mode, AP Generic ER creates ER targets whose name matches
    the source exit they were split from.  We stored the ExitID on the
    source LM2Entrance; the ER target's connected_region holds the old
    vanilla target region, and ER targets' own name == source exit name.
    We search the connected_region's exits for the matching name to get
    the ExitID.  If target is itself an LM2Entrance, use it directly.
    """
    # Fast path: target already has game_exit_id (it's a LM2Entrance)
    if hasattr(target, 'game_exit_id'):
        return target.game_exit_id
    # ER targets have connected_region = the old vanilla target region.
    # The matching source exit in that region carries the ExitID.
    if target.connected_region is not None:
        for exit_ in target.connected_region.exits:
            if exit_.name == target.name and hasattr(exit_, 'game_exit_id'):
                return exit_.game_exit_id
    # Also check parent_region (in case the target is stored differently)
    if target.parent_region is not None:
        for exit_ in target.parent_region.exits:
            if exit_.name == target.name and hasattr(exit_, 'game_exit_id'):
                return exit_.game_exit_id
    # Last resort: return a sentinel that matches nothing
    return ExitID.None_


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

    from .entrances import INCLUDE_DESPITE_FALSE

    result = []
    for region in world.multiworld.get_regions(world.player):
        for exit_ in region.exits:
            if not isinstance(exit_, LM2Entrance):
                continue
            if exit_.exit_type not in shuffle_types:
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


def disconnect_shuffleable_exits(world) -> None:
    """
    Prepare exits for AP Generic ER using AP's own
    disconnect_entrance_for_randomization utility.

    Coupled TWO_WAY mode requires even counts per group -- AP ER cannot
    self-pair an exit with its own ER target (coupled connect() would
    create a self-loop, which it explicitly rejects).

    If filtering (logic=False removal) leaves an odd count in any group,
    the last exit in that group is left in vanilla connection so the
    remainder is always even.

    ONE_WAY exits are excluded from count-parity checks since AP ER
    handles them independently from TWO_WAY exits.
    """
    if not _ER_AVAILABLE:
        raise RuntimeError(
            "entrance_rando.py not found.  "
            "Ensure your AP installation includes entrance_rando.py at the root."
        )

    from entrance_rando import disconnect_entrance_for_randomization
    from .entrances import ONE_WAY_EXITS
    import collections

    candidates = _shuffleable_exits(world)

    # Assign randomization_type to all candidates first (needed for grouping)
    for exit_ in candidates:
        # All LM2 exits are TWO_WAY in ER — even vanilla one-directional
        # transitions are shuffled as coupled two-way pairs by the C# randomizer.
        # ONE_WAY_EXITS is kept empty; this check is a no-op but preserved
        # for future use.
        if exit_.game_exit_id in ONE_WAY_EXITS:
            exit_.randomization_type = _ER_ONE_WAY
        else:
            exit_.randomization_type = _ER_TWO_WAY

    # Count TWO_WAY exits per group. If a group has odd count, drop the last
    # (least-important) exit from that group so the count is even, leaving
    # it in its vanilla connection.  ONE_WAY exits are not affected since
    # they are not subject to the coupled pairing constraint.
    two_way_by_group: dict = collections.defaultdict(list)
    one_way_exits: list = []
    for exit_ in candidates:
        if exit_.randomization_type == _ER_ONE_WAY:
            one_way_exits.append(exit_)
        else:
            two_way_by_group[exit_.randomization_group].append(exit_)

    # Exits whose vanilla partners were ONE_WAY (filtered out).
    # These are "orphaned" in the two-way pool — prefer dropping them first
    # when a group has odd count, since their vanilla connection is already
    # non-functional anyway.
    from .entrances import ONE_WAY_EXITS
    orphaned_exits = {
        ExitID.f03Up,   # vanilla partner f02Down is ONE_WAY (solid floor drop)
        ExitID.f04Up3,  # vanilla partner f03Down2 is ONE_WAY (solid floor drop)
        ExitID.f01Down, # vanilla partner fL05Up is ONE_WAY (spawns in air)
    }

    to_disconnect: list = list(one_way_exits)
    for group, exits in two_way_by_group.items():
        if len(exits) % 2 != 0:
            # Prefer dropping orphaned exits (vanilla partner was ONE_WAY/excluded),
            # then inaccessible exits, then any last exit as fallback.
            orphaned = [e for e in exits if e.game_exit_id in orphaned_exits]
            inaccessible = [e for e in exits if is_inaccessible_exit(e.game_exit_id)
                            and e not in orphaned]
            dropped = (orphaned[-1] if orphaned else
                       inaccessible[-1] if inaccessible else exits[-1])
            exits.remove(dropped)
            print(f"[ER] Group {group}: odd count, leaving '{dropped.name}' vanilla")
        to_disconnect.extend(exits)

    for exit_ in to_disconnect:
        if exit_.randomization_type == _ER_ONE_WAY:
            disconnect_entrance_for_randomization(
                exit_,
                one_way_target_name=f"{exit_.name} [target]"
            )
        else:
            disconnect_entrance_for_randomization(exit_)


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



# ============================================================
# Convenience filters (parity with C# flags)
# ============================================================

def is_dead_end_exit(exit_id: ExitID) -> bool:
    return exit_id in {
        ExitID.fStart,
        ExitID.fL05Up,
        ExitID.fL08Right,
        ExitID.fLGate,
        ExitID.f00Down,
        ExitID.f00GateYA,
        ExitID.f01Down,
        ExitID.f03Down1,
        ExitID.f03Down2,
        ExitID.f03Down3,
        ExitID.f04Up3,
        ExitID.f06GateP0,
        ExitID.f06_2GateP0,
        ExitID.f09In,
        ExitID.f09GateP0,
        ExitID.f11Pyramid,
        ExitID.f12GateP0,
        ExitID.f13GateP0,
        ExitID.fNibiru,
        ExitID.fP01Right,
    }


def is_one_way_exit(exit_id: ExitID) -> bool:
    return exit_id in {
        ExitID.fL05Up,
        ExitID.f02Down,
        ExitID.f03Down2,
        ExitID.f03In,
        ExitID.f09In,
    }


def is_inaccessible_exit(exit_id: ExitID) -> bool:
    return exit_id in {
        ExitID.fP02Left,
        ExitID.fStart,
        ExitID.fL05Up,
        ExitID.fL08Right,
        ExitID.f02GateYA,
        ExitID.f02Down,
        ExitID.f03In,
        ExitID.f03GateYC,
        ExitID.f03Down2,
        ExitID.f06GateP0,
        ExitID.f09In,
        ExitID.f12GateP0,
        ExitID.f13GateP0,
        ExitID.fNibiru,
        ExitID.fP01Left,
    }