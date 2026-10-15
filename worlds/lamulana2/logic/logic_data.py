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

# ---------------------------------------------------------------------------
# World level (WorldLevel(n))
# ---------------------------------------------------------------------------
#
# The game's world level is G_Difficulty (flag 0,53), read by every mob in
# GroundCharacter.resetParameter: a mob whose LowestLevel..HardestLevel range
# excludes the current level (capped at 6) despawns. That is how enemies start
# appearing in new areas as the world levels up.
#
# G_Difficulty starts at 0 (Normal) or 3 (Hard: the Mausoleum tablet, or the
# game_difficulty option). It rises by +1 at most three times, via the
# hardWatcher1/2/3 FlagWatchers once storyChecker (flag 3,30) reaches 60 / 120 /
# 190. Normal therefore runs 0..3 and Hard 3..6.
#
# storyChecker is a tally raised on pickup of the items below (vanilla
# EventItemScript getFlags; in AP, SceneRandomizer.CreateGetFlags and
# ItemGrantManager on receipt, so it follows the item, not the location).
# Full tally: 9 Ankh Jewels + 12 Crystal Skulls + 30 story items = 200.
WORLD_LEVEL_TALLY: Dict[str, int] = {
    "Ankh Jewel": 4,
    "Ankh Jewel (Fafnir)": 4,
    "Ankh Jewel (Vritra)": 4,
    "Ankh Jewel (Kujata)": 4,
    "Ankh Jewel (Aten-Ra)": 4,
    "Ankh Jewel (Jormungand)": 4,
    "Ankh Jewel (Anu)": 4,
    "Ankh Jewel (Surtr)": 4,
    "Ankh Jewel (Echidna)": 4,
    "Ankh Jewel (Hel)": 4,
    "Crystal Skull": 4,
    "Djed Pillar": 4,
    "Mjolnir": 4,
    "Ancient Battery": 4,
    "Lamp of Time": 4,
    "Pochette Key": 4,
    "Pyramid Crystal": 4,
    "Vessel": 4,
    "Egg of Creation": 4,
    "Giant's Flute": 4,
    "Cog of Antiquity": 4,
    "Mulana Talisman": 4,
    "Glove": 4,
    "Dinosaur Figure": 4,
    "Gale Fibula": 4,
    "Flame Torc": 4,
    "Power Band": 4,
    "Ganesha's Talisman": 4,
    "Maat's Feather": 4,
    "Feather": 4,
    "Frey's Ship": 4,
    "Harp": 4,
    "Destiny Tablet": 4,
    "Secret Treasure of Life": 4,
    "Origin Sigil": 4,
    "Birth Sigil": 4,
    "Life Sigil": 4,
    "Death Sigil": 4,
    "Claydoll Suit": 4,
    "Holy Grail": 2,
    "Grapple Claw": 2,
}

# storyChecker needed for each +1 step above the starting level.
WORLD_LEVEL_THRESHOLDS: Tuple[int, ...] = (60, 120, 190)

# Starting G_Difficulty per game_difficulty option value (normal, hard).
WORLD_LEVEL_BASE: Tuple[int, ...] = (0, 3)

# The hardWatcher FlagWatchers live only in these fields (field00 RoY, 03 IB,
# 05 DF, 06 SotFG, 07 GotD, 12 AC), so a threshold is only applied once the
# player enters one of them. Any region of those fields will do.
WORLD_LEVEL_WATCHER_AREAS: Tuple[str, ...] = (
    "RoY", "RoYTopLeft", "RoYTopRight", "RoYTopMiddle", "RoYMiddle", "RoYBottom", "RoYBottomLeft",
    "IBBifrost", "IBTop", "IBTopLeft", "IBCetusLadder", "IBMain", "IBRight", "IBBottom", "IBLeft",
    "IBLeftSG", "IBBattery", "IBDinosaur", "IBMoon", "IBLadder", "IBBoat",
    "DFEntrance", "DFRight", "DFMain", "DFTop",
    "SotFGMain", "SotFGGrail", "SotFGTop", "SotFGBalor", "SotFGLeft",
    "GotD", "GotDWedjet",
    "ACBottom", "ACWind", "ACTablet", "ACMain",
)


def world_level_steps(level: int, game_difficulty: int):
    """
    WorldLevel(level) means G_Difficulty >= level. Returns the number of
    storyChecker steps needed above the starting level: 0 (always true),
    1..3, or None (unreachable: needs more than three steps).
    """
    base = WORLD_LEVEL_BASE[1 if game_difficulty else 0]
    steps = level - base
    if steps <= 0:
        return 0
    if steps > len(WORLD_LEVEL_THRESHOLDS):
        return None
    return steps
