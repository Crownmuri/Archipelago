from __future__ import annotations

import re
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

from .ids import ExitID, AreaID, LOGIC_FLAG_MAP
from .regions import LM2Entrance, ExitType
from .locations import LocationType
from .logic.logic_tokens import LogicTokeniser
from .logic.logic_tree import LogicTree


# ============================================================
# Data containers (seed-writer friendly)
# ============================================================

@dataclass(frozen=True)
class EntrancePair:
    from_exit: ExitID
    to_exit: ExitID

@dataclass(frozen=True)
class SoulGatePair:
    gate1: ExitID
    gate2: ExitID
    soul_amount: int


# ============================================================
# One-way exits (used by regions.py disconnect_shuffleable_exits)
# ============================================================

# All exits in LM2 are treated as TWO_WAY by the ER.  Even exits that are
# physically one-directional in vanilla (Bifrost falls, corridor drops) are
# shuffled as paired two-way transitions by the C# randomizer, because in
# ER context taking exit A connects you to B, and the reverse connection
# from B back to A is the ER-created coupled pair.
#
# ONE_WAY_EXITS is kept as an empty set for API compatibility.
ONE_WAY_EXITS: set = set()

# Exits whose vanilla logic is False but which the C# randomizer still
# includes in the shuffle pool as normal two-way exits.
# - Ladder drops (fL05Up, f02Down, f03Down2, f01Down): vanilla logic=False
#   because they are one-directional in base game, but in ER they pair
#   normally with any other exit (14 vertical exits = 7 pairs).
# - Unique transition drops (f03In = IB Bifrost Fall, f09In = HL Monster's
#   Jaw): vanilla logic=False but included in the unique transitions pool.
INCLUDE_DESPITE_FALSE = {
    # Vertical drops: logic=False in vanilla but shuffled as TWO_WAY by C# ER
    ExitID.fL05Up,
    ExitID.f02Down,
    ExitID.f03Down2,
    ExitID.f01Down,
    # Unique transition drops: logic=False in vanilla but in C# ER pool
    ExitID.f03In,    # Immortal Battlefield Bifrost Fall
    ExitID.f09In,    # Heavens Labyrinth Monster's Jaw
    ExitID.fNibiru,  # Nibiru Spaceship
    # Gate exits that are logic=False in vanilla (open after specific flags)
    # but included in the C# ER gate pool as normal exits
    ExitID.f02GateYA,   # Annwfn Right Gate (G-4)
    ExitID.f03GateYC,   # Immortal Battlefield Left Gate (A-6)
    # Horizontal/Altar exits that are logic=False in vanilla but in C# pool
    ExitID.fP01Left,    # Altar Left Door (A-1)
    ExitID.fP02Left,    # Cliff (A-1) — user changed to True in World.json;
                        # kept here as safety net for older World.json versions
}

