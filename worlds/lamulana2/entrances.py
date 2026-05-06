from __future__ import annotations

import re
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

from . import _log
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
# Exit pool filters
# ============================================================
#
# All exits in LM2 are treated as TWO_WAY by the ER.  Even exits that are
# physically one-directional in vanilla (Bifrost falls, corridor drops) are
# shuffled as paired two-way transitions by the C# randomizer, because in
# ER context taking exit A connects you to B, and the reverse connection
# from B back to A is the ER-created coupled pair.

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


# Pairs that form a *virtual* dead-end when one side is the starting exit:
# both areas can be entered, but escape requires late-game items the player
# can't have yet (mantras, djed, mid-late bosses), and neither side has
# another non-soul-gate exit to bootstrap progression.  Treated like Cliff
# in ReduceDeadEndStarts -- the starting exit must not pair with the other.
#
# TS <-> DF: TS escape needs djed + mantra + 5 mantra chants + Raijin/Fujin;
# DF's only other exit is a soul gate, and no boss is reachable inside the
# TS<->DF island to earn souls.
_VIRTUAL_DEAD_END_START_PAIRS: frozenset = frozenset({
    frozenset({ExitID.f08GateP0, ExitID.f05GateP1}),  # TS Bottom Gate <-> DF Left Gate
})


# Vanilla soul gate pairings used when soul_gate_entrances is OFF but
# value-only randomization is enabled.  N9 pair is listed last so that
# random_dissonance N9 floor handling is straightforward.
_VANILLA_SOUL_GATE_PAIRS: Tuple[Tuple[ExitID, ExitID], ...] = (
    (ExitID.f00GateN1, ExitID.f05GateN1),
    (ExitID.f02GateN2, ExitID.f06GateN2),
    (ExitID.f03GateN3, ExitID.f07GateN3),
    (ExitID.f03GateN4, ExitID.f08GateN4),
    (ExitID.f04GateN5, ExitID.f09GateN5),
    (ExitID.f04GateN6, ExitID.f14GateN6),
    (ExitID.f06GateN7, ExitID.f10GateN7),
    (ExitID.f08GateN8, ExitID.f12GateN8),
    (ExitID.f03GateN9, ExitID.f13GateN9),
)


def _would_self_loop(e1_id: ExitID, e2_id: ExitID) -> bool:
    """True if pairing e1<->e2 would create a trivial self-loop."""
    return frozenset({e1_id, e2_id}) in _BANNED_SELF_LOOP_PAIRS


def _is_virtual_dead_end_start_pair(e1_id: ExitID, e2_id: ExitID) -> bool:
    """True if pairing e1<->e2 forms a virtual dead-end when one side is
    the starting exit (see _VIRTUAL_DEAD_END_START_PAIRS)."""
    return frozenset({e1_id, e2_id}) in _VIRTUAL_DEAD_END_START_PAIRS


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
        _log(f"[ER] Repaired {repaired} same-dungeon pair(s) via swap")
    elif bad:
        still_bad = sum(1 for e1, e2 in result if _same_dungeon(e1, e2))
        if still_bad:
            _log(f"[ER] WARNING: {still_bad} same-dungeon pair(s) could not be repaired")

    return result


_BASE_UF_EXCLUDED_TYPES: Set = {
    ExitType.SoulGate,
    ExitType.Corridor,
    ExitType.PrisonExit,
    ExitType.PrisonGate,
    ExitType.SpiralGate,
}


