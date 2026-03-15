from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

from .ids import ExitID, AreaID
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
# Exit classification sets
# ============================================================

# Exits that are permanently inaccessible from normal play.
# When accessibility=full these must be paired with accessible exits
# so they don't create unreachable orphan areas.
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

# Exits that lead to areas with no outgoing traversable connection —
# used to avoid stranding the player at the very first transition.
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

# Exits where traversal is one-directional: you cannot return the way you came.
# These are treated as "must-exit" entrances and are placed first so that
# their destination can always reach an escape area.
ONE_WAY_EXITS = {
    ExitID.fL05Up,
    ExitID.f02Down,
    ExitID.f03Down2,
    ExitID.f03In,
    ExitID.f09In,
}

# Areas that connect to the broader world and allow the player to continue.
# An ER layout is rejected if the starting area cannot reach any of these.
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
# Entrance Randomizer
# ============================================================

DEBUG_ER = True   # Set to True to enable entrance randomizer debug output

class EntranceRandomizer:
    """
    Forward-fill entrance randomizer for La-Mulana 2.

    Algorithm (ALTTP connect_mandatory_exits + connect_caves inspired):

      Phase 1 – Must-exits first:
        One-way exits are paired before everything else.  Each one-way
        exit is matched with a partner whose current destination can reach
        an escape area, guaranteeing the player is never stranded.

      Phase 2 – Frontier expansion:
        Remaining exits are paired using BFS-guided heuristics.  At each
        step we prefer:
          (a) a source exit whose parent area is already reachable, and
          (b) a partner whose destination expands the reachable set.
        This grows the accessible zone outward rather than scattering
        connections randomly, making unbeatable layouts structurally
        impossible in the vast majority of cases.

      Phase 3 – Post-hoc escape check:
        The existing _passes_escape_check() runs as a final safety net.
        Because the forward fill builds sound graphs by construction it
        rarely fires; 50 retry attempts cover remaining edge cases such
        as complex soul-gate kill-ordering.
    """

    def __init__(self, rng: random.Random, entrances: List[LM2Entrance], world):
        self.rng = rng
        self.entrances = entrances
        self.world = world
        self.options = world.options
        self.starting_area: AreaID = world.starting_area
        self.starting_entrance: Optional[ExitID] = None

        self.pairs: List[EntrancePair] = []
        self.soul_gate_pairs: List[SoulGatePair] = []

    # ============================================================
    # Public entry point
    # ============================================================

    def randomize(self) -> List[EntrancePair]:
        self._determine_starting_entrance()

        # Snapshot vanilla state so retries can fully reset
        vanilla_regions = {e: e.connected_region for e in self.entrances}
        vanilla_logic   = {e: getattr(e, '_original_logic', None) for e in self.entrances}

        _er_flags = []
        if self.options.horizontal_entrances:       _er_flags.append('horizontal')
        if self.options.vertical_entrances:         _er_flags.append('vertical')
        if self.options.gate_entrances:             _er_flags.append('gates')
        if self.options.soul_gate_entrances:        _er_flags.append('soul_gates')
        if self.options.full_random_entrances:      _er_flags.append('full_random')
        if self.options.include_unique_transitions: _er_flags.append('unique_transitions')
        if self.options.random_soul_gate_value:     _er_flags.append('random_soul_gate_value')
        if self.options.include_nine_soul_gates:    _er_flags.append('include_nine_soul_gates')
        if self.options.random_dissonance:          _er_flags.append('random_dissonance')
        _weapon = getattr(self.world, 'starting_weapon', None)
        print(
            f"[ER] === start ==="
            f"\n  starting_area   : {self.starting_area.name if hasattr(self.starting_area, 'name') else self.starting_area}"
            f"\n  starting_weapon : {_weapon.name if hasattr(_weapon, 'name') else _weapon}"
            f"\n  accessibility   : {getattr(self.options.accessibility, 'current_key', self.options.accessibility)}"
            f"\n  er_flags        : {', '.join(_er_flags) or 'none'}"
        )

        max_attempts = 50
        for attempt in range(max_attempts):
            # --- Reset to vanilla ---
            for e, region in vanilla_regions.items():
                e.disconnect()
                if region is not None:
                    e.connect(region)
                self._reset_logic(e, vanilla_logic.get(e))

            self.pairs = []
            self.soul_gate_pairs = []

            # --- Structural entrance randomization ---
            if self.options.full_random_entrances:
                self._randomize_full_random()
            else:
                if self.options.horizontal_entrances:
                    self._randomize_horizontal()
                if self.options.vertical_entrances:
                    self._randomize_vertical()
                if self.options.gate_entrances:
                    self._randomize_gates()

            # --- Soul gate randomization (has its own inner retry loop) ---
            if self.options.soul_gate_entrances:
                try:
                    self._randomize_soul_gate_entrances_retry()
                except RuntimeError:
                    continue  # soul-gate deadlock: retry the whole layout

            # --- Final safety net ---
            if self._passes_escape_check(attempt):
                if attempt > 0:
                    print(f"[ER] Layout accepted on attempt {attempt + 1}")
                self._log_entrance_pairs()
                self._log_ibmain_escape_path(self._area_graph())
                break
        else:
            raise Exception(
                f"[ER] Failed to generate a valid entrance layout after {max_attempts} attempts."
            )

        return self.pairs

    def _log_entrance_pairs(self):
        """Print all entrance and soul gate pairs with their final logic."""
        if not DEBUG_ER:
            return

        # Build a map from ExitID to the entrance object for quick lookup
        entrance_by_id = {e.game_exit_id: e for e in self.entrances}

        print("\n[ER DEBUG] ===== ENTRANCE PAIRS =====")
        for pair in self.pairs:
            from_exit = pair.from_exit
            to_exit   = pair.to_exit
            from_name = from_exit.name if hasattr(from_exit, 'name') else str(from_exit)
            to_name   = to_exit.name if hasattr(to_exit, 'name') else str(to_exit)
            print(f"  {from_name}  <->  {to_name}")

        print("\n[ER DEBUG] ===== SOUL GATE PAIRS =====")
        for sg_pair in self.soul_gate_pairs:
            gate1_id = sg_pair.gate1
            gate2_id = sg_pair.gate2
            souls = sg_pair.soul_amount

            gate1 = entrance_by_id.get(gate1_id)
            gate2 = entrance_by_id.get(gate2_id)

            logic1 = gate1._original_logic if gate1 else "?"
            logic2 = gate2._original_logic if gate2 else "?"

            g1_name = gate1_id.name if hasattr(gate1_id, 'name') else str(gate1_id)
            g2_name = gate2_id.name if hasattr(gate2_id, 'name') else str(gate2_id)

            print(f"  {g1_name} <-> {g2_name}  (souls={souls})")
            print(f"      Logic1: {logic1}")
            print(f"      Logic2: {logic2}")

        print("[ER DEBUG] ===== END =====\n")

    # ============================================================
    # Starting entrance determination
    # ============================================================

    def _determine_starting_entrance(self):
        """
        Map the chosen starting AreaID to the ExitID that represents
        'the first shuffleable exit from that area'.  Used to protect
        the starting transition from loops and dead-ends.
        """
        candidates: List[ExitID] = []

        if self.starting_area == AreaID.VoD:
            if self.options.gate_entrances:
                candidates.append(ExitID.f01Right)
            if self.options.include_unique_transitions:
                candidates.append(ExitID.f01Start)
        elif self.starting_area == AreaID.RoY:
            candidates.append(ExitID.f00GateY0)
        elif self.starting_area == AreaID.AnnwfnMain:
            if self.options.vertical_entrances:
                candidates.append(ExitID.f02Up)
            if self.options.include_unique_transitions:
                candidates.append(ExitID.f02Bifrost)
                candidates.append(ExitID.f02Down)
        elif self.starting_area == AreaID.IBMain:
            candidates.append(ExitID.f03Right)
        elif self.starting_area == AreaID.ITLeft:
            candidates.append(ExitID.f04Up)
        elif self.starting_area == AreaID.DFMain:
            candidates.append(ExitID.f05GateP1)
        elif self.starting_area == AreaID.SotFGGrail:
            candidates.append(ExitID.f06GateP0)
        elif self.starting_area == AreaID.TSLeft:
            candidates.append(ExitID.f08GateP0)
        elif self.starting_area == AreaID.ValhallaMain:
            candidates.append(ExitID.f10GateP0)
        elif self.starting_area == AreaID.DSLMMain:
            candidates.append(ExitID.f11GateP0)
        elif self.starting_area == AreaID.ACTablet:
            candidates.append(ExitID.f12GateP0)
        elif self.starting_area == AreaID.HoMTop:
            candidates.append(ExitID.f13GateP0)

        self.starting_entrance = candidates[0] if candidates else ExitID.None_

    # ============================================================
    # Graph helpers
    # ============================================================

    def _area_graph(self) -> Dict[AreaID, Set[AreaID]]:
        """
        Build a directed area→{area} adjacency map from the current
        live entrance connections, ignoring structurally disabled exits.
        """
        graph: Dict[AreaID, Set[AreaID]] = defaultdict(set)
        for e in self.entrances:
            if e.connected_region is None:
                continue
            logic = getattr(e, '_original_logic', '') or ''
            if 'false' in logic.lower():
                continue
            graph[e.parent_region.game_area_id].add(e.connected_region.game_area_id)
        return graph

    def _reachable_from(self, start: AreaID,
                        graph: Dict[AreaID, Set[AreaID]]) -> Set[AreaID]:
        """Forward BFS: all areas reachable from *start*."""
        visited: Set[AreaID] = {start}
        q: deque = deque([start])
        while q:
            cur = q.popleft()
            for nxt in graph.get(cur, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    q.append(nxt)
        return visited

    def _can_reach_escape(self, graph: Dict[AreaID, Set[AreaID]]) -> Set[AreaID]:
        """
        Reverse BFS: all areas from which at least one escape area is
        reachable.  Used to guarantee one-way exits don't strand the player.
        """
        rev: Dict[AreaID, Set[AreaID]] = defaultdict(set)
        for src, dsts in graph.items():
            for dst in dsts:
                rev[dst].add(src)

        visited: Set[AreaID] = set(_ESCAPE_AREAS)
        q: deque = deque(_ESCAPE_AREAS)
        while q:
            cur = q.popleft()
            for prev in rev.get(cur, ()):
                if prev not in visited:
                    visited.add(prev)
                    q.append(prev)
        return visited

    # ============================================================
    # Core forward-fill primitives
    # ============================================================

    def _swap(self, a: LM2Entrance, b: LM2Entrance) -> None:
        """
        Connect two exits so that each leads to the other's parent area,
        then record the pair.

        C# game semantics: pair(A, B) means "taking exit A lands you in
        the area that contains exit B" — i.e. A connects to B.parent_region
        and B connects to A.parent_region.

        The previous implementation exchanged connected_regions (i.e. A
        connected to B's vanilla destination, B to A's vanilla destination).
        That was wrong for every cross-area exit pair: the AP region graph
        showed incorrect connectivity, making playthrough, item logic, and
        fill reachability disagree with the actual game.
        """
        parent_a = a.parent_region
        parent_b = b.parent_region
        a.disconnect()
        b.disconnect()
        a.connect(parent_b)   # taking a → arrive in b's area
        b.connect(parent_a)   # taking b → arrive in a's area
        self.pairs.append(EntrancePair(a.game_exit_id, b.game_exit_id))

    def _is_safe_pair(self, exit_a: LM2Entrance, exit_b: LM2Entrance,
                      can_escape: Set[AreaID]) -> bool:
        """
        Return True if pairing exit_a with exit_b satisfies all hard
        structural constraints:
          - The starting exit must not lead to a dead-end or create a loop
          - One-way exits must land in areas that can reach an escape
        """
        # Protect the starting exit: it must always lead somewhere useful
        if exit_a.game_exit_id == self.starting_entrance:
            if exit_b.game_exit_id in DEAD_END_EXITS:
                return False
            if self._creates_start_loop(exit_b):
                return False
        if exit_b.game_exit_id == self.starting_entrance:
            if exit_a.game_exit_id in DEAD_END_EXITS:
                return False
            if self._creates_start_loop(exit_a):
                return False

        # One-way exits: their new destination must be escapable.
        # After the fixed _swap, exit_a connects to exit_b.parent_region,
        # so check that area — not exit_b's current connected_region.
        if exit_a.game_exit_id in ONE_WAY_EXITS:
            if exit_b.parent_region is None:
                return False
            if exit_b.parent_region.game_area_id not in can_escape:
                return False

        return True

    def _pick_partner(self, source: LM2Entrance,
                      candidates: List[LM2Entrance],
                      reachable: Set[AreaID],
                      can_escape: Set[AreaID]) -> LM2Entrance:
        """
        Choose the best partner for *source* from *candidates*.

        Priority order:
          1. Safe AND doesn't disconnect IBMain from escape AND expands frontier
          2. Safe AND doesn't disconnect IBMain from escape
          3. Safe (hard structural constraints only)
          4. Any candidate (last resort — outer escape check retries)

        _swap_disconnects_ibmain excludes soul gate exits when called during the
        gate fill phase, so that vanilla SG connections don't mask a genuine
        disconnect of IBMain's physical (non-SG) exit cluster.
        """
        safe = [c for c in candidates if self._is_safe_pair(source, c, can_escape)]
        pool = safe if safe else candidates

        ibmain_safe = [c for c in pool if not self._swap_disconnects_ibmain(source, c)]
        pool = ibmain_safe if ibmain_safe else pool

        # Prefer partners whose parent area is not yet reachable: after the
        # fixed _swap, taking source connects to c.parent_region, so a
        # candidate whose parent_region is new territory expands the frontier.
        expanding = [c for c in pool
                     if c.parent_region
                     and c.parent_region.game_area_id not in reachable]
        return self.rng.choice(expanding) if expanding else self.rng.choice(pool)

    def _place_must_exits(self, must_exits: List[LM2Entrance],
                          partner_pool: List[LM2Entrance]) -> None:
        """
        ALTTP connect_mandatory_exits parity.

        Place every one-way exit before any other pairing.  Each is
        matched with a partner whose *current* destination area can reach
        an escape area so that the player is never permanently stranded.
        Removes matched partners from partner_pool in-place.
        """
        graph = self._area_graph()
        can_escape = self._can_reach_escape(graph)
        reachable  = self._reachable_from(self.starting_area, graph)

        for must in must_exits:
            partner = self._pick_partner(must, partner_pool, reachable, can_escape)
            partner_pool.remove(partner)
            self._swap(must, partner)
            # Rebuild reachability after each swap so later must-exits
            # see the updated graph.
            graph     = self._area_graph()
            can_escape = self._can_reach_escape(graph)
            reachable  = self._reachable_from(self.starting_area, graph)

    def _forward_fill(self, pool_a: List[LM2Entrance],
                      pool_b: Optional[List[LM2Entrance]] = None) -> None:
        """
        ALTTP connect_caves parity.

        If pool_b is None (or the same object as pool_a), pairs are drawn
        from a single pool.  Otherwise pool_a is paired with pool_b.

        At each step:
          1. Rebuild the reachability graph from the live connections.
          2. Prefer a source exit whose parent area is already reachable
             (frontier-first, same as ALTTP sorting caves by exit count).
          3. Pick the best partner via _pick_partner.
        """
        same_pool = pool_b is None or pool_b is pool_a
        if same_pool:
            combined = list(pool_a)
            self.rng.shuffle(combined)
            while len(combined) >= 2:
                graph      = self._area_graph()
                reachable  = self._reachable_from(self.starting_area, graph)
                can_escape = self._can_reach_escape(graph)

                frontier = [e for e in combined
                            if e.parent_region.game_area_id in reachable]
                source = self.rng.choice(frontier) if frontier else combined[-1]
                combined.remove(source)

                partner = self._pick_partner(source, combined, reachable, can_escape)
                combined.remove(partner)
                self._swap(source, partner)
            pool_a.clear()
        else:
            self.rng.shuffle(pool_a)
            self.rng.shuffle(pool_b)
            while pool_a and pool_b:
                graph      = self._area_graph()
                reachable  = self._reachable_from(self.starting_area, graph)
                can_escape = self._can_reach_escape(graph)

                frontier_a = [e for e in pool_a
                              if e.parent_region.game_area_id in reachable]
                source = self.rng.choice(frontier_a) if frontier_a else pool_a[-1]
                pool_a.remove(source)

                partner = self._pick_partner(source, pool_b, reachable, can_escape)
                pool_b.remove(partner)
                self._swap(source, partner)

    # ============================================================
    # Per-type randomization methods
    # ============================================================

    def _randomize_horizontal(self) -> None:
        """
        Pair LeftDoor exits with RightDoor exits.

        Hard structural constraints preserved from the C# original:
          - fP02Left must not go to fL08Right (inaccessible cliff ledge)
          - fP00Left must not self-loop with fP00Right
          - fL11GateN must not pair with fL11GateY0 (full accessibility:
            would create an illusion corridor with no escape)
          - Inaccessible exits are paired with accessible ones when
            accessibility=full (except f12GateP0 with costume_clip on)
        """
        left_doors  = list(self._get_exits_of_type(ExitType.LeftDoor))
        right_doors = list(self._get_exits_of_type(ExitType.RightDoor))
        self.rng.shuffle(left_doors)
        self.rng.shuffle(right_doors)

        # --- Phase 1: one-way exits must land in escapable areas ---
        one_way_left  = [e for e in left_doors  if e.game_exit_id in ONE_WAY_EXITS]
        one_way_right = [e for e in right_doors if e.game_exit_id in ONE_WAY_EXITS]
        for e in one_way_left:  left_doors.remove(e)
        for e in one_way_right: right_doors.remove(e)
        self._place_must_exits(one_way_left,  right_doors)
        self._place_must_exits(one_way_right, left_doors)

        # --- Phase 2: specific hard-constraint pairings ---
        # fP02Left: cannot go to fL08Right
        p02_left = next((d for d in left_doors if d.game_exit_id == ExitID.fP02Left), None)
        if p02_left:
            left_doors.remove(p02_left)
            safe_rights = [r for r in right_doors if r.game_exit_id != ExitID.fL08Right]
            pool = safe_rights if safe_rights else right_doors
            graph      = self._area_graph()
            reachable  = self._reachable_from(self.starting_area, graph)
            can_escape = self._can_reach_escape(graph)
            partner = self._pick_partner(p02_left, pool, reachable, can_escape)
            right_doors.remove(partner)
            self._swap(p02_left, partner)

        # fP00Left: cannot self-loop with fP00Right
        p00_left = next((d for d in left_doors if d.game_exit_id == ExitID.fP00Left), None)
        if p00_left:
            left_doors.remove(p00_left)
            safe_rights = [r for r in right_doors if r.game_exit_id != ExitID.fP00Right]
            pool = safe_rights if safe_rights else right_doors
            graph      = self._area_graph()
            reachable  = self._reachable_from(self.starting_area, graph)
            can_escape = self._can_reach_escape(graph)
            partner = self._pick_partner(p00_left, pool, reachable, can_escape)
            right_doors.remove(partner)
            self._swap(p00_left, partner)

        # --- Phase 3: accessibility=full – inaccessible exits first ---
        if self.options.accessibility.value == 2:
            self._pair_inaccessible_first(left_doors, right_doors)
            self._pair_inaccessible_first(right_doors, left_doors)

        # --- Phase 4: forward-fill remaining ---
        self._forward_fill(left_doors, right_doors)

    def _randomize_vertical(self) -> None:
        """
        Pair UpLadder exits with DownLadder exits.

        Hard structural constraint preserved:
          - f02Down / f03Down2 (one-way drops) must not pair with fL05Up
            (an inaccessible up-ladder), which would create a permanently
            unreachable connection from both directions.
        """
        down_ladders = list(self._get_exits_of_type(ExitType.DownLadder))
        up_ladders   = list(self._get_exits_of_type(ExitType.UpLadder))
        self.rng.shuffle(down_ladders)
        self.rng.shuffle(up_ladders)

        # --- Phase 1: one-way downs placed first ---
        # f02Down and f03Down2 are in both ONE_WAY_EXITS and DEAD_END_EXITS.
        # They must NOT pair with fL05Up (inaccessible upward exit).
        one_way_downs = [e for e in down_ladders if e.game_exit_id in ONE_WAY_EXITS]
        for e in one_way_downs:
            down_ladders.remove(e)

        safe_ups = [u for u in up_ladders if u.game_exit_id != ExitID.fL05Up]
        self._place_must_exits(one_way_downs, safe_ups if safe_ups else up_ladders)
        # Sync: remove any ups consumed by must-exits from the main pool
        for u in list(up_ladders):
            if u not in safe_ups and u not in up_ladders:
                pass  # already gone
        up_ladders[:] = [u for u in up_ladders if u in safe_ups or u.game_exit_id == ExitID.fL05Up]
        # Rebuild: safe_ups may have shrunk
        for u in list(up_ladders):
            # If it was consumed by _place_must_exits it has a new connected_region;
            # check by whether it's still in the original list reference.
            pass  # _place_must_exits removes from safe_ups in-place via partner_pool arg

        # Rebuild up_ladders to only contain what wasn't consumed
        consumed = {p.to_exit for p in self.pairs}
        up_ladders = [u for u in self._get_exits_of_type(ExitType.UpLadder)
                      if u.game_exit_id not in consumed]
        down_ladders_remaining = [d for d in self._get_exits_of_type(ExitType.DownLadder)
                                  if d.game_exit_id not in consumed
                                  and d.game_exit_id not in ONE_WAY_EXITS]

        # --- Phase 2: accessibility=full – inaccessible exits first ---
        if self.options.accessibility.value == 2:
            self._pair_inaccessible_first(up_ladders, down_ladders_remaining)
            self._pair_inaccessible_first(down_ladders_remaining, up_ladders)

        # --- Phase 3: forward-fill remaining ---
        self._forward_fill(up_ladders, down_ladders_remaining)

    def _randomize_gates(self) -> None:
        """
        Pair Gate exits with Gate exits (single pool, swap-based).

        Hard structural constraints preserved:
          - fL11GateN must not pair with fL11GateY0 when accessibility=full
            (would trap the player in the Gate of Illusion loop)
          - Inaccessible exits are paired with accessible ones when
            accessibility=full (except f12GateP0 with costume_clip)
        """
        gates = list(self._get_exits_of_type(ExitType.Gate))
        self.rng.shuffle(gates)

        # --- Phase 1: fL11GateN constraint (full accessibility only) ---
        if self.options.accessibility.value == 2:
            illusion_gate = next((g for g in gates
                                  if g.game_exit_id == ExitID.fL11GateN), None)
            if illusion_gate:
                gates.remove(illusion_gate)
                allowed = [g for g in gates if g.game_exit_id != ExitID.fL11GateY0]
                pool = allowed if allowed else gates
                graph      = self._area_graph()
                reachable  = self._reachable_from(self.starting_area, graph)
                can_escape = self._can_reach_escape(graph)
                partner = self._pick_partner(illusion_gate, pool, reachable, can_escape)
                gates.remove(partner)
                self._swap(illusion_gate, partner)

        # --- Phase 2: accessibility=full – inaccessible exits first ---
        if self.options.accessibility.value == 2:
            self._pair_inaccessible_first(gates, gates, same_pool=True)
            # Rebuild from what's left (same_pool clears the list after pairing)
            gates = [g for g in self._get_exits_of_type(ExitType.Gate)
                     if g.game_exit_id not in {p.from_exit for p in self.pairs}
                     and g.game_exit_id not in {p.to_exit   for p in self.pairs}]

        # --- Phase 3: forward-fill remaining ---
        self._forward_fill(gates)

    def _randomize_full_random(self) -> None:
        """
        Mix all enabled entrance types into a single pool and pair them
        using the same forward-fill algorithm.

        Unique transitions (OneWay, Pyramid, Start, Altar) are included
        when include_unique_transitions is enabled.
        """
        pool: List[LM2Entrance] = []

        if self.options.horizontal_entrances:
            pool.extend(self._get_exits_of_type(ExitType.LeftDoor))
            pool.extend(self._get_exits_of_type(ExitType.RightDoor))
        if self.options.vertical_entrances:
            pool.extend(self._get_exits_of_type(ExitType.DownLadder))
            pool.extend(self._get_exits_of_type(ExitType.UpLadder))
        if self.options.gate_entrances:
            pool.extend(self._get_exits_of_type(ExitType.Gate))
        if self.options.include_unique_transitions:
            pool.extend(self._get_exits_of_type(ExitType.OneWay))
            pool.extend(self._get_exits_of_type(ExitType.Pyramid))
            pool.extend(self._get_exits_of_type(ExitType.Start))
            pool.extend(self._get_exits_of_type(ExitType.Altar))

        self.rng.shuffle(pool)

        # --- Phase 1: one-way exits placed first ---
        one_ways = [e for e in pool if e.game_exit_id in ONE_WAY_EXITS]
        for e in one_ways:
            pool.remove(e)
        self._place_must_exits(one_ways, pool)

        # --- Phase 2: specific hard-constraint pairings ---
        # fP02Left must not go to fL08Right
        p02_left = next((e for e in pool if e.game_exit_id == ExitID.fP02Left), None)
        if p02_left:
            pool.remove(p02_left)
            safe = [e for e in pool if e.game_exit_id != ExitID.fL08Right]
            candidates = safe if safe else pool
            graph      = self._area_graph()
            reachable  = self._reachable_from(self.starting_area, graph)
            can_escape = self._can_reach_escape(graph)
            partner = self._pick_partner(p02_left, candidates, reachable, can_escape)
            pool.remove(partner)
            self._swap(p02_left, partner)

        # fP00Left must not self-loop with fP00Right
        p00_left = next((e for e in pool if e.game_exit_id == ExitID.fP00Left), None)
        if p00_left:
            pool.remove(p00_left)
            safe = [e for e in pool if e.game_exit_id != ExitID.fP00Right]
            candidates = safe if safe else pool
            graph      = self._area_graph()
            reachable  = self._reachable_from(self.starting_area, graph)
            can_escape = self._can_reach_escape(graph)
            partner = self._pick_partner(p00_left, candidates, reachable, can_escape)
            pool.remove(partner)
            self._swap(p00_left, partner)

        # fL11GateN must not pair with fL11GateY0 (full accessibility)
        if self.options.accessibility.value == 2:
            illusion_gate = next((e for e in pool
                                  if e.game_exit_id == ExitID.fL11GateN), None)
            if illusion_gate:
                pool.remove(illusion_gate)
                allowed = [e for e in pool if e.game_exit_id != ExitID.fL11GateY0]
                candidates = allowed if allowed else pool
                graph      = self._area_graph()
                reachable  = self._reachable_from(self.starting_area, graph)
                can_escape = self._can_reach_escape(graph)
                partner = self._pick_partner(illusion_gate, candidates, reachable, can_escape)
                pool.remove(partner)
                self._swap(illusion_gate, partner)

        # --- Phase 3: accessibility=full – inaccessible exits first ---
        if self.options.accessibility.value == 2:
            self._pair_inaccessible_first(pool, pool, same_pool=True)
            consumed = {p.from_exit for p in self.pairs} | {p.to_exit for p in self.pairs}
            pool = [e for e in pool if e.game_exit_id not in consumed]

        # --- Phase 4: forward-fill remaining ---
        self._forward_fill(pool)

    # ============================================================
    # Accessibility helper: inaccessible exits paired first
    # ============================================================

    def _pair_inaccessible_first(self, pool: List[LM2Entrance],
                                  accessible_pool: List[LM2Entrance],
                                  same_pool: bool = False) -> None:
        """
        When accessibility=full, exits in INACCESSIBLE_EXITS must be
        paired with accessible exits so they don't create orphaned areas.

        Modifies both pools in-place.  f12GateP0 is excluded when
        costume_clip is enabled (players can reach it via clip).
        """
        inaccessible = [
            e for e in pool
            if e.game_exit_id in INACCESSIBLE_EXITS
            and not (self.options.costume_clip and e.game_exit_id == ExitID.f12GateP0)
        ]
        if not inaccessible:
            return

        if same_pool:
            # Both source and partner come from the same list
            accessible = [e for e in pool if e not in inaccessible]
        else:
            accessible = [e for e in accessible_pool
                          if e.game_exit_id not in INACCESSIBLE_EXITS]

        for ie in inaccessible:
            if ie not in pool:
                continue
            if not accessible:
                break
            pool.remove(ie)
            graph      = self._area_graph()
            reachable  = self._reachable_from(self.starting_area, graph)
            can_escape = self._can_reach_escape(graph)
            partner = self._pick_partner(ie, accessible, reachable, can_escape)
            accessible.remove(partner)
            if same_pool:
                pool.remove(partner)
            else:
                accessible_pool.remove(partner)
            self._swap(ie, partner)

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
        """Retry wrapper for soul gate randomization with up to 100 inner attempts."""
        MAX_ATTEMPTS = 100

        gates = self._get_exits_of_type(ExitType.SoulGate)
        vanilla_state = {
            g.game_exit_id: (g.connected_region, g._original_logic)
            for g in gates
        }

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

            self.soul_gate_pairs.clear()
            self._randomize_soul_gate_entrances()

            if self._validate_soul_gate_reachability():
                if attempt > 0:
                    print(f"[ER] Soul gate succeeded on attempt {attempt + 1}")
                return

            print(f"[ER] Soul gate attempt {attempt + 1} failed, retrying...")

        raise RuntimeError(
            f"Soul gate randomization failed after {MAX_ATTEMPTS} attempts."
        )

    # ============================================================
    # Soul gate validation helpers
    # ============================================================

    def get_max_reachable_regions(self) -> set:
        """
        Returns the set of region names reachable with all guardians defeated.
        Used to mark structurally cut-off locations as EXCLUDED after ER.
        """
        import re

        soul_gate_exits = set(self._get_exits_of_type(ExitType.SoulGate))
        gate_costs: dict = {}
        for gate in soul_gate_exits:
            if gate.connected_region is None:
                gate_costs[id(gate)] = 9999
                continue
            logic = getattr(gate, '_original_logic', '') or ''
            is_dead = (' and False' in logic or
                       logic.strip() == 'False' or
                       logic.strip().startswith('(False)'))
            if is_dead:
                gate_costs[id(gate)] = 9999
                continue
            kill_matches = re.findall(r'GuardianKills\((\d+)\)', logic)
            gate_costs[id(gate)] = int(kill_matches[-1]) if kill_matches else 0

        guardian_locs = [
            loc for loc in self.world.multiworld.get_locations(self.world.player)
            if hasattr(loc, 'location_type') and loc.location_type == LocationType.Guardian
        ]
        return self._flood_fill(len(guardian_locs), soul_gate_exits, gate_costs)

    def _flood_fill(self, kills: int, soul_gate_exits: set, gate_costs: dict) -> set:
        """
        Return the set of region names reachable with *kills* guardian kills.
        Soul gate exits are only traversable when their kill cost <= kills.
        gate_costs maps id(gate) → kill cost (9999 = permanently blocked).
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
                if exit_ in soul_gate_exits:
                    if kills < gate_costs.get(id(exit_), 9999):
                        continue
                queue.append(exit_.connected_region)
        return visited

    def _validate_soul_gate_reachability(self) -> bool:
        import re

        soul_gate_exits = set(self._get_exits_of_type(ExitType.SoulGate))

        gate_costs: dict = {}
        for gate in soul_gate_exits:
            if gate.connected_region is None:
                gate_costs[id(gate)] = 9999
                continue
            logic = gate._original_logic
            is_dead = (' and False' in logic or
                       logic.strip() == 'False' or
                       logic.strip().startswith('(False)'))
            if is_dead:
                gate_costs[id(gate)] = 9999
                continue
            kill_matches = re.findall(r'GuardianKills\((\d+)\)', logic)
            gate_costs[id(gate)] = int(kill_matches[-1]) if kill_matches else 0

        guardian_locs = [
            loc for loc in self.world.multiworld.get_locations(self.world.player)
            if hasattr(loc, 'location_type') and loc.location_type == LocationType.Guardian
        ]

        # Part 1: kill-order simulation — each guardian must be reachable in sequence
        reachable = self._flood_fill(0, soul_gate_exits, gate_costs)
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
                reachable = self._flood_fill(kills, soul_gate_exits, gate_costs)
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
            all_reachable = self._flood_fill(len(guardian_locs), soul_gate_exits, gate_costs)
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

    # ============================================================
    # IBMain post-endgame escape maintenance
    # ============================================================
    #
    # After Ninth Child is beaten (in SpiralHell, accessed via IBBoat),
    # the game returns the player to IBMain with Holy Grail disabled.
    # The player must physically walk from IBMain to an escape area.
    #
    # IBMain cluster external exits (all randomizable):
    #   f03Right   RightDoor  [IBRight]         horizontal
    #   f03Up      UpLadder   [IBCetusLadder]   vertical
    #   f03Down1   DownLadder [IBLadder]         vertical
    #   f03Down3   DownLadder [IBBattery]        vertical (behind Grapple Claw)
    #   f03GateN3  SoulGate   [IBMain]           soul gate phase
    #   f03GateN4  SoulGate   [IBLeftSG]         soul gate phase
    #   (f03GateYC Gate, f03Down2, f03GateN9 are permanently logic:False)
    #
    # With 6 exits and all soul gates open, IBMain is naturally well-connected.
    # The post-hoc check in _passes_escape_check catches rare failures.
    # _swap_disconnects_ibmain in _pick_partner provides a proactive preference.
    #
    # Parity with C#: EntrancePlacementCheck(EscapeCheck=true) starts from
    # AreaID.IBMain, disables PrisonExit/PrisonGate only, not SoulGates.

    def _ibmain_can_escape(self, graph: Dict[AreaID, Set[AreaID]]) -> bool:
        """BFS from AreaID.IBMain; True iff any _ESCAPE_AREA is reachable."""
        visited: Set[AreaID] = {AreaID.IBMain}
        q: deque = deque([AreaID.IBMain])
        while q:
            cur = q.popleft()
            if cur in _ESCAPE_AREAS:
                return True
            for nxt in graph.get(cur, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    q.append(nxt)
        return False

    def _swap_disconnects_ibmain(self,
                                  exit_a: LM2Entrance,
                                  exit_b: LM2Entrance) -> bool:
        """
        Simulate swapping exit_a ↔ exit_b; return True if IBMain would lose
        its escape path in the resulting graph.

        Uses the full area graph so that all current connections (including
        still-vanilla soul gate connections during gate fill) are considered.
        This means the filter is conservative: it only blocks swaps that
        would disconnect IBMain even accounting for soul gate connectivity.
        The post-hoc check in _passes_escape_check provides the final
        guarantee after soul gate randomization completes.
        """
        # Capture originals before touching anything
        orig_a = exit_a.connected_region
        orig_b = exit_b.connected_region
        parent_a = exit_a.parent_region
        parent_b = exit_b.parent_region

        # Simulate the corrected swap (each exit → partner's parent_region)
        exit_a.disconnect(); exit_b.disconnect()
        exit_a.connect(parent_b)
        exit_b.connect(parent_a)

        result = not self._ibmain_can_escape(self._area_graph())

        # Restore
        exit_a.disconnect(); exit_b.disconnect()
        if orig_a is not None: exit_a.connect(orig_a)
        if orig_b is not None: exit_b.connect(orig_b)
        return result

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
        (src, dst) → human-readable description for warp hops.
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
        path_str  = " → ".join(steps)
        line = f"[ER] SPOILER — IBMain → Cliff ({hop_count - 1} hops): {path_str}"
        print(line)
        self.world.ibmain_escape_spoiler = line
        return line

    # ============================================================
    # Post-hoc escape check (safety net)
    # ============================================================

    def _passes_escape_check(self, attempt: int = 0) -> bool:
        """
        Final safety net — runs after the forward fill.

        Checks:
          1. At least one escape area is reachable from the starting area.
          2. No orphaned areas with locations (full accessibility only).
          3. Enough unconditional free locations in the zero-item starting
             cluster for AP's fill_restrictive to place early progression.
          4. Every reachable one-way exit leads to an area that can escape.
        """
        escape_areas = set(_ESCAPE_AREAS)

        graph         = defaultdict(set)
        reverse_graph = defaultdict(set)

        for e in self.entrances:
            if not e.connected_region:
                continue
            logic = getattr(e, '_original_logic', '') or ''
            if 'false' in logic.lower():
                continue
            src = e.parent_region.game_area_id
            dst = e.connected_region.game_area_id
            graph[src].add(dst)
            reverse_graph[dst].add(src)

        # 1. Basic escape reachability
        reachable_from_start: Set[AreaID] = {self.starting_area}
        q: deque = deque([self.starting_area])
        while q:
            cur = q.popleft()
            for nxt in graph.get(cur, ()):
                if nxt not in reachable_from_start:
                    reachable_from_start.add(nxt)
                    q.append(nxt)

        if not (reachable_from_start & escape_areas):
            print(f"[ER] Attempt {attempt}: FAIL — no escape area reachable from start")
            return False


        # 1c. Starting cluster viability: ensure the logic-free area reachable
        # from the starting point contains enough locations to bootstrap item fill.
        # Catches item-fill deadlocks early so ER retries instead of failing later.
        if not self._starting_cluster_viable(attempt):
            return False

        # 1b. Post-endgame escape: after Ninth Child, Holy Grail is disabled.
        # The player is returned to IBMain and must physically walk to a
        # grail-enabling area, re-enable Holy Grail, then warp or walk to Cliff.
        # This is the same model used by _log_ibmain_escape_path and mirrors
        # the JS tracker's calculateEscapeRoute logic.
        #
        # A seed where IBMain can reach VoD (grail-enabling) but all grail-warp
        # destinations are physically disconnected from Cliff still fails here.
        # Example: Cliff ↔ MausoleumofGiants in an isolated 2-area island —
        # IBMain → VoD passes the old _ibmain_can_escape check, but no grail
        # warp destination connects to Cliff, so the game is unbeatable.
        extended_graph, _ = self._ibmain_escape_graph(graph)
        visited_ib: Set[AreaID] = {AreaID.IBMain}
        q_ib: deque = deque([AreaID.IBMain])
        while q_ib:
            cur = q_ib.popleft()
            if cur == AreaID.Cliff:
                break
            for nxt in extended_graph.get(cur, ()):
                if nxt not in visited_ib:
                    visited_ib.add(nxt); q_ib.append(nxt)
        if AreaID.Cliff not in visited_ib:
            print(f"[ER] Attempt {attempt}: FAIL — IBMain cannot reach Cliff post-endgame "
                  f"(even via Holy Grail warps from grail-enabling areas)")
            return False

        # 2. Orphaned regions check
        #
        # Guardians feed the soul gate kill counter. An unreachable guardian
        # makes every soul gate that needs its kill permanently impassable,
        # breaking the win condition regardless of accessibility setting.
        # FinalBoss locations are similarly always required.
        #
        # IMPORTANT: use get_max_reachable_regions() here, not _reachable_from().
        # _reachable_from() is a dumb BFS that ignores soul gate kill requirements,
        # so it can mark an area as "reachable" even when it's behind a soul gate
        # whose kill threshold can only be met by guardians inside that same area —
        # a circular deadlock that only the flood-fill simulation detects.
        sg_reachable: Set[AreaID] = self.get_max_reachable_regions()

        for region in self.world.multiworld.regions:
            if region.player != self.world.player:
                continue
            if not hasattr(region, 'game_area_id'):
                continue
            for loc in region.locations:
                loc_type = getattr(loc, 'location_type', None)
                # Always fatal — guardian kill count or win condition broken
                if loc_type in (LocationType.Guardian, LocationType.FinalBoss):
                    if region.name not in sg_reachable:
                        print(f"[ER] Attempt {attempt}: FAIL — unreachable {loc_type.value} "
                              f"(soul gate deadlock): {loc.name} in {region.name}")
                        return False
                # Full accessibility — any unreachable location is fatal
                elif self.options.accessibility.value == 2:
                    if region.game_area_id not in reachable_from_start:
                        print(f"[ER] Attempt {attempt}: FAIL — orphaned area (full): {region.name}")
                        return False

        # 3. One-way exit must-escape check
        can_reach_escape: Set[AreaID] = set(escape_areas)
        rq: deque = deque(escape_areas)
        while rq:
            cur = rq.popleft()
            for prev in reverse_graph.get(cur, ()):
                if prev not in can_reach_escape:
                    can_reach_escape.add(prev)
                    rq.append(prev)

        for e in self.entrances:
            if not e.connected_region:
                continue
            if e.game_exit_id not in ONE_WAY_EXITS:
                continue
            logic = getattr(e, '_original_logic', '') or ''
            if 'false' in logic.lower():
                continue
            src = e.parent_region.game_area_id
            if src not in reachable_from_start:
                continue
            dst = e.connected_region.game_area_id
            if dst not in can_reach_escape:
                print(f"[ER] Attempt {attempt}: FAIL — one-way exit {e.game_exit_id} "
                      f"leads to {dst} which can't reach escape")
                return False

        return True

    # ============================================================
    # Misc helpers
    # ============================================================

    def _get_entrance_by_id(self, exit_id: ExitID) -> Optional[LM2Entrance]:
        for e in self.entrances:
            if e.game_exit_id == exit_id:
                return e
        return None

    def _get_exits_of_type(self, exit_type: ExitType) -> List[LM2Entrance]:
        return [e for e in self.entrances if e.exit_type == exit_type]

    def _creates_start_loop(self, entrance: LM2Entrance) -> bool:
        """
        Return True if pairing this entrance with the starting entrance
        would create an isolated two-area loop, trapping the player.
        """
        if not self.starting_entrance:
            return False

        start = self.starting_entrance
        eid   = entrance.game_exit_id

        if start == ExitID.f00GateY0:
            return eid in {ExitID.f00GateYA, ExitID.f00GateYB, ExitID.f00GateYC, ExitID.f00Down}
        if start == ExitID.f01Right:
            return eid == ExitID.f01Start
        if start == ExitID.f01Start:
            return eid == ExitID.f01Right
        if start == ExitID.f02Up:
            return eid in {ExitID.f02Bifrost, ExitID.f02Down, ExitID.f02GateYA}
        if start == ExitID.f02Bifrost:
            return eid in {ExitID.f02Up, ExitID.f02Down, ExitID.f02GateYA}
        if start == ExitID.f03Right:
            return eid in {ExitID.f03Down1, ExitID.f03Down2, ExitID.f03Down3,
                           ExitID.f03Up, ExitID.f03GateYC, ExitID.f03In}
        if start == ExitID.f04Up:
            return eid in {ExitID.f04Up2, ExitID.f04Up3, ExitID.f04GateYB}
        return False

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