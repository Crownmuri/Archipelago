"""
Shared logic vocabulary.

Logic is evaluated on two paths: RuleNode.compile() in logic_tree.py builds
closures over `options` at compile time, and PlayerStateAdapter in
player_state.py interprets the same rules against a live state.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# Setting(...) names whose spelling does not survive the CamelCase -> snake_case
# fallback, mapped to the real option attribute.
SETTING_OVERRIDES: Dict[str, str] = {
    "FDCForBacksides":   "require_fdc",
    "AutoScan":          "auto_scan",
    "AutoPlaceSkulls":   "auto_skulls",
    "RandomDissonance":  "random_dissonance",
    "RandomResearch":    "random_research",
    "CostumeClip":       "costume_clip",
    "MinimalBosses":     "logic_difficulty",
    "RemoveITStatue":    "remove_icefire_treetop_statue",
    "LifeForHoM":        "life_sigil_to_awaken_hom",
    "DLCItem":           "dlc_item_logic",
    "RandomCurses":      "random_cursed_chests",
    "RequiredGuardians": "required_guardians",
    "RequiredSkulls":    "required_skulls",
}

# Setting(...) names that are a derived predicate rather than a single option
# -- usually the negation of one. Each takes the options object.
EXPLICIT_SETTINGS: Dict[str, Callable[[object], bool]] = {
    "AutoScan":              lambda o: bool(o.auto_scan),
    "Random Ladders":        lambda o: bool(o.vertical_entrances),
    "Non Random Ladders":    lambda o: not o.vertical_entrances,
    "Random Gates":          lambda o: bool(o.gate_entrances),
    "Non Random Gates":      lambda o: not o.gate_entrances,
    "Random Soul Gates":     lambda o: bool(o.random_soul_gate_value),
    "Non Random Soul Gates": lambda o: not o.random_soul_gate_value,
    "Non Random Unique":     lambda o: not o.unique_transitions,
    "Remove IT Statue":      lambda o: bool(o.remove_icefire_treetop_statue),
    "Not Life for HoM":      lambda o: not o.life_sigil_to_awaken_hom,
    "CostumeClip":           lambda o: bool(o.costume_clip),
}

# ---------------------------------------------------------------------------
# Progressive families
# ---------------------------------------------------------------------------

# Named tiers that resolve to a count of the progressive item.
WHIP_LEVELS: Dict[str, int] = {
    "Leather Whip": 1,
    "Chain Whip": 2,
    "Flail Whip": 3,
}

SHIELD_LEVELS: Dict[str, int] = {
    "Buckler": 1,
    "Silver Shield": 2,
    "Angel Shield": 3,
}

# The Beherit ships under two labels: seven "Progressive Beherit" when
# random_dissonance is on, a single "Beherit" when it is off. World.json only
# ever spells the progressive form, so both answer to it. Exactly one of the
# two exists in any given seed, so summing their counts is exact.
BEHERIT_NAMES: Tuple[str, ...] = ("Progressive Beherit", "Beherit")