def _build_base_uf(world, shuffled_exit_ids: Optional[Set] = None) -> '_UnionFind':
    """
    Build a union-find seeded with the EXISTING connectivity graph.

    Walks every exit in the world.  For exits that are NOT being shuffled
    (internal connections, elevators, etc.), unions the parent area with
    the connected area.  This gives the pairing functions an accurate
    picture of which areas are ALREADY connected regardless of ER, so
    cross-component preference actually targets real structural gaps
    rather than wasting pairings on areas that are already reachable
    through internal routes.

    Item-gated logical edges (SoulGate, Corridor, PrisonGate, SpiralGate)
    and one-way drops (PrisonExit) are NOT unioned: the structural
    algorithm needs to see the raw physical-traversal topology, not the
    omniscient post-item graph.  Including these inflates base
    connectivity (the entire backside collapses into one component via
    vanilla soul gates), which makes the reachability-first source check
    trivial and prevents the algorithm from prioritising pairings that
    bridge real structural gaps.
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

            # Skip item-gated and one-way exit types (see docstring).
            ex_type = getattr(exit_, 'exit_type', None)
            if ex_type in _BASE_UF_EXCLUDED_TYPES:
                continue

            dst_area = getattr(exit_.connected_region, 'game_area_id', None)
            if area_id is not None and dst_area is not None:
                uf.union(area_id, dst_area)

    return uf


def _generate_pairings_reachable_first(
    candidates: List[LM2Entrance],
    rng: random.Random,
    world,
    starting_exit_ids: Optional[Set] = None,
    base_uf: Optional['_UnionFind'] = None,
) -> List[Tuple[LM2Entrance, LM2Entrance]]:
    """
    TUNIC-style constructive pairing for full-random mode.

    Maintains a "reachable from starting_area" set as pairings commit.
    Sources must come from a currently-reachable area; targets prefer
    unreachable areas so each pairing expands the graph.

    The same hardcoded structural-constraint pre-pairings as
    _generate_pairings (Cliff, Cavern self-loop, Illusion, Altar,
    one-way drops, ReduceDeadEndStarts) are applied first — those rules
    are correct regardless of algorithm.

    Returns the same (LM2Entrance, LM2Entrance) tuple list as the
    legacy algorithm so downstream code (_apply_pairings, validators)
    is unchanged.
    """
    starting_area = getattr(world, 'starting_area', None)
    if base_uf is None or starting_area is None:
        # Reachability tracking needs both — fall back to legacy algorithm
        return _generate_pairings(candidates, rng, starting_exit_ids, base_uf)

    pool = list(candidates)
    rng.shuffle(pool)
    pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    _starting_exit_ids: Set = starting_exit_ids or set()
    uf = base_uf.copy()
    for e in pool:
        uf.find(_exit_area(e))  # register all areas

    def _reachable_set() -> Set:
        """Compute the set of areas currently in the same UF component
        as starting_area.  Recomputed after each pair commit because
        union() may have merged previously-isolated components."""
        root = uf.find(starting_area)
        return {a for a in uf.parent if uf.find(a) == root}

    reachable = _reachable_set()

    def _find_by_id(eid: ExitID) -> Optional[LM2Entrance]:
        return next((e for e in pool if e.game_exit_id == eid), None)

    def _commit_pair(e1: LM2Entrance, e2: LM2Entrance) -> None:
        nonlocal reachable
        pool.remove(e1)
        pool.remove(e2)
        pairings.append((e1, e2))
        a1, a2 = _exit_area(e1), _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)
        reachable = _reachable_set()

    def _pick_except(exclude_fn) -> Optional[LM2Entrance]:
        ok = [e for e in pool if not exclude_fn(e)]
        if ok:
            return rng.choice(ok)
        return rng.choice(pool) if pool else None

    def _same_area(e1: LM2Entrance, e2: LM2Entrance) -> bool:
        return _same_dungeon(e1, e2)

    # ── Hardcoded structural pre-pairings (mirror _generate_pairings) ──
    # Cliff
    cliff = _find_by_id(ExitID.fP02Left)
    if cliff and cliff in pool:
        partner = _pick_except(lambda e: (
            e is cliff
            or e.game_exit_id in INACCESSIBLE_EXITS
            or e.game_exit_id == ExitID.fL08Right
            or _would_self_loop(ExitID.fP02Left, e.game_exit_id)
            or e.game_exit_id in _starting_exit_ids
            or _same_area(cliff, e)
        ))
        if partner:
            _commit_pair(cliff, partner)

    # Cavern self-loop ban
    cavern_left = _find_by_id(ExitID.fP00Left)
    if cavern_left and cavern_left in pool:
        partner = _pick_except(lambda e: (
            e is cavern_left
            or e.game_exit_id == ExitID.fP00Right
            or e.game_exit_id == ExitID.fL08Right
            or _same_area(cavern_left, e)
        ))
        if partner:
            _commit_pair(cavern_left, partner)

    # Illusion gate self-loop ban
    ill_north = _find_by_id(ExitID.fL11GateN)
    if ill_north and ill_north in pool:
        partner = _pick_except(lambda e: (
            e is ill_north
            or e.game_exit_id == ExitID.fL11GateY0
            or _same_area(ill_north, e)
        ))
        if partner:
            _commit_pair(ill_north, partner)

    # Altar self-loop ban
    altar_left = _find_by_id(ExitID.fP01Left)
    if altar_left and altar_left in pool:
        partner = _pick_except(lambda e: (
            e is altar_left
            or e.game_exit_id == ExitID.fP01Right
            or _same_area(altar_left, e)
        ))
        if partner:
            _commit_pair(altar_left, partner)

    # One-way down ladders (avoid pairing with fL05Up, both inaccessible)
    for ow_id in [ExitID.f02Down, ExitID.f03Down2]:
        ow = _find_by_id(ow_id)
        if ow and ow in pool:
            partner = _pick_except(lambda e, _ow=ow: (
                e is _ow
                or e.game_exit_id == ExitID.fL05Up
                or _same_area(_ow, e)
            ))
            if partner:
                _commit_pair(ow, partner)

    # ReduceDeadEndStarts
    # The C# original guarantees ONE good exit out of the start area (break
    # after first successful pair).  LM2's reality with multi-exit start
    # areas (TS, RoY, IB) needs stricter: ALL starting-area exits must avoid
    # dead-end partners, not just one.  Otherwise the unprotected exits get
    # paired with dead-ends in the main loop, leaving the player with one
    # narrow escape route from the start.
    #
    # Extra exclusions beyond _generate_pairings parity:
    #  - virtual dead-end pairs (e.g. TS<->DF) — see _VIRTUAL_DEAD_END_START_PAIRS
    #  - other starting-area exits — when prevent_area_loops=False, _same_area
    #    only matches exact sub-areas (e.g. TSBottom != TSNeck), so without
    #    this guard step 596 could pair TS Bottom <-> TS Neck and leave zero
    #    outward exits from the starting region's gate exits.
    starting_partner_dungeons: Set[str] = set()
    if _starting_exit_ids:
        start_exits = [e for e in pool if e.game_exit_id in _starting_exit_ids]
        rng.shuffle(start_exits)
        for se in start_exits:
            if se not in pool:
                continue
            partner = _pick_except(lambda e, _se=se: (
                e is _se
                or e.game_exit_id in DEAD_END_EXITS
                or e.game_exit_id == ExitID.fP02Left
                or _would_self_loop(se.game_exit_id, e.game_exit_id)
                or _is_virtual_dead_end_start_pair(se.game_exit_id, e.game_exit_id)
                or e.game_exit_id in _starting_exit_ids
                or _same_area(_se, e)
            ))
            if partner is not None:
                _commit_pair(se, partner)
                d = _exit_dungeon(partner)
                if d is not None:
                    starting_partner_dungeons.add(d)

    # Inaccessible exits — pair up with accessible partners.
    # Must not pair with starting-area exits (mirrors Cliff's step-1 guard):
    # otherwise the player can be stranded with only late-game routes out.
    # Also avoid exits whose dungeon already absorbed a starting-area pairing —
    # otherwise we extend the dead-end through a passthrough dungeon (e.g.
    # TS Bottom <-> GoI Left, then Inferno Cavern <-> GoI Right makes the
    # entire GoI dungeon a 2-screen dead-end from start).
    inaccessible = [e for e in pool if e.game_exit_id in INACCESSIBLE_EXITS]
    rng.shuffle(inaccessible)
    for inac in inaccessible:
        if inac not in pool:
            continue
        accessible_partners = [e for e in pool
                               if e is not inac
                               and e.game_exit_id not in INACCESSIBLE_EXITS
                               and e.game_exit_id not in _starting_exit_ids
                               and _exit_dungeon(e) not in starting_partner_dungeons
                               and not _same_area(inac, e)]
        if not accessible_partners:
            # Relax starting-partner-dungeon constraint first
            accessible_partners = [e for e in pool
                                   if e is not inac
                                   and e.game_exit_id not in INACCESSIBLE_EXITS
                                   and e.game_exit_id not in _starting_exit_ids
                                   and not _same_area(inac, e)]
        if not accessible_partners:
            # Then relax same-area
            accessible_partners = [e for e in pool
                                   if e is not inac
                                   and e.game_exit_id not in INACCESSIBLE_EXITS
                                   and e.game_exit_id not in _starting_exit_ids]
        if not accessible_partners:
            # Last-resort: relax everything to avoid leaving inaccessibles unpaired
            accessible_partners = [e for e in pool
                                   if e is not inac
                                   and e.game_exit_id not in INACCESSIBLE_EXITS]
        if accessible_partners:
            partner = rng.choice(accessible_partners)
            _commit_pair(inac, partner)

    # ── Reachability-driven main loop ────────────────────────────────
    # Source MUST be in a currently-reachable area.  Target prefers an
    # unreachable area (expands the graph).  When forced to pick a
    # source from an unreachable area, do so but log it — caller may
    # detect via _validate_starting_cluster and retry.
    forced_unreachable_sources = 0
    rng.shuffle(pool)
    while len(pool) >= 2:
        sources_in_reach = [e for e in pool if _exit_area(e) in reachable]
        if sources_in_reach:
            e1 = rng.choice(sources_in_reach)
        else:
            # Graph stranded — no reachable source can pair an exit
            # Pick anything; the caller's validators will catch this
            e1 = rng.choice(pool)
            forced_unreachable_sources += 1
        pool.remove(e1)

        # Prefer target in an unreachable area (expands graph)
        unreached_targets = [e for e in pool
                             if _exit_area(e) not in reachable
                             and not _same_area(e1, e)]
        if unreached_targets:
            e2 = rng.choice(unreached_targets)
        else:
            different_area = [e for e in pool if not _same_area(e1, e)]
            e2 = rng.choice(different_area) if different_area else pool[-1]

        pool.remove(e2)
        pairings.append((e1, e2))
        a1, a2 = _exit_area(e1), _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)
        reachable = _reachable_set()

    if forced_unreachable_sources:
        _log(f"[ER] Reachability-first pairing: {forced_unreachable_sources} "
              f"forced from unreachable areas (validator may retry)")
    if uf.num_components > 1:
        _log(f"[ER] WARNING (constructive): {uf.num_components} disconnected "
              f"area components after pairing")

    return _repair_same_dungeon_pairs(pairings, rng)


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
    # Stricter than C# ReduceDeadEndStarts: ALL starting-area exits must
    # avoid dead-end partners, not just one.  See _generate_pairings_reachable_first
    # for the full rationale (LM2 multi-exit start areas need it).
    starting_partner_dungeons: Set[str] = set()
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
                or _is_virtual_dead_end_start_pair(se.game_exit_id, e.game_exit_id)
                or e.game_exit_id in _starting_exit_ids
                or _same_area(_se, e)
            ))
            if partner is not None:
                _pair(se, partner)
                d = _exit_dungeon(partner)
                if d is not None:
                    starting_partner_dungeons.add(d)

    # ── 6. Priority-pair inaccessible exits ───────────────────────────────
    # Inaccessibles (Endless Corridor, Inferno Cavern, etc.) must not pair
    # with starting-area exits: that would leave the player stranded with
    # only late-game routes out (matches Cliff's step-1 guard).  Cliff
    # itself was already removed in step 1.
    # Also avoid exits in dungeons that absorbed a starting-area pairing —
    # otherwise we extend the dead-end by 1 hop through a passthrough dungeon
    # (e.g. TS Bottom <-> GoI Left, Inferno Cavern <-> GoI Right).
    inaccessible = [e for e in pool if e.game_exit_id in INACCESSIBLE_EXITS]
    rng.shuffle(inaccessible)
    for inac in inaccessible:
        if inac not in pool:
            continue
        accessible_partners = [e for e in pool
                               if e is not inac
                               and e.game_exit_id not in INACCESSIBLE_EXITS
                               and e.game_exit_id not in _starting_exit_ids
                               and _exit_dungeon(e) not in starting_partner_dungeons
                               and not _same_area(inac, e)]
        if not accessible_partners:
            # Relax starting-partner-dungeon constraint first
            accessible_partners = [e for e in pool
                                   if e is not inac
                                   and e.game_exit_id not in INACCESSIBLE_EXITS
                                   and e.game_exit_id not in _starting_exit_ids
                                   and not _same_area(inac, e)]
        if not accessible_partners:
            # Then relax same-area
            accessible_partners = [e for e in pool
                                   if e is not inac
                                   and e.game_exit_id not in INACCESSIBLE_EXITS
                                   and e.game_exit_id not in _starting_exit_ids]
        if not accessible_partners:
            # Last-resort: relax everything to avoid leaving inaccessibles unpaired
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
        _log(f"[ER] WARNING: {uf.num_components} disconnected area components "
              f"after pairing (structural islands likely)")

    if pool:
        _log(f"[ER] WARNING: {len(pool)} exit(s) left unpaired: "
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
                    and starting_area == AreaID.VoD)
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
                        and starting_area == AreaID.VoD)
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
        _log(f"[ER-H] WARNING: {len(right_doors)} right door(s) unpaired")
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
        _log(f"[ER-V] WARNING: {len(up_ladders)} up ladder(s) unpaired")
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
                  and not _is_virtual_dead_end_start_pair(starting_eid, g.game_exit_id)
                  and not _same_dungeon(starter, g)]
            if not ok:
                # Relax dungeon constraint
                ok = [g for g in gates
                      if g.game_exit_id not in DEAD_END_EXITS
                      and not _start_loop_check(starting_eid, g.game_exit_id)
                      and not _is_virtual_dead_end_start_pair(starting_eid, g.game_exit_id)]
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
            _log(f"[ER-G] WARNING: gate '{g1.name}' unpaired (odd count)")
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
        _log(f"[ER-G] WARNING: {len(priority_gates)} priority gate(s) unpaired")

    return _repair_same_dungeon_pairs(pairings, rng)


# ── Unique transitions (same-pool, when enabled in separate mode) ─────

def _pair_unique_pool(
    unique_pool: List[LM2Entrance],
    rng: random.Random,
    world,
    base_uf: Optional['_UnionFind'] = None,
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

    uf = base_uf.copy() if base_uf is not None else _UnionFind()
    for e in unique_pool:
        uf.find(_exit_area(e))

    # Altar anti-self-loop
    altar_left = _find_in(pool, ExitID.fP01Left)
    if altar_left and len(pool) >= 2:
        pool.remove(altar_left)
        ok = [e for e in pool if e.game_exit_id != ExitID.fP01Right]
        if ok:
            partner = rng.choice(ok)
            pool.remove(partner)
            pairings.append((altar_left, partner))
            a1, a2 = _exit_area(altar_left), _exit_area(partner)
            if a1 is not None and a2 is not None:
                uf.union(a1, a2)
        else:
            pool.append(altar_left)

    while len(pool) >= 2:
        e1 = pool.pop(rng.randrange(len(pool)))
        e2 = rng.choice(pool)
        pool.remove(e2)
        pairings.append((e1, e2))
        a1, a2 = _exit_area(e1), _exit_area(e2)
        if a1 is not None and a2 is not None:
            uf.union(a1, a2)

    if pool:
        _log(f"[ER-U] WARNING: {len(pool)} unique exit(s) unpaired (odd count)")

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

    # Use a cumulative UF across pools so that later pools know about
    # connections established by earlier pools (improves connectivity).
    cumulative_uf = base_uf.copy()

    all_pairings: List[Tuple[LM2Entrance, LM2Entrance]] = []

    def _update_cumulative_uf(pairs):
        for e1, e2 in pairs:
            a1, a2 = _exit_area(e1), _exit_area(e2)
            if a1 is not None and a2 is not None:
                cumulative_uf.union(a1, a2)

    if opts.horizontal_entrances:
        pairs = _pair_horizontal_bipartite(
            by_type.get(ExitType.LeftDoor, []),
            by_type.get(ExitType.RightDoor, []),
            rng, world, cumulative_uf,
        )
        all_pairings.extend(pairs)
        _update_cumulative_uf(pairs)
        if pairs:
            _log(f"[ER] Horizontal pool: {len(pairs)} pairs")

    if opts.vertical_entrances:
        pairs = _pair_vertical_bipartite(
            by_type.get(ExitType.UpLadder, []),
            by_type.get(ExitType.DownLadder, []),
            rng, world, cumulative_uf,
        )
        all_pairings.extend(pairs)
        _update_cumulative_uf(pairs)
        if pairs:
            _log(f"[ER] Vertical pool: {len(pairs)} pairs")

    if opts.gate_entrances:
        pairs = _pair_gates_pool(
            by_type.get(ExitType.Gate, []),
            rng, world, cumulative_uf,
        )
        all_pairings.extend(pairs)
        _update_cumulative_uf(pairs)
        if pairs:
            _log(f"[ER] Gate pool: {len(pairs)} pairs")

    if opts.unique_transitions:
        unique: List[LM2Entrance] = []
        for t in (ExitType.OneWay, ExitType.Pyramid, ExitType.Start, ExitType.Altar):
            unique.extend(by_type.get(t, []))
        if len(unique) >= 2:
            pairs = _pair_unique_pool(unique, rng, world, cumulative_uf)
            all_pairings.extend(pairs)
            _update_cumulative_uf(pairs)
            if pairs:
                _log(f"[ER] Unique pool: {len(pairs)} pairs")

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
    player = world.player
    prog = state.prog_items[player]

    def add(name: str, count: int = 1) -> None:
        prog[name] = prog.get(name, 0) + count

    # Precollected items
    for item in world.multiworld.precollected_items[player]:
        add(item.name)

    # All pool items
    for item in world.multiworld.itempool:
        if item.player == player:
            add(item.name)

    # Any already-placed items owned by this player
    for loc in world.multiworld.get_locations(player):
        if loc.item is not None and loc.item.player == player:
            add(loc.item.name)

    # Logic flags / synthetic progression
    for flag_name in LOGIC_FLAG_MAP.keys():
        add(flag_name)

    prog["Guardians"] = max(prog.get("Guardians", 0), 9)
    prog["Dissonance"] = max(prog.get("Dissonance", 0), 6)

    if hasattr(state, "stale"):
        state.stale[player] = True

    return state


def _build_items_only_state(world):
    """
    Like _build_omniscient_state but no events/flags — only the static
    item pool (precollected + itempool).  Used as a base state to copy
    from in _validate_region_reachability so we avoid re-collecting all
    items on every ER retry attempt.
    """
    from BaseClasses import CollectionState

    state = CollectionState(world.multiworld)
    player = world.player
    prog = state.prog_items[player]

    def add(name: str, count: int = 1) -> None:
        prog[name] = prog.get(name, 0) + count

    for item in world.multiworld.precollected_items[player]:
        add(item.name)

    for item in world.multiworld.itempool:
        if item.player == player:
            add(item.name)

    if hasattr(state, "stale"):
        state.stale[player] = True

    return state


def _reset_state_for_attempt(state, player: int) -> None:
    """
    Reset reachability/event caches so a base CollectionState (built once
    with all items collected) can be reused after the entrance graph has
    changed between ER attempts.  Items themselves stay; only the cached
    sphere-sweep results are cleared.
    """
    state.stale[player] = True
    state.reachable_regions[player].clear()
    state.blocked_connections[player].clear()
    # locations_checked tracks event-collection per sphere-sweep — must
    # restart fresh each attempt.
    state.locations_checked = set()
    state.path = {}


def _validate_region_reachability(world, base_state=None) -> Tuple[bool, List[str]]:
    """
    Sphere-sweep validation that mirrors AP's fulfills_accessibility().

    Starts with all POOL items collected (simulating optimal fill placement)
    but does NOT force-set logic-flag events (bosses, shortcuts, guardians,
    etc.).  Events are collected dynamically as their locations become
    reachable, exactly as happens during the real fill sweep.

    This catches circular event dependencies that the old omniscient
    approach missed: e.g. Area A needs an event from Area B, but Area B
    is only reachable through Area A.

    Performance: if `base_state` (an items-only CollectionState built by
    _build_items_only_state) is supplied, it is copied and reset rather
    than re-collecting all itempool items each call.  This is the hot
    path during ER retry loops.

    Returns (is_valid, list_of_unreachable_location_names).
    """
    from BaseClasses import CollectionState
    player = world.player

    if base_state is not None:
        state = base_state.copy()
        _reset_state_for_attempt(state, player)
    else:
        state = CollectionState(world.multiworld)
        for item in world.multiworld.precollected_items[player]:
            state.collect(item)
        for item in world.multiworld.itempool:
            if item.player == player:
                state.collect(item)
        if hasattr(state, 'stale'):
            state.stale[player] = True

    # Sphere-sweep: find reachable locations, collect their events, repeat
    remaining = []
    for loc in world.multiworld.get_locations(player):
        if loc.parent_region is not None:
            remaining.append(loc)

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

        # Collect events from newly reachable locations
        collected_new = False
        for loc in sphere:
            if loc.item is not None and loc.item.player == player:
                state.collect(loc.item, True, loc)
                collected_new = True

        if hasattr(state, 'stale') and collected_new:
            state.stale[player] = True

    unreachable = [loc.name for loc in remaining]
    return len(unreachable) == 0, unreachable


# ── Starting cluster viability check ─────────────────────────────────

# Minimum number of ACCESSIBLE locations (loc.can_reach) in sphere-0.
# Must be high enough that after pre-fills (shops, mantras, research,
# logic flags, dissonance), enough UNFILLED slots remain for the fill
# to bootstrap progression. 
_MIN_STARTING_LOCATIONS = 8

# Minimum number of UNFILLED accessible locations in sphere-0.
# This is the actual bottleneck: the fill algorithm needs empty slots
# to place progression items.  Pre-fills (shops, mantras, research,
# dissonance, logic flags) consume slots before the fill even starts.
_MIN_STARTING_UNFILLED = 4

# Minimum number of distinct REACHABLE AREAS (regions with unique
# game_area_id) in sphere-0.  Prevents configurations where many
# locations are accessible but all in 1-2 areas (tiny cluster that
# the fill can't break out of even with the unfilled minimum met).
_MIN_STARTING_AREAS = 3

def _validate_starting_cluster(world, omniscient_base=None) -> Tuple[bool, str]:
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

    `omniscient_base` is an optional reusable CollectionState (built once
    by the caller via _build_omniscient_state) used for the guardian-
    escape check below.  If supplied, it is copied per call instead of
    rebuilt — saves ~150ms per ER attempt.
    """
    from BaseClasses import CollectionState

    state = CollectionState(world.multiworld)
    player = world.player
    prog = state.prog_items[player]

    def add(name: str, count: int = 1) -> None:
        prog[name] = prog.get(name, 0) + count

    for item in world.multiworld.precollected_items[player]:
        add(item.name)

    if hasattr(state, "stale"):
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
        # State with everything EXCEPT guardian kills.  Reuse the cached
        # omniscient state when the caller hands one in — only the
        # reachability cache (which depends on current pairings) needs
        # invalidation, the item set is identical every attempt.
        if omniscient_base is not None:
            no_kills = omniscient_base.copy()
            _reset_state_for_attempt(no_kills, player)
        else:
            no_kills = _build_omniscient_state(world)
        no_kills.prog_items[player]["Guardians"] = 0
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
        _log(f"[ER] Odd exit count, leaving '{dropped.name}' in vanilla")

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
        _log(f"[ER] ReduceDeadEndStarts: starting area {starting_area}, "
              f"exits in pool: {[str(eid) for eid in starting_exit_ids]}")

    if not full_random:
        from .regions import ExitType
        pool_summary = defaultdict(int)
        for e in candidates:
            pool_summary[e.exit_type] += 1
        _log(f"[ER] Separate-pool mode: "
              + ", ".join(f"{t.value}={n}" for t, n in sorted(pool_summary.items(),
                          key=lambda x: x[0].value)))

    # Save vanilla connections: exit -> target region
    vanilla_targets: Dict[int, object] = {}
    for e in candidates:
        vanilla_targets[id(e)] = e.connected_region

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
            _log(f"[ER] Restored {restored} unpaired exit(s) to vanilla")

    last_pairings = None
    last_unreachable: List[str] = []
    last_cluster_msg: str = ""

    # Build base connectivity UF from non-shuffled connections (built once,
    # cloned per attempt).  This tells pairing functions which areas are
    # ALREADY connected through internal exits, corridors, etc.
    shuffled_ids = {e.game_exit_id for e in candidates
                    if getattr(e, 'game_exit_id', None) is not None}
    base_uf = _build_base_uf(world, shuffled_ids)

    # Build base CollectionStates ONCE — items and precollected don't
    # change between ER attempts, only entrance pairings do.  Validators
    # accept a base state, copy it, and reset its reachability cache so
    # only the cheap part (sphere-sweep) runs per attempt.  Pre-fix this
    # cost ~150ms × 100 attempts; post-fix ~30ms each.
    items_only_base = _build_items_only_state(world)
    omniscient_base = _build_omniscient_state(world)

    for attempt in range(MAX_ATTEMPTS):
        _disconnect_all()

        # ── Generate pairings ─────────────────────────────────────────
        # Full-random uses TUNIC-style constructive pairing (source must
        # be reachable from start); separate-pool mode dispatches per
        # exit type.  _generate_pairings_reachable_first falls back to
        # the legacy _generate_pairings when starting_area is None.
        if full_random:
            pairings = _generate_pairings_reachable_first(
                candidates, rng, world, starting_exit_ids,
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
        valid, unreachable = _validate_region_reachability(world,
                                                           base_state=items_only_base)
        last_unreachable = unreachable

        if unreachable:
            accessibility = world.options.accessibility
            if accessibility == accessibility.option_minimal:
                # Minimal: tolerate unreachable if enough locations
                # remain for progression items to be placed.
                progression_count = sum(
                    1 for item in world.multiworld.itempool
                    if item.player == world.player and item.advancement
                )
                total_locs = sum(
                    1 for _ in world.multiworld.get_locations(world.player)
                )
                reachable_count = total_locs - len(unreachable)
                if reachable_count < progression_count + 10:
                    if attempt < 5 or attempt % 25 == 0:
                        _log(f"[ER] Attempt {attempt + 1}: only "
                              f"{reachable_count} reachable locations for "
                              f"{progression_count} progression items, "
                              f"retrying...")
                    continue
                # Enough reachable — accept with warning
                if attempt < 5 or attempt % 25 == 0:
                    _log(f"[ER] Attempt {attempt + 1}: tolerating "
                          f"{len(unreachable)} unreachable "
                          f"({reachable_count} reachable for "
                          f"{progression_count} progression)")
            else:
                # Full/Items: zero unreachable locations allowed
                if attempt < 5 or attempt % 25 == 0:
                    _log(f"[ER] Attempt {attempt + 1}: {len(unreachable)} "
                          f"unreachable (e.g. {unreachable[:3]}), retrying...")
                continue

        # ── Validation 2: starting cluster viability ──────────────────
        # With ONLY precollected items, is the reachable cluster large
        # enough and open (has outward exits) to bootstrap progression?
        # Catches the case where omniscient check passes but the fill
        # can't place enough items to break out of a tiny starting area.
        cluster_ok, cluster_msg = _validate_starting_cluster(world,
                                                              omniscient_base=omniscient_base)
        last_cluster_msg = cluster_msg

        if not cluster_ok:
            if attempt < 5 or attempt % 25 == 0:
                _log(f"[ER] Attempt {attempt + 1}: {cluster_msg}, retrying...")
            continue

        # Both checks passed
        if attempt > 0:
            _log(f"[ER] Structural ER succeeded on attempt {attempt + 1} "
                  f"({cluster_msg})")
        break
    else:
        raise RuntimeError(
            f"Structural ER failed after {MAX_ATTEMPTS} attempts. "
            f"Last: {len(last_unreachable)} unreachable, "
            f"cluster: {last_cluster_msg}"
        )

    # ── Build pairing records for seed file & spoiler log ────────────
    _build_pairing_records(world, last_pairings)

    # Store the set of locations that were already unreachable after structural ER.
    # Soul gate validation will use this to avoid rejecting configurations that
    # don't make things WORSE than the structural layout already is.
    world._structural_unreachable = set(last_unreachable)

    # ── Print pairings ───────────────────────────────────────────────
    _log(f"\n[ER] === ENTRANCE PAIRINGS ===")
    for src, tgt in sorted(world._er_name_pairings):
        _log(f"[ER]   {src}  <->  {tgt}")
    _log(f"[ER] === END PAIRINGS ({len(world._er_name_pairings)} pairs) ===\n")

    # NOTE: IBMain escape route is logged AFTER soul gates are placed
    # (in __init__.py) so the graph includes soul gate connections.


# ============================================================
# Soul Gate Randomizer
# ============================================================

class SoulGateRandomizer:
    """
    Handles soul gate pairing and GuardianKills(N) logic injection.

    Runs after custom_structural_er.  Soul gates carry dynamic
    GuardianKills(N) thresholds that the structural ER pool has no
    model for, so they are paired separately with their own retry loop.
    """

    def __init__(self, rng: random.Random, entrances: List[LM2Entrance], world):
        self.rng = rng
        self.entrances = entrances
        self.world = world
        self.options = world.options
        self.soul_gate_pairs: List[SoulGatePair] = []

    def randomize(self) -> bool:
        """Randomize soul gates with retry logic. Returns True on success, False if exhausted."""
        if self.options.soul_gate_entrances:
            return self._randomize_soul_gate_entrances_retry()
        # Value-only mode: vanilla pairings, but values may still change
        # because of value/include-nine shuffling or the random_dissonance
        # N9 floor.  Skip entirely when none of those apply.
        needs_value_pass = (
            self.options.random_soul_gate_value
            or self.options.include_nine_soul_gates
            or self.options.random_dissonance
        )
        if not needs_value_pass:
            return True
        return self._randomize_soul_gate_values_retry()

    def _log_soul_gate_pairings(self, label: str = ""):
        """Print current soul gate pairings for debugging."""
        if not self.soul_gate_pairs:
            _log(f"[ER-SG] {label}No soul gate pairs.")
            return
        _log(f"[ER-SG] {label}Soul gate pairings ({len(self.soul_gate_pairs)} pairs):")
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
            _log(f"[ER-SG]   {name1} <-> {name2}  (cost: {sgp.soul_amount})")

    def _get_exits_of_type(self, exit_type: ExitType) -> List[LM2Entrance]:
        return [e for e in self.entrances if e.exit_type == exit_type]

    # ============================================================
    # Soul gate randomization
    # ============================================================

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

    def _update_epg_logic(self, gate1: LM2Entrance, gate2: LM2Entrance, soul_amount: int,
                            force_override: bool = False):
        """Update EPG gates puzzle logic when the EPG soul gate is randomized."""
        for exit_ in self.entrances:
            if hasattr(exit_, 'connecting_area') and exit_.connecting_area == AreaID.EPDHel:
                if force_override:
                    self._override_guardian_kills(exit_, soul_amount)
                if gate1.game_exit_id == ExitID.f04GateN6 or gate2.game_exit_id == ExitID.f04GateN6:
                    self._append_logic_outside_parens(
                        exit_, f'and IsDead(Vidofnir) and GuardianKills({soul_amount})')
                else:
                    self._append_logic_outside_parens(exit_, f'and GuardianKills({soul_amount})')
                break

    # ============================================================
    # Speculative gate placement
    #
    # Place each soul gate pair one at a time.  After each placement,
    # run the kill-simulation check; if the new constraint cuts off a
    # critical region, roll back and try a different (partner, kills)
    # combination.
    # ============================================================

    def _kill_simulation_check(self) -> bool:
        """
        Return True iff the kill-progression simulation reaches every
        guardian location in some valid order.  Treats unplaced gates
        as freely traversable (vanilla logic, no GuardianKills) so this
        works correctly mid-placement: if the incremental state passes,
        committing further gates can only add constraints, never remove
        them — a failure here is a hard signal to backtrack.
        """
        kill_costs = self._build_kill_costs()
        guardian_locs = [
            loc for loc in self.world.multiworld.get_locations(self.world.player)
            if hasattr(loc, 'location_type')
                and loc.location_type == LocationType.Guardian
        ]

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

        return all(
            loc.parent_region is not None
            and loc.parent_region.name in reachable
            for loc in guardian_locs
        )

    def _save_gate_pair_state(self, gate1, gate2, epd_hel_exit) -> dict:
        """Snapshot mutable state so a placement can be rolled back."""
        return {
            'g1_region': gate1.connected_region,
            'g1_logic':  gate1._original_logic,
            'g2_region': gate2.connected_region,
            'g2_logic':  gate2._original_logic,
            'epd_logic': epd_hel_exit._original_logic if epd_hel_exit else None,
        }

    def _restore_gate_pair_state(self, gate1, gate2, epd_hel_exit, snap: dict) -> None:
        """Reverse _apply_gate_pair using the snapshot."""
        # Restore gate1
        if gate1.connected_region is not None:
            try:
                gate1.connected_region.entrances.remove(gate1)
            except ValueError:
                pass
            gate1.connected_region = None
        self._reset_logic(gate1, snap['g1_logic'])
        if snap['g1_region'] is not None:
            gate1.connect(snap['g1_region'])

        # Restore gate2
        if gate2.connected_region is not None:
            try:
                gate2.connected_region.entrances.remove(gate2)
            except ValueError:
                pass
            gate2.connected_region = None
        self._reset_logic(gate2, snap['g2_logic'])
        if snap['g2_region'] is not None:
            gate2.connect(snap['g2_region'])

        # Restore EPDHel internal exit logic if it was touched
        if epd_hel_exit is not None and snap['epd_logic'] is not None:
            self._reset_logic(epd_hel_exit, snap['epd_logic'])

    def _apply_gate_pair(self, gate1, gate2, soul_amount: int,
                          swap_regions: bool = True,
                          force_override: bool = False) -> None:
        """
        Execute one gate pairing: append GuardianKills + extra logic,
        and optionally swap target regions.

        When force_override is True, also rewrites any existing
        GuardianKills(N) literal in each gate's vanilla logic so that the
        new value actually lowers the cost.  Required when the floored N9
        amount must take effect even with random_soul_gate_value off
        (Setting(Random Soul Gates) is False, so the original
        GuardianKills(N) clause would otherwise dominate).
        """
        if force_override:
            self._override_guardian_kills(gate1, soul_amount)
            self._override_guardian_kills(gate2, soul_amount)

        self._append_logic_outside_parens(gate1, f'and GuardianKills({soul_amount})')
        self._append_logic_outside_parens(gate2, f'and GuardianKills({soul_amount})')
        self._fix_soul_gate_logic(gate1, gate2)
        self._fix_soul_gate_logic(gate2, gate1)

        if swap_regions:
            saved1 = gate1.parent_region
            saved2 = gate2.parent_region
            gate1.disconnect()
            gate2.disconnect()
            gate1.connect(saved2)
            gate2.connect(saved1)

        if (gate1.game_exit_id == ExitID.f14GateN6
                or gate2.game_exit_id == ExitID.f14GateN6):
            self._update_epg_logic(gate1, gate2, soul_amount,
                                    force_override=force_override)

    def _valid_partners_for(self, gate1, candidate_pool):
        """
        Apply the C# pair-rejection rules (f03GateN9 / f13GateN9 special
        cases) to filter candidate_pool down to valid partners for gate1.
        Falls back to the unfiltered pool if filtering empties it.
        """
        valid = []
        for g in candidate_pool:
            if g is gate1:
                continue
            # f03GateN9 must not pair with f08GateN8 (or f14GateN6 in
            # random-dissonance mode)
            if (gate1.game_exit_id == ExitID.f03GateN9
                    and (g.game_exit_id == ExitID.f08GateN8
                         or (g.game_exit_id == ExitID.f14GateN6
                             and self.options.random_dissonance))):
                continue
            # f13GateN9 must pair with a dead-end / inaccessible exit
            if (gate1.game_exit_id == ExitID.f13GateN9
                    and g.game_exit_id not in DEAD_END_EXITS
                    and g.game_exit_id not in INACCESSIBLE_EXITS):
                continue
            valid.append(g)
        return valid if valid else [g for g in candidate_pool if g is not gate1]

    def _valid_amounts_for(self, gate1, gate2, soul_amounts):
        """Apply the f14GateN6 9-soul restriction in non-random-dissonance/
        full-accessibility modes (matches C# behaviour)."""
        valid = [
            a for a in soul_amounts
            if not (
                (self.options.accessibility.value == 2
                 or not self.options.random_dissonance)
                and (gate1.game_exit_id == ExitID.f14GateN6
                     or gate2.game_exit_id == ExitID.f14GateN6)
                and a == 9
            )
        ]
        return valid if valid else list(soul_amounts)

    def _floor_to_available_gate_value(self, required_guardians: int, allowed_amounts: List[int]) -> int:
        """
        Return the highest available soul-gate value that is <= required_guardians.
        Falls back to the lowest available value if required_guardians is below range.
        """
        allowed = sorted({int(a) for a in allowed_amounts})
        if not allowed:
            return 1

        for value in reversed(allowed):
            if value <= required_guardians:
                return value

        return allowed[0]

    def _randomize_soul_gate_entrances_speculative(self, epd_hel_exit) -> bool:
        """
        Greedy per-pair placement with rollback.  Returns True if all
        gates placed successfully, False if any gate has no valid
        (partner, soul_amount) combination.

        Caller is responsible for resetting all gate state to vanilla
        before invocation (so this routine starts from a clean slate).
        """
        gates = list(self._get_exits_of_type(ExitType.SoulGate))
        self.rng.shuffle(gates)

        if self.options.random_soul_gate_value:
            soul_amounts = [1, 2, 3, 5]
        else:
            soul_amounts = [1, 2, 2, 3, 3, 5, 5, 5]

        # ── 9-soul gate handling ──
        priority_gates = []
        if self.options.include_nine_soul_gates:
            soul_amounts.append(9)
            priority_gates = [g for g in gates
                              if g.game_exit_id in (ExitID.f03GateN9,
                                                     ExitID.f13GateN9)]
            for g in priority_gates:
                gates.remove(g)
        else:
            # Force-pair the two 9-soul gates with each other when the
            # nine-soul option is OFF.  This is a hardcoded structural
            # decision (no speculation needed; the C# port did this
            # unconditionally).
            g1 = next((g for g in gates if g.game_exit_id == ExitID.f03GateN9), None)
            g2 = next((g for g in gates if g.game_exit_id == ExitID.f13GateN9), None)
            if g1 and g2:
                gates.remove(g1)
                gates.remove(g2)
                # With random_dissonance, the final-boss gate has to be
                # accessible based on RequiredGuardians, not the literal
                # 9 the gate is hardcoded to.
                if self.options.random_dissonance:
                    nine_amount = self._floor_to_available_gate_value(
                        int(self.options.required_guardians.value),
                        [1, 2, 3, 5, 9])
                else:
                    nine_amount = 9
                snap = self._save_gate_pair_state(g1, g2, epd_hel_exit)
                self._apply_gate_pair(
                    g1, g2, nine_amount,
                    force_override=self.options.random_dissonance)
                if not self._kill_simulation_check():
                    self._restore_gate_pair_state(g1, g2, epd_hel_exit, snap)
                    return False
                self.soul_gate_pairs.append(SoulGatePair(g1.game_exit_id,
                                                         g2.game_exit_id, nine_amount))

        if not self.options.random_soul_gate_value:
            soul_amounts.sort()
        else:
            self.rng.shuffle(soul_amounts)

        # ── Main placement loop ─────────────────────────────────────────
        # Pop one "gate1" at a time, try (partner, soul_amount) combos
        # until one passes the kill-simulation check.
        while gates or priority_gates:
            if len(gates) + len(priority_gates) < 2:
                break

            if priority_gates:
                gate1 = self.rng.choice(priority_gates)
                priority_gates.remove(gate1)
            else:
                gate1 = self.rng.choice(gates)
                gates.remove(gate1)

            # Build (partner, soul_amount) candidate list, randomized
            partners = self._valid_partners_for(gate1, gates)
            self.rng.shuffle(partners)

            placed = False
            tried = 0
            for gate2 in partners:
                amounts = self._valid_amounts_for(gate1, gate2, soul_amounts)
                forced_amount = None
                is_nine_pair = (
                    gate1.game_exit_id == ExitID.f03GateN9
                    or gate2.game_exit_id == ExitID.f03GateN9
                )
                if self.options.random_dissonance and is_nine_pair:
                    required_guardians = int(self.options.required_guardians.value)
                    # Floor against the canonical soul-gate values so the
                    # result is always a sane game-mechanic number even
                    # when soul_amounts contains duplicates / N9 isn't in
                    # the active pool.
                    forced_amount = self._floor_to_available_gate_value(
                        required_guardians, [1, 2, 3, 5, 9])
                    # When using the multiset (random_soul_gate_value off),
                    # the floored value still has to be drawable from the
                    # remaining pool for the bookkeeping below to work.
                    if (not self.options.random_soul_gate_value
                            and forced_amount not in soul_amounts):
                        forced_amount = self._floor_to_available_gate_value(
                            required_guardians, amounts)

                if forced_amount is not None:
                    amount_order = [forced_amount]
                elif self.options.random_soul_gate_value:
                    amount_order = list(amounts)
                    self.rng.shuffle(amount_order)
                else:
                    # Deterministic order: lowest first.  The current
                    # value will be removed from the pool on success.
                    amount_order = list(amounts)

                for soul_amount in amount_order:
                    snap = self._save_gate_pair_state(gate1, gate2, epd_hel_exit)
                    # When forcing the N9 floor, also rewrite the vanilla
                    # GuardianKills(9) literal so the floor isn't masked
                    # by the original constraint when Setting(Random Soul
                    # Gates) is False.
                    self._apply_gate_pair(
                        gate1, gate2, soul_amount,
                        force_override=(forced_amount is not None
                                          and self.options.random_dissonance
                                          and is_nine_pair))
                    tried += 1

                    if self._kill_simulation_check():
                        # Commit
                        gates.remove(gate2)
                        if not self.options.random_soul_gate_value:
                            if soul_amount in soul_amounts:
                                soul_amounts.remove(soul_amount)
                        self.soul_gate_pairs.append(
                            SoulGatePair(gate1.game_exit_id,
                                         gate2.game_exit_id, soul_amount))
                        placed = True
                        break

                    self._restore_gate_pair_state(gate1, gate2, epd_hel_exit, snap)

                if placed:
                    break

            if not placed:
                _log(f"[ER-SG] Speculative placement: no valid pair for "
                      f"{gate1.name} after {tried} tries — signaling reset")
                return False

        return True

    def _randomize_soul_gate_entrances_retry(self):
        """
        Retry wrapper.  Tries speculative placement first (fast and
        usually succeeds in 1 pass).  If it fails because of an
        unfortunate gate1 ordering, resets all gate state and retries
        up to MAX_ATTEMPTS times with a fresh shuffle.
        """
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

        # Cache items-only state once for the inner validation loop —
        # items don't change between gate-pairing attempts, only the
        # gate connections do.  Saves ~100ms per attempt × 50 attempts.
        items_only_base = _build_items_only_state(self.world)

        def _reset_all_gates_to_vanilla():
            for gate in gates:
                saved_region, saved_logic = vanilla_state[gate.game_exit_id]
                if gate.connected_region is not None:
                    if gate in gate.connected_region.entrances:
                        gate.connected_region.entrances.remove(gate)
                    gate.connected_region = None
                self._reset_logic(gate, saved_logic)
                gate.access_rule = gate.can_access
                gate.connect(saved_region)
            if epd_hel_exit is not None and epd_hel_vanilla_logic is not None:
                self._reset_logic(epd_hel_exit, epd_hel_vanilla_logic)
            self.soul_gate_pairs.clear()

        for attempt in range(MAX_ATTEMPTS):
            _reset_all_gates_to_vanilla()

            if not self._randomize_soul_gate_entrances_speculative(epd_hel_exit):
                _log(f"[ER] Soul gate speculative attempt {attempt + 1} "
                      f"could not place all gates, retrying with fresh shuffle...")
                continue

            # All gates placed.  Final structural check (catches the rare
            # case where kill simulation passes but full-region accessibility
            # would still leave non-guardian regions unreachable).
            valid, unreachable = _validate_region_reachability(self.world,
                                                                base_state=items_only_base)
            if not valid:
                structural = getattr(self.world, '_structural_unreachable', set())
                new_unreachable = [loc for loc in unreachable if loc not in structural]
                if new_unreachable:
                    _log(f"[ER] Soul gate attempt {attempt + 1}: post-gate "
                          f"logic made {len(new_unreachable)} NEW locations "
                          f"unreachable (e.g. {new_unreachable[:3]}), retrying...")
                    continue

            if attempt > 0:
                _log(f"[ER] Soul gate succeeded on attempt {attempt + 1}")
            self._log_soul_gate_pairings()
            return True

        _log(f"[ER] Soul gate randomization failed after {MAX_ATTEMPTS} attempts "
              f"-- structural layout incompatible with soul gates.")
        self._log_soul_gate_pairings("LAST FAILED: ")
        return False

    # ============================================================
    # Value-only randomization (vanilla pairs, shuffled costs)
    #
    # Used when soul_gate_entrances is OFF but value/include-nine
    # shuffling or the random_dissonance N9 floor is requested.  The
    # gates keep their vanilla destinations; only the GuardianKills cost
    # is rewritten.
    # ============================================================

    def _randomize_soul_gate_values_speculative(self, epd_hel_exit) -> bool:
        """
        Walk the canonical vanilla pair list, assign each pair a soul
        cost according to the active options, and apply it via
        _apply_gate_pair(swap_regions=False).  Each placement is
        validated with the same kill-simulation check as the entrance
        speculative loop and rolled back on failure.

        Returns True if every pair found a working assignment.
        """
        gate_by_id = {
            g.game_exit_id: g
            for g in self._get_exits_of_type(ExitType.SoulGate)
        }

        nine_pair_ids = (ExitID.f03GateN9, ExitID.f13GateN9)
        non_nine_pairs: List[Tuple[LM2Entrance, LM2Entrance]] = []
        nine_pair: Optional[Tuple[LM2Entrance, LM2Entrance]] = None
        for a, b in _VANILLA_SOUL_GATE_PAIRS:
            ga = gate_by_id.get(a)
            gb = gate_by_id.get(b)
            if ga is None or gb is None:
                continue
            if (a, b) == nine_pair_ids:
                nine_pair = (ga, gb)
            else:
                non_nine_pairs.append((ga, gb))

        if self.options.random_soul_gate_value:
            soul_amounts: List[int] = [1, 2, 3, 5]
        else:
            soul_amounts = [1, 2, 2, 3, 3, 5, 5, 5]

        # Determine N9 floor up-front; applied whenever the N9 pair is
        # placed (whether through the include-nine shuffle or the
        # standalone path below).
        nine_forced: Optional[int] = None
        if self.options.random_dissonance:
            nine_forced = self._floor_to_available_gate_value(
                int(self.options.required_guardians.value),
                [1, 2, 3, 5, 9])

        # Non-N9 pairs only get reshuffled when the player asked for value
        # randomization (random_soul_gate_value or include_nine_soul_gates).
        # When the only active flag is random_dissonance, we leave them at
        # vanilla and just floor the N9 pair below.
        shuffle_non_nine = (self.options.random_soul_gate_value
                              or self.options.include_nine_soul_gates)

        pairs_to_place: List[Tuple[LM2Entrance, LM2Entrance]] = []
        if shuffle_non_nine:
            pairs_to_place.extend(non_nine_pairs)
            self.rng.shuffle(pairs_to_place)
        if self.options.include_nine_soul_gates and nine_pair is not None:
            soul_amounts.append(9)
            pairs_to_place.append(nine_pair)
            self.rng.shuffle(pairs_to_place)

        if self.options.random_soul_gate_value:
            self.rng.shuffle(soul_amounts)
        else:
            soul_amounts.sort()

        for gate1, gate2 in pairs_to_place:
            is_nine = (gate1.game_exit_id == ExitID.f03GateN9
                        or gate2.game_exit_id == ExitID.f03GateN9)

            if is_nine and nine_forced is not None:
                amount_order = [nine_forced]
            elif self.options.random_soul_gate_value:
                amount_order = list(soul_amounts)
                self.rng.shuffle(amount_order)
            else:
                amount_order = list(soul_amounts)

            placed = False
            for soul_amount in amount_order:
                snap = self._save_gate_pair_state(gate1, gate2, epd_hel_exit)
                # Always force_override in value-only mode: vanilla pair
                # logic still references the vanilla GuardianKills(N),
                # which would otherwise dominate when Setting(Random Soul
                # Gates) is False.
                self._apply_gate_pair(
                    gate1, gate2, soul_amount,
                    swap_regions=False, force_override=True)

                if self._kill_simulation_check():
                    if (not self.options.random_soul_gate_value
                            and not (is_nine and nine_forced is not None)
                            and soul_amount in soul_amounts):
                        soul_amounts.remove(soul_amount)
                    self.soul_gate_pairs.append(
                        SoulGatePair(gate1.game_exit_id,
                                     gate2.game_exit_id, soul_amount))
                    placed = True
                    break

                self._restore_gate_pair_state(gate1, gate2, epd_hel_exit, snap)

            if not placed:
                _log(f"[ER-SG] Value-only placement: no valid amount for "
                      f"{gate1.name} <-> {gate2.name} — signaling reset")
                return False

        # When include_nine_soul_gates is OFF, the N9 pair was held back.
        # Floor it (if random_dissonance) or keep it at vanilla 9 -- the
        # apply step is still required when forced, since vanilla logic
        # has GuardianKills(9) hard-coded.
        if (nine_pair is not None
                and not self.options.include_nine_soul_gates):
            g1, g2 = nine_pair
            amount = nine_forced if nine_forced is not None else 9
            if amount != 9:
                snap = self._save_gate_pair_state(g1, g2, epd_hel_exit)
                self._apply_gate_pair(
                    g1, g2, amount,
                    swap_regions=False, force_override=True)
                if not self._kill_simulation_check():
                    self._restore_gate_pair_state(g1, g2, epd_hel_exit, snap)
                    return False
            self.soul_gate_pairs.append(
                SoulGatePair(g1.game_exit_id, g2.game_exit_id, amount))

        return True

    def _randomize_soul_gate_values_retry(self) -> bool:
        """Retry wrapper around _randomize_soul_gate_values_speculative."""
        MAX_ATTEMPTS = 50

        gates = self._get_exits_of_type(ExitType.SoulGate)
        vanilla_logic = {
            g.game_exit_id: g._original_logic for g in gates
        }

        epd_hel_exit = None
        epd_hel_vanilla_logic = None
        for e in self.entrances:
            if (hasattr(e, 'connecting_area')
                    and e.connecting_area == AreaID.EPDHel):
                epd_hel_exit = e
                epd_hel_vanilla_logic = e._original_logic
                break

        items_only_base = _build_items_only_state(self.world)

        def _reset_logic_only():
            for gate in gates:
                saved_logic = vanilla_logic[gate.game_exit_id]
                self._reset_logic(gate, saved_logic)
            if epd_hel_exit is not None and epd_hel_vanilla_logic is not None:
                self._reset_logic(epd_hel_exit, epd_hel_vanilla_logic)
            self.soul_gate_pairs.clear()

        for attempt in range(MAX_ATTEMPTS):
            _reset_logic_only()

            if not self._randomize_soul_gate_values_speculative(epd_hel_exit):
                _log(f"[ER] Soul gate value-only attempt {attempt + 1} "
                      f"could not place all values, retrying with fresh shuffle...")
                continue

            valid, unreachable = _validate_region_reachability(
                self.world, base_state=items_only_base)
            if not valid:
                structural = getattr(self.world, '_structural_unreachable', set())
                new_unreachable = [loc for loc in unreachable if loc not in structural]
                if new_unreachable:
                    _log(f"[ER] Soul gate value-only attempt {attempt + 1}: "
                          f"post-value logic made {len(new_unreachable)} NEW "
                          f"locations unreachable (e.g. {new_unreachable[:3]}), "
                          f"retrying...")
                    continue

            if attempt > 0:
                _log(f"[ER] Soul gate value-only succeeded on attempt {attempt + 1}")
            self._log_soul_gate_pairings("VALUE-ONLY: ")
            return True

        _log(f"[ER] Soul gate value-only randomization failed after "
              f"{MAX_ATTEMPTS} attempts.")
        self._log_soul_gate_pairings("LAST FAILED (VALUE-ONLY): ")
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
        GuardianKills appended by _apply_gate_pair) AND any
        internal/other exits modified by _update_epg_logic.

        Exits with 'and False' in their logic get cost 9999 (permanently blocked).
        Exits without GuardianKills are NOT in the dict (freely traversable).
        """
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

    # ── Graph helpers used by IBMain escape path ──────────────────────

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
            _log(line)
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
        line = f"[ER] SPOILER -- IBMain -> Cliff ({hop_count - 1} hops): {path_str}"
        _log(line) 
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

    @staticmethod
    def _override_guardian_kills(entrance: LM2Entrance, new_value: int) -> None:
        """
        Replace any GuardianKills(N) literal in the entrance's logic with
        GuardianKills(new_value).  Used when the assigned soul cost must
        actually lower the gate's kill requirement (vanilla pairs in
        value-only mode, or random_dissonance forced N9 floor with
        random_soul_gate_value off).
        """
        cur = getattr(entrance, '_original_logic', '') or ''
        new_logic = re.sub(r'GuardianKills\(\s*\d+\s*\)',
                           f'GuardianKills({new_value})', cur)
        if new_logic == cur:
            return
        entrance._original_logic = new_logic
        tokens = LogicTokeniser(new_logic).tokenise()
        entrance._logic_tree = LogicTree.parse(tokens)
        if getattr(entrance, '_world', None) is not None:
            entrance._compiled_rule = entrance._logic_tree.compile(entrance._world)
        else:
            entrance._compiled_rule = None