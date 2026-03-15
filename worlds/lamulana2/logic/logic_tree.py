# logic/logic_tree.py
# Port of LogicTree.cs
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from .logic_tokens import Token, TokenType, LogicTokeniser
from .logic_shunting_yard import LogicShuntingYard

if TYPE_CHECKING:
    from BaseClasses import CollectionState


class LogicTreeError(Exception):
    pass


# ---------- AST Nodes ----------

class LogicNode(ABC):
    @abstractmethod
    def evaluate(self, player_state) -> bool:
        pass

    @abstractmethod
    def compile(self, world) -> "Callable[[CollectionState], bool]":
        """
        Compile this node into a native Python closure.
        The closure takes an AP CollectionState and returns bool.
        Rules that are static w.r.t. options are pre-evaluated into constants.
        Rules requiring live collection data use state.has()/state.count() directly
        where possible, and fall back to a cached PlayerStateAdapter for the rest.
        """
        pass


# ---------- Module-level helpers for compile() ----------

def _make_adapter_rule(
    name: str,
    args: list[str],
    world,
) -> "Callable[[CollectionState], bool]":
    """
    Fallback: evaluate via a cached PlayerStateAdapter.
    The adapter is rebuilt only when the player's prog_items count changes,
    so it is constructed at most once per sphere step rather than once per check.
    """
    player = world.player
    multiworld = world.multiworld
    options = world.options

    def rule(state: "CollectionState") -> bool:
        from .player_state import get_cached_adapter
        adapter = get_cached_adapter(state, player, multiworld, options)
        return adapter.evaluate_rule(name, args)

    return rule


def _can_reach_compiled(area_name: str, world) -> "Callable[[CollectionState], bool]":
    """
    Compile a CanReach(area) rule into a direct region lookup.
    Lazily resolves the Region object on first call so it is safe to call
    during location construction (before regions_by_area_id is fully built).
    """
    from ..ids import AreaID

    normalized = re.sub(r'\s+', '', area_name)
    try:
        area_id = AreaID[normalized]
    except KeyError:
        return lambda state: False

    player = world.player
    # Capture world by reference; regions_by_area_id is populated later
    _region_cache: list = [None]  # mutable cell to cache the resolved Region

    def rule(state: "CollectionState") -> bool:
        region = _region_cache[0]
        if region is None:
            regions_by_area = getattr(world, 'regions_by_area_id', None)
            if not regions_by_area or area_id not in regions_by_area:
                return False
            region = regions_by_area[area_id]
            _region_cache[0] = region
        return state.can_reach(region, "Region", player)

    return rule


# ---------- RuleNode ----------