DEAD_END_EXITS = {
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

INACCESSIBLE_EXITS = {
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

# Areas that allow the player to continue after the final boss
_ESCAPE_AREAS: frozenset = frozenset({
    AreaID.Cliff,
    AreaID.GateofGuidance,
    AreaID.MausoleumofGiants,
    AreaID.VoD,
    AreaID.VoDLadder,
    AreaID.GateofIllusion,
    AreaID.Nibiru,
})


# ============================================================
# Standalone IBMain escape log (called from connect_entrances)
# ============================================================

def _log_ibmain_escape_standalone(world) -> str:
    """
    Build the IBMain -> Cliff post-endgame escape spoiler from the live
    region graph.  Called from LaMulana2World.connect_entrances after
    structural ER has finished connecting exits.
    """
    # Build area-adjacency graph from the live AP region graph
    graph: Dict[AreaID, Set[AreaID]] = defaultdict(set)
    for region in world.multiworld.get_regions(world.player):
        if not hasattr(region, 'game_area_id'):
            continue
        for exit_ in region.exits:
            if exit_.connected_region is None:
                continue
            if not hasattr(exit_.connected_region, 'game_area_id'):
                continue
            logic = getattr(exit_, '_original_logic', '') or ''
            if 'false' in logic.lower():
                continue
            graph[region.game_area_id].add(exit_.connected_region.game_area_id)

    # Reuse the graph/log logic from SoulGateRandomizer
    sgr = SoulGateRandomizer.__new__(SoulGateRandomizer)
    sgr.world = world
    line = sgr._log_ibmain_escape_path(graph)
    world.ibmain_escape_spoiler = line
    return line


# ============================================================
# Custom Structural ER (replaces AP Generic ER)
# ============================================================
#
# Ports the C# FullRandomEntrances algorithm with:
#   - Cliff-first placement
#   - Anti-self-loop constraints (Cavern, Altar, Illusion)
#   - Inaccessible exit priority pairing
#   - One-way down-ladder constraints
#   - Full-items + events reachability validation (BFS)
#   - Automatic retry on structurally unbeatable configurations
# ============================================================

_BANNED_SELF_LOOP_PAIRS: frozenset = frozenset({
    frozenset({ExitID.fP00Left, ExitID.fP00Right}),   # Cavern L/R
    frozenset({ExitID.fP01Left, ExitID.fP01Right}),   # Altar L/R
    frozenset({ExitID.fL11GateN, ExitID.fL11GateY0}), # Gate of Illusion N/S
    frozenset({ExitID.f03In, ExitID.f03Down2}),        # IBBifrost ↔ IBMoon (no internal entry)
    frozenset({ExitID.fLLeft, ExitID.fLDown}),         # Gate of Guidance Main ↔ Ladder (self-loop)
})


def _would_self_loop(e1_id: ExitID, e2_id: ExitID) -> bool:
    """True if pairing e1<->e2 would create a trivial self-loop."""
    return frozenset({e1_id, e2_id}) in _BANNED_SELF_LOOP_PAIRS


# ── Union-Find for connectivity guarantee ─────────────────────────────

class _UnionFind:
    """Lightweight union-find / disjoint-set for area connectivity."""
    __slots__ = ('parent', 'rank')

    def __init__(self):
        self.parent: Dict = {}
        self.rank: Dict = defaultdict(int)

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path halving
            x = self.parent[x]
        return x

    def union(self, a, b) -> bool:
        """Merge a and b.  Returns True if they were in different sets."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True

    def connected(self, a, b) -> bool:
        return self.find(a) == self.find(b)

    @property
    def num_components(self) -> int:
        roots = set()
        for x in self.parent:
            roots.add(self.find(x))
        return len(roots)

    def copy(self) -> '_UnionFind':
        """Return a shallow copy of this union-find."""
        new = _UnionFind()
        new.parent = dict(self.parent)
        new.rank = defaultdict(int, self.rank)
        return new


def _exit_area(e: LM2Entrance):
    """Return the game_area_id of an exit's parent region."""
    pr = getattr(e, 'parent_region', None)
    return getattr(pr, 'game_area_id', None)


# ── Dungeon grouping ─────────────────────────────────────────────────
# Maps every sub-region AreaID to its parent dungeon.  Used to prevent
# exits from the same dungeon from wasting a pairing on each other.
# E.g. RoYTopLeft, RoYTopMiddle, RoYMiddle all → "RoY".

_DUNGEON_GROUP: Dict[AreaID, str] = {
    # Village of Departure
    AreaID.VoD: "VoD", AreaID.VoDLadder: "VoD",
    # Frontside dungeons
    AreaID.Start: "Start",
    AreaID.InfernoCavern: "InfernoCavern",
    AreaID.GateofGuidance: "GoG", AreaID.GateofGuidanceLeft: "GoG",
    AreaID.MausoleumofGiants: "MoG", AreaID.MausoleumofGiantsRubble: "MoG",
    AreaID.EndlessCorridor: "EC",
    AreaID.GateofIllusion: "GoI",
    # Roots of Yggdrasil
    AreaID.RoY: "RoY", AreaID.RoYTopLeft: "RoY", AreaID.RoYTopMiddle: "RoY",
    AreaID.RoYTopRight: "RoY", AreaID.RoYMiddle: "RoY",
    AreaID.RoYBottom: "RoY", AreaID.RoYBottomLeft: "RoY",
    # Annwfn
    AreaID.AnnwfnMain: "Annwfn", AreaID.AnnwfnOneWay: "Annwfn",
    AreaID.AnnwfnSG: "Annwfn", AreaID.AnnwfnPoison: "Annwfn",
    AreaID.AnnwfnRight: "Annwfn",
    # Immortal Battlefield
    AreaID.IBBifrost: "IB", AreaID.IBTop: "IB", AreaID.IBTopLeft: "IB",
    AreaID.IBCetusLadder: "IB", AreaID.IBMain: "IB", AreaID.IBRight: "IB",
    AreaID.IBBottom: "IB", AreaID.IBLeft: "IB", AreaID.IBLeftSG: "IB",
    AreaID.IBBattery: "IB", AreaID.IBDinosaur: "IB", AreaID.IBMoon: "IB",
    AreaID.IBLadder: "IB", AreaID.IBBoat: "IB",
    # Cavern / Cliff / Altar
    AreaID.Cavern: "Cavern", AreaID.Cliff: "Cliff",
    AreaID.AltarLeft: "Altar", AreaID.AltarRight: "Altar",
    # Icefire Treetop
    AreaID.ITEntrance: "IT", AreaID.ITBottom: "IT", AreaID.ITSinmara: "IT",
    AreaID.ITLeft: "IT", AreaID.ITRight: "IT",
    AreaID.ITRightLeftLadder: "IT", AreaID.ITVidofnir: "IT",
    # Divine Fortress
    AreaID.DFEntrance: "DF", AreaID.DFRight: "DF",
    AreaID.DFMain: "DF", AreaID.DFTop: "DF",
    # Shrine of the Frost Giants
    AreaID.SotFGMain: "SotFG", AreaID.SotFGGrail: "SotFG",
    AreaID.SotFGTop: "SotFG", AreaID.SotFGBalor: "SotFG",
    AreaID.SotFGBlood: "SotFG", AreaID.SotFGBloodTez: "SotFG",
    AreaID.SotFGLeft: "SotFG",
    # Gate of the Dead
    AreaID.GotD: "GotD", AreaID.GotDWedjet: "GotD",
    # Takamagahara Shrine
    AreaID.TSEntrance: "TS", AreaID.TSMain: "TS", AreaID.TSLeft: "TS",
    AreaID.TSNeck: "TS", AreaID.TSNeckEntrance: "TS",
    AreaID.TSBottom: "TS", AreaID.TSBlood: "TS",
    # Heaven's Labyrinth
    AreaID.HL: "HL", AreaID.HLGate: "HL", AreaID.HLSpun: "HL",
    AreaID.HLCog: "HL",
    # Valhalla
    AreaID.ValhallaMain: "Val", AreaID.ValhallaTop: "Val",
    AreaID.ValhallaTopRight: "Val",
    # Dark Star Lord's Mausoleum
    AreaID.DSLMMain: "DSLM", AreaID.DSLMTop: "DSLM",
    AreaID.DSLMPyramid: "DSLM",
    # Nibiru
    AreaID.Nibiru: "Nibiru",
    # Ancient Chaos
    AreaID.ACBottom: "AC", AreaID.ACWind: "AC",
    AreaID.ACTablet: "AC", AreaID.ACMain: "AC", AreaID.ACBlood: "AC",
    # Hall of Malice
    AreaID.HoMTop: "HoM", AreaID.HoM: "HoM", AreaID.HoMAwoken: "HoM",
    # Eternal Prison
    AreaID.EPDEntrance: "EPD", AreaID.EPDMain: "EPD",
    AreaID.EPDTop: "EPD", AreaID.EPDHel: "EPD",
    AreaID.EPG: "EPG",
    # Spiral Hell
    AreaID.SpiralHell: "SpiralHell",
}


def _exit_dungeon(e: LM2Entrance) -> Optional[str]:
    """Return the dungeon group string for an exit's parent region."""
    area_id = _exit_area(e)
    if area_id is None:
        return None
    return _DUNGEON_GROUP.get(area_id)


# When True, same-region checks use dungeon grouping (e.g. RoYTopLeft == RoYMiddle).
# When False, only exact sub-region matches are rejected (vanilla C# behaviour).
# Set by custom_structural_er based on world.options.prevent_area_loops.
_DUNGEON_LEVEL_CHECK: bool = True


def _same_dungeon(e1: LM2Entrance, e2: LM2Entrance) -> bool:
    """True if both exits should be considered 'same area' for pairing avoidance.

    When _DUNGEON_LEVEL_CHECK is True, uses dungeon grouping (all RoY sub-regions
    are treated as one dungeon).  When False, only rejects exact sub-region matches
    (closer to the original C# randomizer behaviour).
    """
    if _DUNGEON_LEVEL_CHECK:
        d1 = _exit_dungeon(e1)
        d2 = _exit_dungeon(e2)
        return d1 is not None and d1 == d2
    else:
        a1 = _exit_area(e1)
        a2 = _exit_area(e2)
        return a1 is not None and a1 == a2


def _repair_same_dungeon_pairs(
    pairings: List[Tuple[LM2Entrance, LM2Entrance]],
    rng: random.Random,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Post-processing swap pass: find same-dungeon pairs and swap partners
    with another pair to break them.

    Pool exhaustion can force a same-dungeon pairing even when the
    per-pair selection preferred different dungeons.  This repairs those
    cases after the fact by finding a swap partner among existing pairs.

    For a bad pair (A1, A2) where both are dungeon X, find another pair
    (B1, B2) where neither is dungeon X, and swap to (A1, B2) + (B1, A2).
    Only swaps if neither resulting pair is same-dungeon.
    """
    # Find indices of same-dungeon pairs
    bad = [i for i, (e1, e2) in enumerate(pairings)
           if _same_dungeon(e1, e2)]

    if not bad:
        return pairings

    result = list(pairings)
    repaired = 0

    for bad_idx in bad:
        e1, e2 = result[bad_idx]
        if not _same_dungeon(e1, e2):
            continue  # already fixed by a prior swap

        bad_dungeon = _exit_dungeon(e1)

        # Find a swap candidate: a pair where swapping fixes both
        candidates = []
        for j, (b1, b2) in enumerate(result):
            if j == bad_idx:
                continue
            # Try swap: (e1, b2) + (b1, e2)
            if (not _same_dungeon(e1, b2)
                    and not _same_dungeon(b1, e2)
                    and _exit_dungeon(b1) != bad_dungeon
                    and _exit_dungeon(b2) != bad_dungeon):
                candidates.append(j)

        if candidates:
            swap_idx = rng.choice(candidates)
            b1, b2 = result[swap_idx]
            result[bad_idx] = (e1, b2)
            result[swap_idx] = (b1, e2)
            repaired += 1

    if repaired:
        print(f"[ER] Repaired {repaired} same-dungeon pair(s) via swap")
    elif bad:
        still_bad = sum(1 for e1, e2 in result if _same_dungeon(e1, e2))
        if still_bad:
            print(f"[ER] WARNING: {still_bad} same-dungeon pair(s) could not be repaired")

    return result


def _build_base_uf(world, shuffled_exit_ids: Optional[Set] = None) -> '_UnionFind':
    """
    Build a union-find seeded with the EXISTING connectivity graph.

    Walks every exit in the world.  For exits that are NOT being shuffled
    (internal connections, corridors, elevators, soul gates, etc.), unions
    the parent area with the connected area.  This gives the pairing
    functions an accurate picture of which areas are ALREADY connected
    regardless of ER, so cross-component preference actually targets
    real structural gaps rather than wasting pairings on areas that are
    already reachable through internal routes.
    """
    uf = _UnionFind()
    _shuffled = shuffled_exit_ids or set()

    for region in world.multiworld.get_regions(world.player):
        area_id = getattr(region, 'game_area_id', None)
        if area_id is not None:
            uf.find(area_id)  # register the area

        for exit_ in region.exits:
            # Skip exits that are being shuffled — their connections will
            # be replaced, so they don't contribute to base connectivity.
            eid = getattr(exit_, 'game_exit_id', None)
            if eid is not None and eid in _shuffled:
                continue

            # Skip disconnected exits
            if exit_.connected_region is None:
                continue

            dst_area = getattr(exit_.connected_region, 'game_area_id', None)
            if area_id is not None and dst_area is not None:
                uf.union(area_id, dst_area)

    return uf


def _generate_pairings(
    candidates: List[LM2Entrance],
    rng: random.Random,
    starting_exit_ids: Optional[Set] = None,
    base_uf: Optional['_UnionFind'] = None,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Generate entrance pairings following C# FullRandomEntrances logic.
    Returns a list of (exit_A, exit_B) tuples representing coupled pairs.

    starting_exit_ids: ExitIDs of exits whose parent area is the starting area.
    When provided, implements C# ReduceDeadEndStarts:
      - Cliff (fP02Left) will not be paired with any starting-area exit.
      - One starting-area exit is pre-placed to a non-dead-end destination.

    base_uf: Pre-seeded union-find with non-shuffled connectivity.
      If None, creates an empty one (only tracks pairing connections).
    """
    pool = list(candidates)
    rng.shuffle(pool)
    pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    _starting_exit_ids: Set = starting_exit_ids or set()

    # Union-find for connectivity: start from the base graph (internal
    # connections, corridors, etc.) and extend with each pairing we create.
    uf = base_uf.copy() if base_uf is not None else _UnionFind()
    for e in pool:
        uf.find(_exit_area(e))  # register all areas

    def _find_by_id(eid: ExitID) -> Optional[LM2Entrance]:
        return next((e for e in pool if e.game_exit_id == eid), None)

    def _pair(e1: LM2Entrance, e2: LM2Entrance) -> None:
        pool.remove(e1)
        pool.remove(e2)
        pairings.append((e1, e2))
        # Update connectivity: pairing connects their parent areas
        a1, a2 = _exit_area(e1), _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    def _pick_except(exclude_fn) -> Optional[LM2Entrance]:
        """Pick a random exit from pool, rejecting those matching exclude_fn."""
        ok = [e for e in pool if not exclude_fn(e)]
        if ok:
            return rng.choice(ok)
        return rng.choice(pool) if pool else None

    def _same_area(e1: LM2Entrance, e2: LM2Entrance) -> bool:
        """True if both exits belong to the same dungeon."""
        return _same_dungeon(e1, e2)

    # ── 1. Place Cliff first ──────────────────────────────────────────────
    # Also exclude starting-area exits from being Cliff's partner (ReduceDeadEndStarts).
    # Cliff leads to a single-transition dead-end area; if the player's starting
    # exit goes to Cliff, they're immediately stranded.
    cliff = _find_by_id(ExitID.fP02Left)
    if cliff and cliff in pool:
        partner = _pick_except(lambda e: (
            e is cliff
            or e.game_exit_id in INACCESSIBLE_EXITS
            or e.game_exit_id == ExitID.fL08Right
            or _would_self_loop(ExitID.fP02Left, e.game_exit_id)
            or e.game_exit_id in _starting_exit_ids  # ReduceDeadEndStarts
            or _same_area(cliff, e)
        ))
        if partner:
            _pair(cliff, partner)

    # ── 2. Prevent Cavern self-loop ───────────────────────────────────────
    cavern_left = _find_by_id(ExitID.fP00Left)
    if cavern_left and cavern_left in pool:
        partner = _pick_except(lambda e: (
            e is cavern_left
            or e.game_exit_id == ExitID.fP00Right
            or e.game_exit_id == ExitID.fL08Right
            or _same_area(cavern_left, e)
        ))
        if partner:
            _pair(cavern_left, partner)

    # ── 3. Prevent Illusion gate self-loop ────────────────────────────────
    ill_north = _find_by_id(ExitID.fL11GateN)
    if ill_north and ill_north in pool:
        partner = _pick_except(lambda e: (
            e is ill_north
            or e.game_exit_id == ExitID.fL11GateY0
            or _same_area(ill_north, e)
        ))
        if partner:
            _pair(ill_north, partner)

    # ── 4. Prevent Altar self-loop ────────────────────────────────────────
    altar_left = _find_by_id(ExitID.fP01Left)
    if altar_left and altar_left in pool:
        partner = _pick_except(lambda e: (
            e is altar_left
            or e.game_exit_id == ExitID.fP01Right
            or _same_area(altar_left, e)
        ))
        if partner:
            _pair(altar_left, partner)

    # ── 5. One-way down ladders: avoid pairing with fL05Up ────────────────
    for ow_id in [ExitID.f02Down, ExitID.f03Down2]:
        ow = _find_by_id(ow_id)
        if ow and ow in pool:
            partner = _pick_except(lambda e, _ow=ow: (
                e is _ow
                or e.game_exit_id == ExitID.fL05Up
                or _same_area(_ow, e)
            ))
            if partner:
                _pair(ow, partner)

    # ── 5b. ReduceDeadEndStarts ───────────────────────────────────────────
    # Port of C# ReduceDeadEndStarts: the starting area's exits should not ALL
    # lead to dead-end areas (areas with only one transition).  Guarantees at
    # least one exit from the starting area goes somewhere with multiple paths.
    #
    # Strategy: shuffle the starting-area exits still in pool, then pair the
    # first one that can find a non-dead-end, non-Cliff partner.  A single
    # non-dead-end exit is sufficient; remaining starting exits pair normally.
    if _starting_exit_ids:
        start_exits = [e for e in pool if e.game_exit_id in _starting_exit_ids]
        rng.shuffle(start_exits)
        for se in start_exits:
            if se not in pool:
                continue
            partner = _pick_except(lambda e, _se=se: (
                e is _se
                or e.game_exit_id in DEAD_END_EXITS
                or e.game_exit_id == ExitID.fP02Left   # Cliff is a single-transition dead end
                or _would_self_loop(se.game_exit_id, e.game_exit_id)
                or _same_area(_se, e)
            ))
            if partner is not None:
                _pair(se, partner)
                break   # one guaranteed non-dead-end exit from start is enough
        # Any remaining starting exits fall through to steps 6 & 7.

    # ── 6. Priority-pair inaccessible exits ───────────────────────────────
    inaccessible = [e for e in pool if e.game_exit_id in INACCESSIBLE_EXITS]
    rng.shuffle(inaccessible)
    for inac in inaccessible:
        if inac not in pool:
            continue
        accessible_partners = [e for e in pool
                               if e is not inac
                               and e.game_exit_id not in INACCESSIBLE_EXITS
                               and not _same_area(inac, e)]
        if not accessible_partners:
            # Relax same-area constraint before giving up entirely
            accessible_partners = [e for e in pool
                                   if e is not inac
                                   and e.game_exit_id not in INACCESSIBLE_EXITS]
        if accessible_partners:
            partner = rng.choice(accessible_partners)
            _pair(inac, partner)

    # ── 7. Connectivity-aware random pairing ─────────────────────────────
    # Use the union-find to STRONGLY prefer partners that merge different
    # connected components.  This prevents structural islands without
    # sacrificing randomness — once the graph is connected, pairs are free.
    rng.shuffle(pool)
    while len(pool) >= 2:
        e1 = pool.pop()
        a1 = _exit_area(e1)

        # Phase A: prefer a partner from a DIFFERENT component (bridges islands)
        cross_component = [e for e in pool
                           if not uf.connected(a1, _exit_area(e))
                           and not _same_area(e1, e)]
        if cross_component:
            e2 = rng.choice(cross_component)
        else:
            # Phase B: all remaining exits are in the same component — pick
            # a partner from a different area if possible, else any partner.
            different_area = [e for e in pool if not _same_area(e1, e)]
            e2 = rng.choice(different_area) if different_area else pool[-1]

        pool.remove(e2)
        pairings.append((e1, e2))
        a2 = _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    if uf.num_components > 1:
        print(f"[ER] WARNING: {uf.num_components} disconnected area components "
              f"after pairing (structural islands likely)")

    if pool:
        print(f"[ER] WARNING: {len(pool)} exit(s) left unpaired: "
              f"{[e.name for e in pool]}")

    return _repair_same_dungeon_pairs(pairings, rng)


# ============================================================
# Separate-pool pairing (C# RandomiseHorizontal / Ladder / Gate)
# ============================================================
#
# When full_random_entrances is OFF, each enabled entrance type
# shuffles only within its own pool — left doors pair with right
# doors, up ladders with down ladders, gates with gates.  This
# mirrors the C# Randomiser's individual Randomise*Entrances
# methods rather than FullRandomEntrances.
# ============================================================

# Port of C# StartEntranceLoopCheck — prevents the starting
# entrance from pairing back into its own area.
_START_ENTRANCE_LOOP_MAP: Dict[ExitID, frozenset] = {
    ExitID.f00GateY0: frozenset({ExitID.f00GateYA, ExitID.f00GateYB, ExitID.f00GateYC, ExitID.f00Down}),
    ExitID.f01Right:  frozenset({ExitID.f01Start}),
    ExitID.f01Start:  frozenset({ExitID.f01Right}),
    ExitID.f02Up:     frozenset({ExitID.f02Bifrost, ExitID.f02Down, ExitID.f02GateYA}),
    ExitID.f02Bifrost:frozenset({ExitID.f02Up, ExitID.f02Down, ExitID.f02GateYA}),
    ExitID.f03Right:  frozenset({ExitID.f03Down1, ExitID.f03Down2, ExitID.f03Down3,
                                  ExitID.f03Up, ExitID.f03GateYC, ExitID.f03In}),
    ExitID.f04Up:     frozenset({ExitID.f04Up2, ExitID.f04Up3, ExitID.f04GateYB}),
}


def _start_loop_check(starting_eid: ExitID, candidate_eid: ExitID) -> bool:
    """Port of C# StartEntranceLoopCheck."""
    return candidate_eid in _START_ENTRANCE_LOOP_MAP.get(starting_eid, frozenset())


def _find_in(pool: List[LM2Entrance], eid: ExitID) -> Optional[LM2Entrance]:
    return next((e for e in pool if e.game_exit_id == eid), None)


# ── Horizontal (bipartite: left doors ↔ right doors) ─────────────────

def _pair_horizontal_bipartite(
    left_pool: List[LM2Entrance],
    right_pool: List[LM2Entrance],
    rng: random.Random,
    world,
    base_uf: Optional['_UnionFind'] = None,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Port of C# RandomiseHorizontalEntrances.

    Left doors pair only with right doors.  Cliff and Cavern are placed
    first with constraints, then the remainder pairs randomly.
    """
    left_doors  = list(left_pool)
    right_doors = list(right_pool)
    rng.shuffle(left_doors)
    rng.shuffle(right_doors)
    pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    starting_area = getattr(world, 'starting_area', None)
    opts = world.options
    has_vertical = bool(opts.vertical_entrances)

    # Priority left doors: Cliff first, then Cavern
    priority_left: List[LM2Entrance] = []
    cliff = _find_in(left_doors, ExitID.fP02Left)
    if cliff:
        priority_left.append(cliff)
        left_doors.remove(cliff)
    cavern_left = _find_in(left_doors, ExitID.fP00Left)
    if cavern_left:
        priority_left.append(cavern_left)
        left_doors.remove(cavern_left)

    cavern_to_cliff = False

    # Union-find for connectivity within horizontal pairings
    uf = base_uf.copy() if base_uf is not None else _UnionFind()
    for e in left_pool + right_pool:
        uf.find(_exit_area(e))

    # Pair all left doors (priority first, then remaining)
    all_left = priority_left + left_doors
    for left_door in all_left:
        if not right_doors:
            break

        if left_door.game_exit_id == ExitID.fP02Left:
            # Cliff: avoid starting-area right doors and fL08Right
            ok = [rd for rd in right_doors if not (
                rd.game_exit_id == ExitID.fL08Right
                or (rd.game_exit_id == ExitID.f01Right
                    and starting_area == AreaID.VoD
                    and (not has_vertical or True))  # ReduceDeadEndStarts always on
                or (rd.game_exit_id == ExitID.f03Right
                    and starting_area == AreaID.IBMain)
            )]
            partner = rng.choice(ok) if ok else rng.choice(right_doors)
        elif left_door.game_exit_id == ExitID.fP00Left:
            # Cavern left: avoid self-loop with fP00Right
            # If Cliff→CavernRight, propagate the same restrictions
            ok = [rd for rd in right_doors if not (
                rd.game_exit_id == ExitID.fP00Right
                or (cavern_to_cliff and (
                    rd.game_exit_id == ExitID.fL08Right
                    or (rd.game_exit_id == ExitID.f01Right
                        and starting_area == AreaID.VoD
                        and (not has_vertical or True))
                    or (rd.game_exit_id == ExitID.f03Right
                        and starting_area == AreaID.IBMain)
                ))
            )]
            partner = rng.choice(ok) if ok else rng.choice(right_doors)
        else:
            # Prefer a partner that bridges disconnected components
            a1 = _exit_area(left_door)
            cross = [rd for rd in right_doors
                     if not uf.connected(a1, _exit_area(rd))
                     and not _same_dungeon(left_door, rd)]
            if cross:
                partner = rng.choice(cross)
            else:
                # Fall back: prefer different dungeon, then any
                diff = [rd for rd in right_doors
                        if not _same_dungeon(left_door, rd)]
                partner = rng.choice(diff) if diff else rng.choice(right_doors)

        right_doors.remove(partner)
        pairings.append((left_door, partner))
        a1, a2 = _exit_area(left_door), _exit_area(partner)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

        # Track if Cliff was paired with Cavern's right door
        if (left_door.game_exit_id == ExitID.fP02Left
                and partner.game_exit_id == ExitID.fP00Right):
            cavern_to_cliff = True

    if right_doors:
        print(f"[ER-H] WARNING: {len(right_doors)} right door(s) unpaired")
    return _repair_same_dungeon_pairs(pairings, rng)


# ── Vertical (bipartite: up ladders ↔ down ladders) ──────────────────

def _pair_vertical_bipartite(
    up_pool: List[LM2Entrance],
    down_pool: List[LM2Entrance],
    rng: random.Random,
    world,
    base_uf: Optional['_UnionFind'] = None,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Port of C# RandomiseLadderEntrances.

    Up ladders pair only with down ladders.  Starting-area ladder gets
    ReduceDeadEndStarts treatment; one-way down ladders (f02Down,
    f03Down2) are placed first to avoid pairing with fL05Up.
    """
    up_ladders   = list(up_pool)
    down_ladders = list(down_pool)
    rng.shuffle(up_ladders)
    rng.shuffle(down_ladders)
    pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    starting_area = getattr(world, 'starting_area', None)

    # Determine starting entrance within this pool
    _STARTING_VERTICAL = {ExitID.f04Up, ExitID.f02Up}
    starting_eid: Optional[ExitID] = None
    if starting_area is not None:
        starting_dungeon = _DUNGEON_GROUP.get(starting_area)
        for e in up_ladders:
            pr = getattr(e, 'parent_region', None)
            if pr is None:
                continue
            e_area = getattr(pr, 'game_area_id', None)
            e_dungeon = _DUNGEON_GROUP.get(e_area) if e_area is not None else None
            if (e.game_exit_id in _STARTING_VERTICAL
                    and ((e_dungeon is not None and e_dungeon == starting_dungeon)
                         or e_area == starting_area)):
                starting_eid = e.game_exit_id
                break

    # ReduceDeadEndStarts: pair starting ladder with non-dead-end
    if starting_eid is not None:
        starter = _find_in(up_ladders, starting_eid)
        if starter:
            up_ladders.remove(starter)
            ok = [dl for dl in down_ladders
                  if dl.game_exit_id not in DEAD_END_EXITS
                  and not _start_loop_check(starting_eid, dl.game_exit_id)
                  and not _same_dungeon(starter, dl)]
            if not ok:
                # Relax dungeon constraint
                ok = [dl for dl in down_ladders
                      if dl.game_exit_id not in DEAD_END_EXITS
                      and not _start_loop_check(starting_eid, dl.game_exit_id)]
            if ok:
                partner = rng.choice(ok)
                down_ladders.remove(partner)
                pairings.append((starter, partner))
            else:
                # Can't satisfy constraint, put it back
                up_ladders.append(starter)

    # Priority: one-way down ladders avoid fL05Up
    priority_down: List[LM2Entrance] = []
    for ow_id in [ExitID.f02Down, ExitID.f03Down2]:
        ow = _find_in(down_ladders, ow_id)
        if ow:
            priority_down.append(ow)
            down_ladders.remove(ow)

    # Union-find for connectivity within vertical pairings
    uf = base_uf.copy() if base_uf is not None else _UnionFind()
    for e in up_pool + down_pool:
        uf.find(_exit_area(e))
    for e1, e2 in pairings:
        a1, a2 = _exit_area(e1), _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    # Pair: priority down ladders first, then remaining
    all_down = priority_down + down_ladders
    for down_ladder in all_down:
        if not up_ladders:
            break

        if down_ladder.game_exit_id in (ExitID.f02Down, ExitID.f03Down2):
            # One-way ladders must not pair with fL05Up, and prefer different dungeon
            ok = [ul for ul in up_ladders
                  if ul.game_exit_id != ExitID.fL05Up
                  and not _same_dungeon(down_ladder, ul)]
            if not ok:
                # Relax dungeon constraint but keep fL05Up rejection
                ok = [ul for ul in up_ladders if ul.game_exit_id != ExitID.fL05Up]
            partner = rng.choice(ok) if ok else rng.choice(up_ladders)
        else:
            # Prefer cross-component partner
            a1 = _exit_area(down_ladder)
            cross = [ul for ul in up_ladders
                     if not uf.connected(a1, _exit_area(ul))
                     and not _same_dungeon(down_ladder, ul)]
            if cross:
                partner = rng.choice(cross)
            else:
                diff = [ul for ul in up_ladders
                        if not _same_dungeon(down_ladder, ul)]
                partner = rng.choice(diff) if diff else rng.choice(up_ladders)

        up_ladders.remove(partner)
        pairings.append((partner, down_ladder))
        a1, a2 = _exit_area(partner), _exit_area(down_ladder)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    if up_ladders:
        print(f"[ER-V] WARNING: {len(up_ladders)} up ladder(s) unpaired")
    return _repair_same_dungeon_pairs(pairings, rng)


# ── Gates (same-pool: gates ↔ gates) ─────────────────────────────────

def _pair_gates_pool(
    gate_pool: List[LM2Entrance],
    rng: random.Random,
    world,
    base_uf: Optional['_UnionFind'] = None,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Port of C# RandomiseGateEntrances.

    Gates pair with other gates (same pool, not bipartite).  Starting
    gate gets ReduceDeadEndStarts; illusion gate avoids self-loop;
    inaccessible gates get priority pairing.
    """
    gates = list(gate_pool)
    rng.shuffle(gates)
    pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    starting_area = getattr(world, 'starting_area', None)
    opts = world.options
    costume_clip = bool(opts.costume_clip)

    # Determine starting entrance within this pool
    # All gate ExitIDs that C# considers starting entrances per area
    _STARTING_GATES = {
        ExitID.f00GateY0,   # RoY
        ExitID.f04GateYB,   # IT
        ExitID.f05GateP1,   # DF
        ExitID.f06GateP0,   # SotFG
        ExitID.f08GateP0,   # TS (lives in TSBottom sub-region)
        ExitID.f10GateP0,   # Valhalla
        ExitID.f11GateP0,   # DSLM
        ExitID.f12GateP0,   # AC
        ExitID.f13GateP0,   # HoM
    }
    starting_eid: Optional[ExitID] = None
    if starting_area is not None:
        starting_dungeon = _DUNGEON_GROUP.get(starting_area)
        for e in gates:
            pr = getattr(e, 'parent_region', None)
            if pr is None:
                continue
            e_area = getattr(pr, 'game_area_id', None)
            e_dungeon = _DUNGEON_GROUP.get(e_area) if e_area is not None else None
            if (e.game_exit_id in _STARTING_GATES
                    and ((e_dungeon is not None and e_dungeon == starting_dungeon)
                         or e_area == starting_area)):
                starting_eid = e.game_exit_id
                break

    # ReduceDeadEndStarts: pair starting gate with non-dead-end, different dungeon
    if starting_eid is not None:
        starter = _find_in(gates, starting_eid)
        if starter and len(gates) >= 2:
            gates.remove(starter)
            ok = [g for g in gates
                  if g.game_exit_id not in DEAD_END_EXITS
                  and not _start_loop_check(starting_eid, g.game_exit_id)
                  and not _same_dungeon(starter, g)]
            if not ok:
                # Relax dungeon constraint
                ok = [g for g in gates
                      if g.game_exit_id not in DEAD_END_EXITS
                      and not _start_loop_check(starting_eid, g.game_exit_id)]
            if ok:
                partner = rng.choice(ok)
                gates.remove(partner)
                pairings.append((starter, partner))
            else:
                gates.append(starter)

    # Illusion anti-self-loop — also prefer different dungeon
    ill_n = _find_in(gates, ExitID.fL11GateN)
    if ill_n and len(gates) >= 2:
        gates.remove(ill_n)
        ok = [g for g in gates
              if g.game_exit_id != ExitID.fL11GateY0
              and not _same_dungeon(ill_n, g)]
        if not ok:
            ok = [g for g in gates if g.game_exit_id != ExitID.fL11GateY0]
        if ok:
            partner = rng.choice(ok)
            gates.remove(partner)
            pairings.append((ill_n, partner))
        else:
            gates.append(ill_n)

    # Inaccessible priority: pair inaccessible gates with accessible ones
    priority_gates: List[LM2Entrance] = [
        g for g in gates if g.game_exit_id in INACCESSIBLE_EXITS
    ]
    if costume_clip:
        priority_gates = [g for g in priority_gates
                          if g.game_exit_id != ExitID.f12GateP0]

    for pg in priority_gates:
        gates.remove(pg)

    # Union-find for connectivity within the gate pool
    uf = base_uf.copy() if base_uf is not None else _UnionFind()
    for e in gate_pool:
        uf.find(_exit_area(e))
    for e1, e2 in pairings:
        a1, a2 = _exit_area(e1), _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    # Pair: priority gates pick from main pool, then connectivity-aware random
    while gates:
        if priority_gates:
            g1 = rng.choice(priority_gates)
            priority_gates.remove(g1)
        else:
            g1 = gates.pop(rng.randrange(len(gates)))

        if not gates:
            # Odd gate left over
            print(f"[ER-G] WARNING: gate '{g1.name}' unpaired (odd count)")
            break

        a1 = _exit_area(g1)
        # Prefer cross-component partner from different dungeon
        cross = [g for g in gates
                 if not uf.connected(a1, _exit_area(g))
                 and not _same_dungeon(g1, g)]
        if cross:
            g2 = rng.choice(cross)
        else:
            # Fall back: different dungeon (even if same component)
            diff = [g for g in gates if not _same_dungeon(g1, g)]
            if diff:
                g2 = rng.choice(diff)
            else:
                g2 = gates[rng.randrange(len(gates))]
        gates.remove(g2)
        pairings.append((g1, g2))
        a2 = _exit_area(g2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    # Any leftover priority gates (shouldn't happen normally)
    if priority_gates:
        print(f"[ER-G] WARNING: {len(priority_gates)} priority gate(s) unpaired")

    return _repair_same_dungeon_pairs(pairings, rng)


# ── Unique transitions (same-pool, when enabled in separate mode) ─────

def _pair_unique_pool(
    unique_pool: List[LM2Entrance],
    rng: random.Random,
    world,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Pair unique transitions among themselves.

    The C# randomizer only shuffles unique transitions in FullRandom mode,
    not in separate-pool mode.  This function exists as an extension for
    cases where unique_transitions is enabled alongside separate
    pools.  It applies the Altar anti-self-loop constraint.
    """
    pool = list(unique_pool)
    rng.shuffle(pool)
    pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    # Altar anti-self-loop
    altar_left = _find_in(pool, ExitID.fP01Left)
    if altar_left and len(pool) >= 2:
        pool.remove(altar_left)
        ok = [e for e in pool if e.game_exit_id != ExitID.fP01Right]
        if ok:
            partner = rng.choice(ok)
            pool.remove(partner)
            pairings.append((altar_left, partner))
        else:
            pool.append(altar_left)

    # Random pair remainder
    rng.shuffle(pool)
    while len(pool) >= 2:
        e1 = pool.pop()
        e2 = pool.pop(rng.randrange(len(pool)))
        pairings.append((e1, e2))

    if pool:
        print(f"[ER-U] WARNING: {len(pool)} unique exit(s) unpaired (odd count)")

    return _repair_same_dungeon_pairs(pairings, rng)


# ── Separate-pool dispatcher ─────────────────────────────────────────

def _generate_separate_pairings(
    candidates: List[LM2Entrance],
    rng: random.Random,
    world,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    Split candidates by exit type and pair within each pool.
    Ports the C# behaviour when FullRandomEntrances is OFF:
    each enabled type shuffles independently.
    """
    from .regions import ExitType

    opts = world.options
    by_type: Dict[ExitType, List[LM2Entrance]] = defaultdict(list)
    for e in candidates:
        by_type[e.exit_type].append(e)

    # Build base UF from non-shuffled connections so each per-pool
    # function knows which areas are ALREADY connected.
    shuffled_ids = {e.game_exit_id for e in candidates
                    if getattr(e, 'game_exit_id', None) is not None}
    base_uf = _build_base_uf(world, shuffled_ids)

    all_pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    if opts.horizontal_entrances:
        pairs = _pair_horizontal_bipartite(
            by_type.get(ExitType.LeftDoor, []),
            by_type.get(ExitType.RightDoor, []),
            rng, world, base_uf,
        )
        all_pairings.extend(pairs)
        if pairs:
            print(f"[ER] Horizontal pool: {len(pairs)} pairs")

    if opts.vertical_entrances:
        pairs = _pair_vertical_bipartite(
            by_type.get(ExitType.UpLadder, []),
            by_type.get(ExitType.DownLadder, []),
            rng, world, base_uf,
        )
        all_pairings.extend(pairs)
        if pairs:
            print(f"[ER] Vertical pool: {len(pairs)} pairs")

    if opts.gate_entrances:
        pairs = _pair_gates_pool(
            by_type.get(ExitType.Gate, []),
            rng, world, base_uf,
        )
        all_pairings.extend(pairs)
        if pairs:
            print(f"[ER] Gate pool: {len(pairs)} pairs")

    if opts.unique_transitions:
        unique: List[LM2Entrance] = []
        for t in (ExitType.OneWay, ExitType.Pyramid, ExitType.Start, ExitType.Altar):
            unique.extend(by_type.get(t, []))
        if len(unique) >= 2:
            pairs = _pair_unique_pool(unique, rng, world)
            all_pairings.extend(pairs)
            if pairs:
                print(f"[ER] Unique pool: {len(pairs)} pairs")

    return all_pairings


# ── Reachability validation ───────────────────────────────────────────

def _build_omniscient_state(world):
    """
    Build a CollectionState with EVERY pool item AND every logic-flag
    event (boss kills, puzzles, shortcuts, etc.).  Simulates "the player
    has everything" so we can check the region graph is fully traversable.
    """
    from BaseClasses import CollectionState

    state = CollectionState(world.multiworld)

    for item in world.multiworld.precollected_items[world.player]:
        state.collect(item)

    for item in world.multiworld.itempool:
        if item.player == world.player:
            state.collect(item)

    for loc in world.multiworld.get_locations(world.player):
        if loc.item is not None and loc.item.player == world.player:
            state.collect(loc.item)

    player = world.player
    prog_items = state.prog_items[player]
    for flag_name in LOGIC_FLAG_MAP.keys():
        if flag_name not in prog_items:
            prog_items[flag_name] = 1
        else:
            prog_items[flag_name] = max(prog_items[flag_name], 1)

    prog_items["Guardians"] = 9
    prog_items["Dissonance"] = max(prog_items.get("Dissonance", 0), 6)

    return state


def _validate_region_reachability(world) -> Tuple[bool, List[str]]:
    """
    Check that every location's parent region is reachable using AP's own
    state.can_reach() with an omniscient CollectionState.

    This uses the EXACT SAME reachability logic as AP's fill algorithm,
    including full can_access() evaluation on exits (parent-region checks,
    CanReach() calls inside compiled rules, etc.).

    Returns (is_valid, list_of_unreachable_location_names).
    """
    state = _build_omniscient_state(world)
    player = world.player

    if hasattr(state, 'stale'):
        state.stale[player] = True

    unreachable = []
    for loc in world.multiworld.get_locations(player):
        if loc.parent_region is None:
            continue
        try:
            if not state.can_reach(loc.parent_region, "Region", player):
                unreachable.append(loc.name)
        except Exception:
            unreachable.append(loc.name)

    return len(unreachable) == 0, unreachable


# ── Starting cluster viability check ─────────────────────────────────

# Minimum number of ACCESSIBLE locations (loc.can_reach) in sphere-0.
# Must be high enough that after pre-fills (shops, mantras, research,
# logic flags, dissonance), enough UNFILLED slots remain for the fill
# to bootstrap progression. 
_MIN_STARTING_LOCATIONS = 15

# Minimum number of UNFILLED accessible locations in sphere-0.
# This is the actual bottleneck: the fill algorithm needs empty slots
# to place progression items.  Pre-fills (shops, mantras, research,
# dissonance, logic flags) consume slots before the fill even starts.
_MIN_STARTING_UNFILLED = 11

# Minimum number of distinct REACHABLE AREAS (regions with unique
# game_area_id) in sphere-0.  Prevents configurations where many
# locations are accessible but all in 1-2 areas (tiny cluster that
# the fill can't break out of even with the unfilled minimum met).
_MIN_STARTING_AREAS = 3


def _validate_starting_cluster(world) -> Tuple[bool, str]:
    """
    Check the starting cluster using loc.can_reach() (LOCATION-level access,
    matching AP's fill algorithm exactly) with ONLY precollected items.

    Previous versions used state.can_reach(region) which only checked region
    reachability — a region with 20 locations might have 18 locked behind
    subweapons the player doesn't start with.  This version evaluates each
    location's full access rule (parent_area check + compiled logic).

    Verifies:
    1. The cluster is "open" — has outward exits to unexplored regions.
    2. Enough locations are accessible to bootstrap progression.
    3. Enough of those locations are UNFILLED (available for the fill).
    """
    from BaseClasses import CollectionState

    state = CollectionState(world.multiworld)
    for item in world.multiworld.precollected_items[world.player]:
        state.collect(item)

    player = world.player
    if hasattr(state, 'stale'):
        state.stale[player] = True

    # Count locations using LOCATION-LEVEL access check (not just region)
    reachable_regions: Set[int] = set()
    reachable_areas: Set = set()     # distinct game_area_id values
    loc_count = 0
    unfilled_count = 0
    for loc in world.multiworld.get_locations(player):
        if loc.parent_region is None:
            continue
        try:
            # Use the location's own can_reach — same check AP's fill uses
            accessible = False
            if hasattr(loc, 'can_reach'):
                accessible = loc.can_reach(state)
            elif hasattr(loc, 'can_access'):
                accessible = loc.can_access(state)
            else:
                accessible = state.can_reach(loc.parent_region, "Region", player)

            if accessible:
                reachable_regions.add(id(loc.parent_region))
                loc_count += 1
                if loc.item is None:
                    unfilled_count += 1
                area_id = getattr(loc.parent_region, 'game_area_id', None)
                if area_id is not None:
                    reachable_areas.add(area_id)
        except Exception:
            pass

    # Check openness: at least one exit from a reachable region leads somewhere
    # unreachable — meaning a progression item COULD unlock new territory.
    has_outward = False
    for r in world.multiworld.regions:
        if r.player != player or id(r) not in reachable_regions:
            continue
        for exit_ in r.exits:
            if exit_.connected_region is None:
                continue
            if id(exit_.connected_region) not in reachable_regions:
                has_outward = True
                break
        if has_outward:
            break

    if not has_outward:
        return False, (f"closed island ({loc_count} accessible locations in "
                        f"{len(reachable_areas)} areas, no exit leads outside)")

    # ── Guardian escape check ─────────────────────────────────────────
    # If ALL outward exits require guardian kills (soul gates), the
    # cluster must contain at least one guardian location.  Otherwise
    # the player can never meet the GuardianKills(N) requirement and
    # is permanently softlocked.
    #
    # Build an omniscient state with 0 guardian kills and test each
    # outward exit's access rule.  This correctly handles edge cases:
    # - Soul gates with "Setting(Random Soul Gates)" → accessible
    #   without kills when the setting is enabled.
    # - Non-soul-gate exits with complex item logic → accessible if
    #   items could be placed in the cluster.
    outward_exits: List = []
    for r in world.multiworld.regions:
        if r.player != player or id(r) not in reachable_regions:
            continue
        for exit_ in r.exits:
            if exit_.connected_region is None:
                continue
            if id(exit_.connected_region) not in reachable_regions:
                outward_exits.append(exit_)

    if outward_exits:
        # State with everything EXCEPT guardian kills
        no_kills = _build_omniscient_state(world)
        no_kills.prog_items[player]["Guardians"] = 0
        if hasattr(no_kills, 'stale'):
            no_kills.stale[player] = True

        has_non_kill_exit = False
        for exit_ in outward_exits:
            try:
                if hasattr(exit_, 'can_access') and exit_.can_access(no_kills):
                    has_non_kill_exit = True
                    break
            except Exception:
                pass

        if not has_non_kill_exit:
            # Every outward exit requires guardian kills — check for guardians
            has_guardian = False
            for loc in world.multiworld.get_locations(player):
                if loc.parent_region is None:
                    continue
                loc_type = getattr(loc, 'location_type', None)
                if loc_type is None:
                    loc_type = getattr(loc, 'lm2_type', None)
                if (loc_type == LocationType.Guardian
                        and id(loc.parent_region) in reachable_regions):
                    has_guardian = True
                    break

            if not has_guardian:
                return False, (
                    f"guardian softlock: all {len(outward_exits)} outward exit(s) "
                    f"require guardian kills but cluster "
                    f"({len(reachable_areas)} areas, {loc_count} locs) "
                    f"has no guardians"
                )

    if len(reachable_areas) < _MIN_STARTING_AREAS:
        return False, (f"too few starting areas ({len(reachable_areas)} areas "
                        f"< {_MIN_STARTING_AREAS} minimum, "
                        f"{loc_count} locs / {unfilled_count} unfilled)")

    if loc_count < _MIN_STARTING_LOCATIONS:
        return False, (f"starting cluster too small ({loc_count} accessible "
                        f"locations in {len(reachable_areas)} areas "
                        f"< {_MIN_STARTING_LOCATIONS} minimum)")

    if unfilled_count < _MIN_STARTING_UNFILLED:
        return False, (f"too few unfilled starting slots ({unfilled_count} unfilled "
                        f"of {loc_count} accessible in {len(reachable_areas)} areas "
                        f"< {_MIN_STARTING_UNFILLED} minimum)")

    return True, (f"OK ({loc_count} accessible, {unfilled_count} unfilled, "
                   f"{len(reachable_areas)} areas, open cluster)")


# ── Disconnect / reconnect helpers ────────────────────────────────────

def _disconnect_exit(exit_: LM2Entrance) -> None:
    """Safely disconnect an exit from its connected region."""
    if exit_.connected_region is not None:
        try:
            exit_.connected_region.entrances.remove(exit_)
        except ValueError:
            pass
        exit_.connected_region = None


def _apply_pairings(pairings: List[Tuple[LM2Entrance, LM2Entrance]]) -> None:
    """Connect each paired exit to its partner's parent region (coupled)."""
    for e1, e2 in pairings:
        e1.connect(e2.parent_region)
        e2.connect(e1.parent_region)


def _build_pairing_records(world, pairings):
    """Store pairing data on the world for seed writing and spoiler log."""
    # Name pairings: BOTH directions (for spoiler log lookup — "where does X go?")
    world._er_name_pairings = []
    for e1, e2 in pairings:
        world._er_name_pairings.append((e1.name, e2.name))
        world._er_name_pairings.append((e2.name, e1.name))

    # Exit ID pairings: ONE direction per pair (for seed file writing).
    # The game reads each pair once and creates the bidirectional connection.
    world._er_pairs = []
    for e1, e2 in pairings:
        world._er_pairs.append(EntrancePair(
            from_exit=e1.game_exit_id,
            to_exit=e2.game_exit_id,
        ))


# ── Main entry point (called from __init__.connect_entrances) ─────────

def custom_structural_er(world) -> None:
    """
    Run custom structural entrance randomization with retry.

    Replaces AP Generic ER.  Disconnects shuffleable exits, pairs them
    using the C#-style algorithm, validates full-items reachability via
    logic-aware BFS, and retries up to MAX_ATTEMPTS times on failure.

    When full_random_entrances is ON, all enabled exit types are mixed
    into one pool (C# FullRandomEntrances).  When OFF, each type shuffles
    within its own pool (C# RandomiseHorizontal / Ladder / GateEntrances).

    Sets world._er_pairs and world._er_name_pairings for seed writing
    and spoiler logging.
    """
    from .regions import _shuffleable_exits

    MAX_ATTEMPTS = 100

    opts = world.options
    full_random = bool(opts.full_random_entrances)

    # Set dungeon-level same-area rejection based on player option.
    # When enabled, exits from the same dungeon (e.g. all RoY sub-regions)
    # are treated as same-area.  When disabled, only exact sub-region
    # matches are avoided (closer to vanilla C# behaviour).
    global _DUNGEON_LEVEL_CHECK
    _DUNGEON_LEVEL_CHECK = bool(getattr(opts, 'prevent_area_loops', True))

    candidates = _shuffleable_exits(world)
    rng = world.multiworld.random

    if not candidates:
        return

    # ── Parity handling ──────────────────────────────────────────────
    # Full-random mode: global even count required (one big pool).
    # Separate-pool mode: parity is handled per pool inside each
    # pairing function; unpaired exits are restored to vanilla below.
    if full_random and len(candidates) % 2 != 0:
        inacc = [e for e in candidates if e.game_exit_id in INACCESSIBLE_EXITS]
        dropped = inacc[-1] if inacc else candidates[-1]
        candidates.remove(dropped)
        print(f"[ER] Odd exit count, leaving '{dropped.name}' in vanilla")

    # ── ReduceDeadEndStarts (full-random mode only) ──────────────────
    # In separate-pool mode, each per-type function handles its own
    # starting-exit logic (matching the C# separate Randomise* methods).
    starting_area = getattr(world, 'starting_area', None)
    starting_exit_ids: Set = set()
    if full_random and starting_area is not None:
        # Use dungeon grouping: if starting area is TSLeft, ALL exits
        # from any TS sub-region (TSMain, TSBottom, TSEntrance, etc.)
        # should be considered starting exits for ReduceDeadEndStarts.
        starting_dungeon = _DUNGEON_GROUP.get(starting_area)
        for e in candidates:
            pr = getattr(e, 'parent_region', None)
            if pr is None:
                continue
            e_area = getattr(pr, 'game_area_id', None)
            if e_area is None:
                continue
            e_dungeon = _DUNGEON_GROUP.get(e_area)
            if (e_dungeon is not None and e_dungeon == starting_dungeon) or e_area == starting_area:
                starting_exit_ids.add(e.game_exit_id)
    if starting_exit_ids:
        print(f"[ER] ReduceDeadEndStarts: starting area {starting_area}, "
              f"exits in pool: {[str(eid) for eid in starting_exit_ids]}")

    if not full_random:
        from .regions import ExitType
        pool_summary = defaultdict(int)
        for e in candidates:
            pool_summary[e.exit_type] += 1
        print(f"[ER] Separate-pool mode: "
              + ", ".join(f"{t.value}={n}" for t, n in sorted(pool_summary.items(),
                          key=lambda x: x[0].value)))

    # Save vanilla connections: exit -> target region
    vanilla_targets: Dict[int, object] = {}
    for e in candidates:
        vanilla_targets[id(e)] = e.connected_region

    def _restore_vanilla():
        for e in candidates:
            _disconnect_exit(e)
            target = vanilla_targets[id(e)]
            if target is not None:
                e.connect(target)

    def _disconnect_all():
        for e in candidates:
            _disconnect_exit(e)

    def _restore_unpaired(pairings):
        """Reconnect any candidate not in a pairing to its vanilla target."""
        paired_ids = set()
        for e1, e2 in pairings:
            paired_ids.add(id(e1))
            paired_ids.add(id(e2))
        restored = 0
        for e in candidates:
            if id(e) not in paired_ids:
                target = vanilla_targets.get(id(e))
                if target is not None:
                    e.connect(target)
                    restored += 1
        if restored:
            print(f"[ER] Restored {restored} unpaired exit(s) to vanilla")

    last_pairings = None
    last_unreachable: List[str] = []
    last_cluster_msg: str = ""

    # Build base connectivity UF from non-shuffled connections (built once,
    # cloned per attempt).  This tells pairing functions which areas are
    # ALREADY connected through internal exits, corridors, etc.
    shuffled_ids = {e.game_exit_id for e in candidates
                    if getattr(e, 'game_exit_id', None) is not None}
    base_uf = _build_base_uf(world, shuffled_ids)

    # ── Persistent-unreachable tracking ──────────────────────────────
    # If the SAME locations are unreachable in every attempt, the ER
    # can't fix them (they're caused by logic/soul-gate issues, not
    # structural pairing).  After a burn-in period, we identify these
    # and tolerate them rather than retrying forever.
    _BURNIN = 5                       # attempts before computing intersection
    all_unreachable_sets: List[Set[str]] = []
    persistent_unreachable: Set[str] = set()

    for attempt in range(MAX_ATTEMPTS):
        _restore_vanilla()
        _disconnect_all()

        # ── Generate pairings ─────────────────────────────────────────
        if full_random:
            pairings = _generate_pairings(candidates, rng, starting_exit_ids,
                                          base_uf=base_uf)
        else:
            pairings = _generate_separate_pairings(candidates, rng, world)

        _apply_pairings(pairings)

        # In separate-pool mode, some exits may be unpaired (odd counts
        # or unmatched bipartite pools).  Restore those to vanilla so
        # they don't leave holes in the region graph.
        if not full_random:
            _restore_unpaired(pairings)

        last_pairings = pairings

        # ── Validation 1: omniscient reachability ─────────────────────
        # With ALL items + events, can every region be reached?
        # Catches permanent map partitions.
        valid, unreachable = _validate_region_reachability(world)
        last_unreachable = unreachable

        # Track unreachable sets for persistent-unreachable detection
        all_unreachable_sets.append(set(unreachable))

        # After burn-in, compute persistent unreachable (locations that
        # failed in EVERY attempt so far).  These aren't ER's fault.
        if attempt + 1 == _BURNIN:
            persistent_unreachable = set.intersection(*all_unreachable_sets)
            if persistent_unreachable:
                print(f"[ER] Detected {len(persistent_unreachable)} persistently "
                      f"unreachable location(s) (not caused by ER): "
                      f"{sorted(persistent_unreachable)[:5]}")

        # Filter out persistent unreachable — only reject if there are
        # NEW unreachable locations that the ER could potentially fix.
        er_caused = [loc for loc in unreachable
                     if loc not in persistent_unreachable]

        if er_caused:
            if attempt < 5 or attempt % 25 == 0:
                print(f"[ER] Attempt {attempt + 1}: {len(er_caused)} ER-caused + "
                      f"{len(persistent_unreachable)} persistent unreachable "
                      f"(e.g. {er_caused[:5]}), retrying...")
            continue

        # If we get here, only persistent unreachable remain (or none).
        if persistent_unreachable and unreachable:
            print(f"[ER] Attempt {attempt + 1}: tolerating "
                  f"{len(persistent_unreachable)} persistently unreachable "
                  f"location(s) not caused by ER")

        # ── Validation 2: starting cluster viability ──────────────────
        # With ONLY precollected items, is the reachable cluster large
        # enough and open (has outward exits) to bootstrap progression?
        # Catches the case where omniscient check passes but the fill
        # can't place enough items to break out of a tiny starting area.
        cluster_ok, cluster_msg = _validate_starting_cluster(world)
        last_cluster_msg = cluster_msg

        if not cluster_ok:
            if attempt < 5 or attempt % 25 == 0:
                print(f"[ER] Attempt {attempt + 1}: {cluster_msg}, retrying...")
            continue

        # Both checks passed
        if attempt > 0:
            print(f"[ER] Structural ER succeeded on attempt {attempt + 1} "
                  f"({cluster_msg})")
        break
    else:
        print(f"[ER] WARNING: Structural ER could not validate after "
              f"{MAX_ATTEMPTS} attempts. Last failure: "
              f"{len(last_unreachable)} unreachable "
              f"({len(persistent_unreachable)} persistent), "
              f"cluster: {last_cluster_msg}. Seed may be unbeatable.")

    # ── Build pairing records for seed file & spoiler log ────────────
    _build_pairing_records(world, last_pairings)

    # Store the set of locations that were already unreachable after structural ER.
    # Soul gate validation will use this to avoid rejecting configurations that
    # don't make things WORSE than the structural layout already is.
    world._structural_unreachable = set(last_unreachable)

    # ── Print pairings ───────────────────────────────────────────────
    print(f"\n[ER] === ENTRANCE PAIRINGS ===")
    for src, tgt in sorted(world._er_name_pairings):
        print(f"[ER]   {src}  <->  {tgt}")
    print(f"[ER] === END PAIRINGS ({len(world._er_name_pairings)} pairs) ===\n")

    # ── IBMain post-endgame escape route ─────────────────────────────
    _log_ibmain_escape_standalone(world)


# ============================================================
# Soul Gate Randomizer
# ============================================================

class SoulGateRandomizer:
    """
    Handles soul gate pairing and GuardianKills(N) logic injection.

    This is the only entrance randomization that remains custom after
    migrating structural ER to AP's built-in entrance_rando system.
    Soul gates carry dynamic GuardianKills(N) thresholds that AP Generic
    ER has no model for, so they are handled here separately.
    """

    def __init__(self, rng: random.Random, entrances: List[LM2Entrance], world):
        self.rng = rng
        self.entrances = entrances
        self.world = world
        self.options = world.options
        self.soul_gate_pairs: List[SoulGatePair] = []

    def randomize(self) -> bool:
        """Randomize soul gates with retry logic. Returns True on success, False if exhausted."""
        if not self.options.soul_gate_entrances:
            return True
        return self._randomize_soul_gate_entrances_retry()

    def _log_soul_gate_pairings(self, label: str = ""):
        """Print current soul gate pairings for debugging."""
        if not self.soul_gate_pairs:
            print(f"[ER-SG] {label}No soul gate pairs.")
            return
        print(f"[ER-SG] {label}Soul gate pairings ({len(self.soul_gate_pairs)} pairs):")
        for sgp in self.soul_gate_pairs:
            # Resolve exit names
            name1 = str(sgp.gate1)
            name2 = str(sgp.gate2)
            for e in self.entrances:
                if hasattr(e, 'game_exit_id'):
                    if e.game_exit_id == sgp.gate1:
                        name1 = e.name
                    if e.game_exit_id == sgp.gate2:
                        name2 = e.name
            print(f"[ER-SG]   {name1} <-> {name2}  (cost: {sgp.soul_amount})")

    def _get_exits_of_type(self, exit_type: ExitType) -> List[LM2Entrance]:
        return [e for e in self.entrances if e.exit_type == exit_type]

    # ============================================================
    # Soul gate randomization (unchanged from original)
    # ============================================================

    def _randomize_soul_gate_entrances(self):
        """
        Direct port of C# RandomiseSoulGateEntrances().

        AP-safe change: soul amounts are sorted ascending before assignment
        so that low-cost gates are placed before high-cost ones, preventing
        deadlocks where GuardianKills(N) areas are only accessible through
        other GuardianKills(N) gates.
        """
        gates = list(self._get_exits_of_type(ExitType.SoulGate))
        self.rng.shuffle(gates)

        if self.options.random_soul_gate_value:
            soul_amounts = [1, 2, 3, 5]
        else:
            soul_amounts = [1, 2, 2, 3, 3, 5, 5, 5]

        if self.options.include_nine_soul_gates:
            soul_amounts.append(9)
            priority_gates = [g for g in gates
                              if g.game_exit_id in (ExitID.f03GateN9, ExitID.f13GateN9)]
            for g in priority_gates:
                gates.remove(g)
        else:
            gate1 = next((g for g in gates if g.game_exit_id == ExitID.f03GateN9), None)
            gate2 = next((g for g in gates if g.game_exit_id == ExitID.f13GateN9), None)
            if gate1 and gate2:
                gates.remove(gate1)
                gates.remove(gate2)
                self._append_logic_outside_parens(gate1, 'and GuardianKills(9)')
                self._append_logic_outside_parens(gate2, 'and GuardianKills(9)')
                self._fix_soul_gate_logic(gate1, gate2)
                self._fix_soul_gate_logic(gate2, gate1)
                saved1 = gate1.parent_region
                saved2 = gate2.parent_region
                gate1.disconnect()
                gate2.disconnect()
                gate1.connect(saved2)
                gate2.connect(saved1)
                self.soul_gate_pairs.append(SoulGatePair(gate1.game_exit_id, gate2.game_exit_id, 9))
            priority_gates = []

        if not self.options.random_soul_gate_value:
            soul_amounts.sort()
        else:
            self.rng.shuffle(soul_amounts)

        while gates or priority_gates:
            if len(gates) + len(priority_gates) < 2:
                break

            if priority_gates:
                gate1 = self.rng.choice(priority_gates)
                priority_gates.remove(gate1)
            else:
                gate1 = self.rng.choice(gates)
                gates.remove(gate1)

            valid_gate2 = []
            for g in gates:
                if (gate1.game_exit_id == ExitID.f03GateN9 and (
                        g.game_exit_id == ExitID.f08GateN8 or
                        (g.game_exit_id == ExitID.f14GateN6 and self.options.random_dissonance))):
                    continue
                if (gate1.game_exit_id == ExitID.f13GateN9 and
                        g.game_exit_id not in DEAD_END_EXITS and
                        g.game_exit_id not in INACCESSIBLE_EXITS):
                    continue
                valid_gate2.append(g)

            if not valid_gate2:
                valid_gate2 = list(gates)
            gate2 = self.rng.choice(valid_gate2)
            gates.remove(gate2)

            valid_amounts = [
                a for a in soul_amounts
                if not (
                    (self.options.accessibility.value == 2 or not self.options.random_dissonance)
                    and (gate1.game_exit_id == ExitID.f14GateN6 or gate2.game_exit_id == ExitID.f14GateN6)
                    and a == 9
                )
            ]
            if not valid_amounts:
                valid_amounts = soul_amounts

            if self.options.random_soul_gate_value:
                soul_amount = self.rng.choice(valid_amounts)
            else:
                soul_amount = valid_amounts[0]
                soul_amounts.remove(soul_amount)

            self._append_logic_outside_parens(gate1, f'and GuardianKills({soul_amount})')
            self._append_logic_outside_parens(gate2, f'and GuardianKills({soul_amount})')
            self._fix_soul_gate_logic(gate1, gate2)
            self._fix_soul_gate_logic(gate2, gate1)

            saved1 = gate1.parent_region
            saved2 = gate2.parent_region
            gate1.disconnect()
            gate2.disconnect()
            gate1.connect(saved2)
            gate2.connect(saved1)

            self.soul_gate_pairs.append(SoulGatePair(gate1.game_exit_id, gate2.game_exit_id, soul_amount))

            if gate1.game_exit_id == ExitID.f14GateN6 or gate2.game_exit_id == ExitID.f14GateN6:
                self._update_epg_logic(gate1, gate2, soul_amount)

    def _fix_soul_gate_logic(self, gate1: LM2Entrance, gate2: LM2Entrance):
        """
        C# FixSoulGateLogic(gate1, gate2) — appends extra requirements to
        gate2 based on gate1's ID.  GuardianKills is handled separately.
        """
        if gate1.game_exit_id == ExitID.f14GateN6:
            self._append_logic_outside_parens(gate2, 'and CanWarp')
        elif gate1.game_exit_id == ExitID.f06GateN7:
            self._append_logic_outside_parens(gate2, 'and Has(Feather) and Has(Claydoll Suit)')
        elif gate1.game_exit_id == ExitID.f12GateN8:
            self._append_logic_outside_parens(gate2, 'and (CanWarp or Has(Feather))')
        elif gate1.game_exit_id == ExitID.f13GateN9:
            self._append_logic_outside_parens(gate2, 'and False')

    def _update_epg_logic(self, gate1: LM2Entrance, gate2: LM2Entrance, soul_amount: int):
        """Update EPG gates puzzle logic when the EPG soul gate is randomized."""
        for exit_ in self.entrances:
            if hasattr(exit_, 'connecting_area') and exit_.connecting_area == AreaID.EPDHel:
                if gate1.game_exit_id == ExitID.f04GateN6 or gate2.game_exit_id == ExitID.f04GateN6:
                    self._append_logic_outside_parens(
                        exit_, f'and IsDead(Vidofnir) and GuardianKills({soul_amount})')
                else:
                    self._append_logic_outside_parens(exit_, f'and GuardianKills({soul_amount})')
                break

    def _randomize_soul_gate_entrances_retry(self):
        """Retry wrapper for soul gate randomization with up to 50 inner attempts."""
        MAX_ATTEMPTS = 50

        gates = self._get_exits_of_type(ExitType.SoulGate)
        vanilla_state = {
            g.game_exit_id: (g.connected_region, g._original_logic)
            for g in gates
        }

        # _update_epg_logic modifies the EPDHel Internal exit (not a soul gate),
        # appending GuardianKills(N).  We must save/restore it on each retry,
        # otherwise the logic accumulates "and GuardianKills(N)" on every attempt.
        epd_hel_exit = None
        epd_hel_vanilla_logic = None
        for e in self.entrances:
            if (hasattr(e, 'connecting_area')
                    and e.connecting_area == AreaID.EPDHel):
                epd_hel_exit = e
                epd_hel_vanilla_logic = e._original_logic
                break

        for attempt in range(MAX_ATTEMPTS):
            for gate in gates:
                saved_region, saved_logic = vanilla_state[gate.game_exit_id]
                if gate.connected_region is not None:
                    if gate in gate.connected_region.entrances:
                        gate.connected_region.entrances.remove(gate)
                    gate.connected_region = None
                gate._original_logic = saved_logic
                tokens = LogicTokeniser(saved_logic).tokenise()
                gate._logic_tree = LogicTree.parse(tokens)
                if gate._world is not None:
                    gate._compiled_rule = gate._logic_tree.compile(gate._world)
                gate.access_rule = gate.can_access
                gate.connect(saved_region)

            # Restore EPDHel internal exit logic (cleared of prior attempts'
            # GuardianKills appendages).
            if epd_hel_exit is not None and epd_hel_vanilla_logic is not None:
                self._reset_logic(epd_hel_exit, epd_hel_vanilla_logic)

            self.soul_gate_pairs.clear()
            self._randomize_soul_gate_entrances()

            if not self._validate_soul_gate_reachability():
                print(f"[ER] Soul gate attempt {attempt + 1} failed, retrying...")
                continue

            # Kill simulation passed.  Now check that the logic modifications
            # made by _update_epg_logic (GuardianKills on the EPDHel Internal
            # exit) haven't created a circular dependency (e.g. GuardianKills(9)
            # blocks Hel, but Hel IS the 9th guardian).
            # Only reject if soul gates made things WORSE than the structural
            # layout already was — don't reject inherited unreachables.
            valid, unreachable = _validate_region_reachability(self.world)
            if not valid:
                structural = getattr(self.world, '_structural_unreachable', set())
                new_unreachable = [loc for loc in unreachable if loc not in structural]
                if new_unreachable:
                    print(f"[ER] Soul gate attempt {attempt + 1}: post-gate logic "
                          f"made {len(new_unreachable)} NEW locations unreachable "
                          f"(e.g. {new_unreachable[:3]}), retrying...")
                    continue
                # All unreachable locations were already unreachable from structural ER

            if attempt > 0:
                print(f"[ER] Soul gate succeeded on attempt {attempt + 1}")
            self._log_soul_gate_pairings()
            return True

        print(f"[ER] Soul gate randomization failed after {MAX_ATTEMPTS} attempts "
              f"— structural layout incompatible with soul gates.")
        self._log_soul_gate_pairings("LAST FAILED: ")
        return False

    # ============================================================
    # Soul gate validation helpers
    # ============================================================

    def get_max_reachable_regions(self) -> set:
        """
        Returns the set of region names reachable with all guardians defeated.
        Used to mark structurally cut-off locations as EXCLUDED after ER.
        """
        kill_costs = self._build_kill_costs()
        guardian_locs = [
            loc for loc in self.world.multiworld.get_locations(self.world.player)
            if hasattr(loc, 'location_type') and loc.location_type == LocationType.Guardian
        ]
        return self._flood_fill(len(guardian_locs), kill_costs)

    def _flood_fill(self, kills: int, kill_gated_exits: dict) -> set:
        """
        Return the set of region names reachable with *kills* guardian kills.

        kill_gated_exits maps id(exit) -> kill cost for ANY exit that has
        a GuardianKills(N) requirement in its logic (soul gates, internal
        exits modified by _update_epg_logic, etc.).  Exits not in the dict
        are freely traversable.  Cost of 9999 = permanently blocked.
        """
        visited: set = set()
        queue = []
        for r in self.world.multiworld.regions:
            if r.player == self.world.player and r.name == 'Menu':
                queue.append(r)
                break
        while queue:
            region = queue.pop()
            if region.name in visited:
                continue
            visited.add(region.name)
            for exit_ in region.exits:
                if exit_.connected_region is None:
                    continue
                if exit_.connected_region.name in visited:
                    continue
                # Gate on kill cost if this exit has a GuardianKills requirement
                cost = kill_gated_exits.get(id(exit_))
                if cost is not None and kills < cost:
                    continue
                queue.append(exit_.connected_region)
        return visited

    def _build_kill_costs(self) -> dict:
        """
        Scan ALL exits for GuardianKills(N) requirements and return a dict
        mapping id(exit) -> kill cost.  This covers soul gates (which have
        GuardianKills appended by _randomize_soul_gate_entrances) AND any
        internal/other exits modified by _update_epg_logic.

        Exits with 'and False' in their logic get cost 9999 (permanently blocked).
        Exits without GuardianKills are NOT in the dict (freely traversable).
        """
        import re
        kill_costs: dict = {}

        for region in self.world.multiworld.get_regions(self.world.player):
            for exit_ in region.exits:
                if exit_.connected_region is None:
                    continue
                logic = getattr(exit_, '_original_logic', '') or ''
                if not logic.strip():
                    continue

                # Check for permanently dead exits
                is_dead = (' and False' in logic or
                           logic.strip() == 'False' or
                           logic.strip().startswith('(False)'))
                if is_dead:
                    kill_costs[id(exit_)] = 9999
                    continue

                # Extract GuardianKills(N) — use the last (highest) match
                kill_matches = re.findall(r'GuardianKills\((\d+)\)', logic)
                if kill_matches:
                    kill_costs[id(exit_)] = int(kill_matches[-1])

        return kill_costs

    def _validate_soul_gate_reachability(self) -> bool:
        kill_costs = self._build_kill_costs()

        guardian_locs = [
            loc for loc in self.world.multiworld.get_locations(self.world.player)
            if hasattr(loc, 'location_type') and loc.location_type == LocationType.Guardian
        ]

        # Part 1: kill-order simulation — each guardian must be reachable in
        # a valid sequence where each kill unlocks the next threshold.
        reachable = self._flood_fill(0, kill_costs)
        kills = 0
        changed = True
        while changed:
            changed = False
            new_kills = sum(
                1 for loc in guardian_locs
                if loc.parent_region and loc.parent_region.name in reachable
            )
            if new_kills > kills:
                kills = new_kills
                reachable = self._flood_fill(kills, kill_costs)
                changed = True

        unreachable_guardians = [
            loc.name for loc in guardian_locs
            if not loc.parent_region or loc.parent_region.name not in reachable
        ]
        if unreachable_guardians:
            print(f"[ER] Soul gate kill simulation failed. Unreachable: {unreachable_guardians}")
            return False

        # Part 2: structural reachability (full accessibility only)
        if self.world.options.accessibility == self.world.options.accessibility.option_full:
            all_reachable = self._flood_fill(len(guardian_locs), kill_costs)
            all_locs = list(self.world.multiworld.get_locations(self.world.player))
            unreachable_locs = [
                loc.name for loc in all_locs
                if loc.parent_region and loc.parent_region.name not in all_reachable
            ]
            if unreachable_locs:
                print(f"[ER] Structural reachability failed: {len(unreachable_locs)} locations cut off "
                      f"(e.g. {unreachable_locs[:3]})")
                return False

        print(f"[ER]   Kill simulation passed: all {len(guardian_locs)} guardians reachable"
              + (', all locations structurally reachable'
                 if self.world.options.accessibility == self.world.options.accessibility.option_full
                 else ''))
        return True


    def _logic_free_graph(self) -> Dict[AreaID, Set[AreaID]]:
        """
        Area graph restricted to exits whose logic is unconditionally True
        (bare 'True' or empty string only — no item or flag requirements).

        Used by _starting_cluster_viable to approximate the set of areas
        reachable with zero items from the starting area.
        """
        graph: Dict[AreaID, Set[AreaID]] = defaultdict(set)
        for e in self.entrances:
            if e.connected_region is None:
                continue
            logic = (getattr(e, '_original_logic', '') or '').strip()
            if logic.lower() not in ('true', ''):
                continue
            graph[e.parent_region.game_area_id].add(e.connected_region.game_area_id)
        return graph

    def _starting_cluster_viable(self, attempt: int) -> bool:
        """
        Guard against closed-island item deadlocks that ER structural checks miss.

        Builds the set of areas reachable from the starting area using only
        starting items (via can_access on the pre-collected CollectionState).
        Then checks that at least one exit FROM that cluster leads to an area
        OUTSIDE it — i.e. the cluster is open and can expand with more items.

        A cluster with no outward exits is a closed island: all items the player
        can ever reach are the ones already placed in that cluster, and no
        progression path can cross the boundary regardless of where items are
        placed. AP's fill will produce an unbeatable seed every time.

        Concrete failure: ACTablet start where f12GateP0 (ACBottom) is paired
        with f10GateP0 (ValhallaMain). Both exits are within the starting
        cluster, and no other exit from the cluster points outside it. The
        cluster has 23 locations and passes a count-based threshold, but is
        structurally unbeatable.
        """
        from BaseClasses import CollectionState

        # Build a CollectionState with only the pre-collected starting items.
        state = CollectionState(self.world.multiworld)
        for item in self.world.multiworld.precollected_items[self.world.player]:
            state.collect(item)

        # BFS: expand through any exit accessible with starting items.
        visited: Set[AreaID] = {self.starting_area}
        queue: list = [self.starting_area]
        while queue:
            cur = queue.pop()
            for exit_ in self.entrances:
                if exit_.parent_region.game_area_id != cur:
                    continue
                if exit_.connected_region is None:
                    continue
                dst = exit_.connected_region.game_area_id
                if dst in visited:
                    continue
                if exit_.can_access(state):
                    visited.add(dst)
                    queue.append(dst)

        # Open-cluster check: at least one exit from the cluster must lead outside.
        # An exit pointing to a destination NOT in visited means the cluster has
        # an item-gated door that can expand reachability with more items.
        for exit_ in self.entrances:
            if exit_.connected_region is None:
                continue
            if exit_.parent_region.game_area_id not in visited:
                continue
            if exit_.connected_region.game_area_id not in visited:
                return True   # open — some exit points outside the cluster

        # Every exit from the cluster leads back into it: closed island.
        print(f"[ER] Attempt {attempt}: FAIL — starting cluster is a closed island "
              f"({len(visited)} areas reachable with starting items, no exit leads outside). "
              f"Guaranteed unbeatable regardless of item placement.")
        return False


    # ── Graph helpers used by IBMain escape path ──────────────────────

    def _area_graph(self) -> Dict[AreaID, Set[AreaID]]:
        graph: Dict[AreaID, Set[AreaID]] = defaultdict(set)
        for e in self.entrances:
            if e.connected_region is None:
                continue
            logic = getattr(e, '_original_logic', '') or ''
            if 'false' in logic.lower():
                continue
            if hasattr(e.parent_region, 'game_area_id') and hasattr(e.connected_region, 'game_area_id'):
                graph[e.parent_region.game_area_id].add(e.connected_region.game_area_id)
        return graph

    def _ibmain_escape_graph(self,
                              base_graph: Dict[AreaID, Set[AreaID]]
                              ) -> Tuple[Dict[AreaID, Set[AreaID]],
                                         Dict[Tuple[AreaID, AreaID], str]]:
        """
        Extend *base_graph* with Holy Grail warp edges for the escape BFS.

        Mirrors the JavaScript tracker's calculateEscapeRoute logic:
          - Reaching any of the five grail-enabling areas re-enables Holy Grail.
          - From there the player can warp to any of the fourteen grail fields.
          - Those virtual warp edges are added here so the BFS can find a path
            to Cliff through a Holy Grail warp even if no direct physical path
            exists from IBMain.

        Returns (extended_graph, edge_labels) where edge_labels maps
        (src, dst) -> human-readable description for warp hops.
        """
        # Areas whose entry re-enables the Holy Grail (post-endgame).
        _GRAIL_ENABLING: frozenset = frozenset({
            AreaID.GateofGuidance,
            AreaID.GateofGuidanceLeft,
            AreaID.MausoleumofGiants,
            AreaID.MausoleumofGiantsRubble,
            AreaID.VoD,
            AreaID.VoDLadder,
            AreaID.GateofIllusion,
            AreaID.Nibiru,
        })

        # Canonical grail warp landing spots (one representative area per dungeon).
        # Order mirrors the JS GRAIL_FIELDS list.
        _GRAIL_WARP_DESTS: List[Tuple[str, AreaID]] = [
            ("Village of Departure",         AreaID.VoD),
            ("Roots of Yggdrasil",           AreaID.RoY),
            ("Annwfn",                       AreaID.AnnwfnMain),
            ("Immortal Battlefield",         AreaID.IBMain),
            ("Icefire Treetop",              AreaID.ITLeft),
            ("Divine Fortress",              AreaID.DFMain),
            ("Shrine of the Frost Giants",   AreaID.SotFGGrail),
            ("Gate of the Dead",             AreaID.GotD),
            ("Takamagahara Shrine",          AreaID.TSMain),
            ("Heaven's Labyrinth",           AreaID.HL),
            ("Valhalla",                     AreaID.ValhallaMain),
            ("Dark Star Lord's Mausoleum",   AreaID.DSLMMain),
            ("Ancient Chaos",                AreaID.ACTablet),
            ("Hall of Malice",               AreaID.HoM),
            ("Eternal Prison Gloom",         AreaID.EPG),
            ("Eternal Prison Doom",          AreaID.EPDHel),
        ]

        extended: Dict[AreaID, Set[AreaID]] = defaultdict(set)
        for src, dsts in base_graph.items():
            extended[src].update(dsts)

        edge_labels: Dict[Tuple[AreaID, AreaID], str] = {}

        for src in _GRAIL_ENABLING:
            for dest_name, dest_area in _GRAIL_WARP_DESTS:
                if dest_area != src:  # no self-warp
                    extended[src].add(dest_area)
                    edge_labels[(src, dest_area)] = f"Holy Grail warp to {dest_name}"

        return extended, edge_labels

    def _log_ibmain_escape_path(self, graph: Dict[AreaID, Set[AreaID]]) -> str:
        """
        BFS from IBMain to Cliff using the Holy Grail-extended escape graph.

        Mirrors the JavaScript tracker's calculateEscapeRoute function:
        if IBMain can reach a grail-enabling area (Gate of Guidance, Mausoleum
        of Giants, VoD, Gate of Illusion, or Nibiru) the player can re-enable
        the Holy Grail and warp to any dungeon, then walk to Cliff from there.
        Warp hops are labelled in the path string.

        Returns a human-readable path string, prints it, and stores it on
        self.world.ibmain_escape_spoiler for __init__.write_spoiler().
        """
        def aname(a: AreaID) -> str:
            return a.name if hasattr(a, 'name') else str(a)

        extended, edge_labels = self._ibmain_escape_graph(graph)

        target = AreaID.Cliff
        start  = AreaID.IBMain

        # BFS tracking both predecessor area and the edge label (if any).
        parent: Dict[AreaID, Optional[AreaID]]   = {start: None}
        via:    Dict[AreaID, Optional[str]]       = {start: None}
        q: deque = deque([start])
        while q:
            cur = q.popleft()
            if cur == target:
                break
            for nxt in extended.get(cur, ()):
                if nxt not in parent:
                    parent[nxt] = cur
                    via[nxt]    = edge_labels.get((cur, nxt))
                    q.append(nxt)

        if target not in parent:
            line = "[ER] SPOILER: IBMain has no post-endgame escape route to Cliff."
            print(line)
            self.world.ibmain_escape_spoiler = line
            return line

        # Reconstruct path with labels for warp hops.
        steps: List[str] = []
        cur = target
        while cur is not None:
            label = via.get(cur)
            if label:
                steps.append(f"({label})")
            steps.append(aname(cur))
            cur = parent.get(cur)
        steps.reverse()

        hop_count = sum(1 for s in steps if not s.startswith('('))
        path_str  = " -> ".join(steps)
        line = f"[ER] SPOILER — IBMain -> Cliff ({hop_count - 1} hops): {path_str}"
        print(line)
        self.world.ibmain_escape_spoiler = line
        return line

    # ── Logic append helpers (used by soul gate methods) ──────────────

    @staticmethod
    def _append_logic_outside_parens(entrance: LM2Entrance, suffix: str) -> None:
        cur = (getattr(entrance, '_original_logic', '') or '').strip()
        if suffix.strip().startswith('and') and (' or ' in cur) and not cur.startswith('('):
            cur = f'({cur})'
        if cur:
            cur = cur + ' '
        new_logic = cur + suffix.strip()
        entrance._original_logic = new_logic
        tokens = LogicTokeniser(new_logic).tokenise()
        entrance._logic_tree = LogicTree.parse(tokens)
        if getattr(entrance, '_world', None) is not None:
            entrance._compiled_rule = entrance._logic_tree.compile(entrance._world)
        else:
            entrance._compiled_rule = None

    @staticmethod
    def _reset_logic(entrance: LM2Entrance, base_logic: Optional[str]) -> None:
        if base_logic is not None:
            entrance._original_logic = base_logic
            tokens = LogicTokeniser(base_logic).tokenise()
            entrance._logic_tree = LogicTree.parse(tokens)
            if getattr(entrance, '_world', None) is not None:
                entrance._compiled_rule = entrance._logic_tree.compile(entrance._world)
            else:
                entrance._compiled_rule = None