class RuleNode(LogicNode):
    def __init__(self, rule: str):
        self.rule = rule  # e.g. "Has(Mjolnir)"

    def evaluate(self, player_state) -> bool:
        name, args = self._parse_rule(self.rule)
        return player_state.evaluate_rule(name, args)

    def compile(self, world) -> "Callable[[CollectionState], bool]":  # noqa: C901
        name, args = self._parse_rule(self.rule)
        player = world.player
        options = world.options

        # ── Static / option-only rules (pre-evaluated to a constant) ──────────

        if name == "True":
            return lambda state: True

        if name == "False":
            return lambda state: False

        if name == "Setting":
            setting_name = args[0] if args else ""
            # Delegate to a lightweight inline evaluation so we don't need
            # the full adapter just to read an option value.
            result = _eval_setting(setting_name, options)
            return lambda state, r=result: r

        if name == "Start":
            area_name = args[0] if args else ""
            from ..ids import AreaID
            norm = re.sub(r'\s+', '', area_name)
            try:
                target = AreaID[norm]
            except KeyError:
                return lambda state: False
            starting_area = getattr(world, 'starting_area', None)
            result = (starting_area == target)
            return lambda state, r=result: r

        if name == "Glitch":
            glitch_name = args[0] if args else ""
            if glitch_name == "Costume Clip":
                result = bool(options.costume_clip)
                return lambda state, r=result: r
            return lambda state: False

        if name == "HasMap":
            if options.remove_maps:
                return lambda state: True
            item = args[0] if args else ""
            return lambda state, i=item, p=player: state.has(i, p)

        if name == "HasResearch":
            if options.remove_research:
                return lambda state: True
            item = args[0] if args else ""
            return lambda state, i=item, p=player: state.has(i, p)

        # ── Direct state.has() / state.count() rules ──────────────────────────

        if name in ("Has", "IsDead", "PuzzleFinished"):
            item = args[0] if args else ""

            # Progressive Whip
            if "Whip" in item:
                level = {"Leather Whip": 1, "Chain Whip": 2, "Flail Whip": 3}.get(item, 0)
                if level:
                    return lambda state, l=level, p=player: (
                        state.count("Progressive Whip", p) >= l
                    )

            # Progressive Shield
            shield_levels = {"Buckler": 1, "Silver Shield": 2, "Angel Shield": 3}
            if item in shield_levels:
                level = shield_levels[item]
                return lambda state, l=level, p=player: (
                    state.count("Progressive Shield", p) >= l
                )

            # Ammo items require the starting-weapon ammo check in the adapter
            if item.endswith("Ammo"):
                return _make_adapter_rule(name, args, world)

            # Plain item
            return lambda state, i=item, p=player: state.has(i, p)

        if name == "OrbCount":
            n = int(args[0])
            return lambda state, required=n, p=player: (
                state.count("Sacred Orb", p) >= required
            )

        if name == "SkullCount":
            n = int(args[0])
            if options.remove_excess_skulls:
                cap = (
                    options.required_skulls.value
                    if hasattr(options.required_skulls, "value")
                    else int(options.required_skulls)
                )
                return lambda state, required=n, c=cap, p=player: (
                    min(state.count("Crystal Skull", p), c) >= required
                )
            return lambda state, required=n, p=player: (
                state.count("Crystal Skull", p) >= required
            )

        if name == "AnkhCount":
            n = int(args[0])
            # When guardian_specific_ankhs is OFF, generic pool counter suffices.
            if not getattr(options, "guardian_specific_ankhs", False):
                return lambda state, required=n, p=player: (
                    state.count("Ankh Jewel", p) >= required
                )
            # ON: softlock check just needs at least 1 — adapter handles it.
            return _make_adapter_rule(name, args, world)

        if name == "Dissonance":
            n = int(args[0]) if args else 0
            # C# parity: Dissonance count OR Progressive Beherit >= n+1
            return lambda state, required=n, p=player: (
                state.count("Dissonance", p) >= required
                or state.count("Progressive Beherit", p) >= (required + 1)
            )

        if name == "CanChant":
            mantra = args[0] if args else ""
            return lambda state, m=mantra, p=player: (
                state.has("Djed Pillar", p)
                and state.has("Mantra", p)
                and state.has(m, p)
            )

        # ── Region reachability (no adapter needed) ───────────────────────────

        if name == "CanReach":
            area_name = args[0] if args else ""
            return _can_reach_compiled(area_name, world)

        # ── Everything else → cached adapter ─────────────────────────────────

        return _make_adapter_rule(name, args, world)

    @staticmethod
    def _parse_rule(rule: str) -> tuple[str, list[str]]:
        """
        Parses 'RuleName(arg1,arg2,...)' with correct nested-paren handling.
        Fixes the original rstrip(')') bug that mangled 'Ankh Jewel (Fafnir)'.
        """
        if "(" not in rule:
            return rule, []

        paren_idx = rule.index("(")
        name = rule[:paren_idx]
        depth = 0
        content_start = paren_idx + 1
        content_end = len(rule)

        for i in range(paren_idx, len(rule)):
            c = rule[i]
            if c == "(":
                depth += 1
                if depth == 1:
                    content_start = i + 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    content_end = i
                    break

        content = rule[content_start:content_end].strip()
        if not content:
            return name, []
        return name, [arg.strip() for arg in content.split(",")]

    def __repr__(self):
        return f"Rule({self.rule})"


# ---------- AndNode ----------

class AndNode(LogicNode):
    def __init__(self, left: LogicNode, right: LogicNode):
        self.left = left
        self.right = right

    def evaluate(self, player_state) -> bool:
        return self.left.evaluate(player_state) and self.right.evaluate(player_state)

    def compile(self, world) -> "Callable[[CollectionState], bool]":
        left = self.left.compile(world)
        right = self.right.compile(world)
        return lambda state: left(state) and right(state)

    def __repr__(self):
        return f"And({self.left}, {self.right})"


# ---------- OrNode ----------

class OrNode(LogicNode):
    def __init__(self, left: LogicNode, right: LogicNode):
        self.left = left
        self.right = right

    def evaluate(self, player_state) -> bool:
        return self.left.evaluate(player_state) or self.right.evaluate(player_state)

    def compile(self, world) -> "Callable[[CollectionState], bool]":
        left = self.left.compile(world)
        right = self.right.compile(world)
        return lambda state: left(state) or right(state)

    def __repr__(self):
        return f"Or({self.left}, {self.right})"


# ---------- LogicTree Builder ----------

class LogicTree:
    """
    Faithful port of LogicTree.cs
    """

    @staticmethod
    def parse(expr: str | list[Token]) -> LogicNode:
        if isinstance(expr, str):
            tokens = LogicTokeniser(expr).tokenise()
        else:
            tokens = expr

        rpn = LogicShuntingYard(tokens).to_rpn()
        stack: list[LogicNode] = []

        for token in rpn:
            if token.type == TokenType.RULE:
                stack.append(RuleNode(token.value))
                continue

            if token.type in (TokenType.AND, TokenType.OR):
                if len(stack) < 2:
                    raise LogicTreeError("Invalid logic expression")

                right = stack.pop()
                left = stack.pop()

                if token.type == TokenType.AND:
                    stack.append(AndNode(left, right))
                else:
                    stack.append(OrNode(left, right))
                continue

            raise LogicTreeError(f"Unexpected token in RPN: {token.type}")

        if len(stack) != 1:
            raise LogicTreeError("Invalid logic expression")

        return stack[0]


# ---------- Setting evaluation helper (options-only, no state needed) ----------

def _eval_setting(setting_name: str, options) -> bool:
    """
    Mirrors the logic in PlayerStateAdapter._setting() but operates purely
    on options so the result can be pre-computed at compile time.
    """
    explicit: dict[str, object] = {
        "AutoScan":            lambda: options.auto_scan,
        "Random Ladders":      lambda: options.vertical_entrances,
        "Non Random Ladders":  lambda: not options.vertical_entrances,
        "Random Gates":        lambda: options.gate_entrances,
        "Non Random Gates":    lambda: not options.gate_entrances,
        "Random Soul Gates":   lambda: options.random_soul_gate_value,
        "Non Random Soul Gates": lambda: not options.random_soul_gate_value,
        "Non Random Unique":   lambda: not options.include_unique_transitions,
        "Remove IT Statue":    lambda: options.remove_icefire_treetop_statue,
        "Not Life for HoM":    lambda: not options.life_sigil_to_awaken_hom,
        "CostumeClip":         lambda: options.costume_clip,
    }

    if setting_name in explicit:
        try:
            return bool(explicit[setting_name]())
        except AttributeError:
            return False

    setting_overrides = {
        "FDCForBacksides":   "require_fdc",
        "AutoScan":          "auto_scan",
        "AutoPlaceSkulls":   "auto_skulls",
        "RandomDissonance":  "random_dissonance",
        "RandomResearch":    "random_research",
        "CostumeClip":       "costume_clip",
        "HardBosses":        "logic_difficulty",
        "RemoveITStatue":    "remove_icefire_treetop_statue",
        "LifeForHoM":        "life_sigil_to_awaken_hom",
        "DLCItem":           "dlc_item_logic",
        "RandomCurses":      "random_cursed_chests",
        "RequiredGuardians": "required_guardians",
        "RequiredSkulls":    "required_skulls",
    }

    key = setting_overrides.get(
        setting_name,
        re.sub(r'(?<!^)(?=[A-Z])', '_', setting_name).lower(),
    )

    if not hasattr(options, key):
        return False

    value = getattr(options, key)
    raw = value.value if hasattr(value, "value") else value

    if key == "logic_difficulty":
        return raw == 1

    return bool(raw)