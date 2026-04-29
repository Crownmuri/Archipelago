from typing import Dict
from dataclasses import dataclass
from Options import Choice, Toggle, DefaultOnToggle, Range, ItemsAccessibility, PerGameCommonOptions, DeathLink

# --- Choice Definitions ---

class AutoScan(DefaultOnToggle):
    """Automatically scan tablets when read."""
    display_name = "Auto Scan Tablets"

class AutoSkulls(DefaultOnToggle):
    """Auto-Place Crystal Skulls in Nibiru."""
    display_name = "Auto Place Skulls"

# --- Item Placement Options ---
# Each needs its own subclass so Archipelago's template generator can distinguish them.

class RandomGrail(Choice):
    """Randomize the Holy Grail."""
    display_name = "Random Grail"
    option_starting = 0
    option_shuffled = 1
    default = 0

class RandomFDC(Choice):
    """Randomize the Future Development Company."""
    display_name = "Random FDC"
    option_starting = 0
    option_shuffled = 1
    default = 0

class RandomScanner(Choice):
    """Randomize the Hand Scanner."""
    display_name = "Random Scanner"
    option_starting = 0
    option_shuffled = 1
    default = 1

class RandomCodex(Choice):
    """Randomize the Codices."""
    display_name = "Random Codices"
    option_starting = 0
    option_shuffled = 1
    default = 1

class RandomRing(Choice):
    """Randomize the Ring."""
    display_name = "Random Ring"
    option_starting = 0
    option_shuffled = 1
    default = 1

class RandomShellHorn(Choice):
    """Randomize the Shell Horn."""
    display_name = "Random Shell Horn"
    option_starting = 0
    option_shuffled = 1
    default = 1

class RandomMapsSoftware(Choice):
    """Randomize Maps Software."""
    display_name = "Random Maps Software"
    option_starting = 0
    option_shuffled = 1
    default = 1

class MantraPlacement(Choice):
    """random: Mantras can be anywhere.
    only_murals: Mantras are restricted to mural locations.
    original: Mantras stay in their vanilla mural locations."""
    display_name = "Mantra Placement"
    option_original = 0
    option_only_murals = 1
    option_shuffled = 2
    default = 2

class ShopPlacement(Choice):
    """random: All shop items are shuffled.
    at_least_one: Each shop is guaranteed at least one non-ammo/weight item.
    original: Shops keep vanilla items."""
    display_name = "Shop Placement"
    option_original = 0
    option_at_least_one = 1
    option_shuffled = 2
    default = 2

class EchidnaDifficulty(Choice):
    """The Boss Echidna phase difficulty."""
    display_name = "Echidna Difficulty"
    option_child = 0
    option_teenager = 1
    option_young_adult = 2
    option_adult = 3
    option_normal = 4
    default = 4

class ItemChestColor(Choice):
    """Color for item chests."""
    display_name = "Item Chest Color"
    option_blue = 0
    option_turquoise = 1
    option_red = 2
    option_pink = 3
    option_yellow = 4
    default = 0

class FillerChestColor(Choice):
    """Color for filler chests."""
    display_name = "Filler Chest Color"
    option_blue = 0
    option_turquoise = 1
    option_red = 2
    option_pink = 3
    option_yellow = 4
    default = 4

class APChestColor(Choice):
    """Color for AP chests."""
    display_name = "AP Chest Color"
    option_blue = 0
    option_turquoise = 1
    option_red = 2
    option_pink = 3
    option_yellow = 4
    default = 1

# --- Logic Changes ---
class LogicDifficulty(Choice):
    """Logic difficulty setting."""
    display_name = "Logic Difficulty"
    option_standard = 0
    option_hard = 1
    default = 0

class GuardianSpecificAnkhJewels(DefaultOnToggle):
    """Makes Ankhs only usable at their designated bosses."""
    display_name = "Guardian Specific Ankh Jewels"

class CostumeClip(Toggle):
    """Include Glitched logic (costume clip)."""
    display_name = "Costume Clip"

# --- Item Pool ---
class RandomResearch(DefaultOnToggle):
    """Shuffle research into the AP item pool."""
    display_name = "Random Research"

class RandomDissonance(DefaultOnToggle):
    """Adds Progressive Beherit into the item pool and places chests at dissonance locations."""
    display_name = "Random Dissonance"

class RandomCursedChests(DefaultOnToggle):
    """Randomize Cursed Chests."""
    display_name = "Random Cursed Chests"

class Potsanity(Toggle):
    """Include pots as randomized location checks. Adds ~300 pot locations containing filler rewards (coins, weights, ammo). Not compatible with legacy seed files."""
    display_name = "Potsanity"

class RemoveResearch(Toggle):
    """Remove Research Notes from the item pool."""
    display_name = "Remove Research Notes"

class RemoveMaps(Toggle):
    """Remove Map Software items from the item pool."""
    display_name = "Remove Maps"

class RemoveSkulls(DefaultOnToggle):
    """Remove Excess Crystal Skulls from the item pool."""
    display_name = "Remove Skulls"

# --- QoL ---
class RequireFDC(DefaultOnToggle):
    """Require Future Development Company for backsides."""
    display_name = "Require FDC"

class DLCItemLogic(Toggle):
    """Considers the DLC Item for accessibility."""
    display_name = "DLC Item Logic"

class LifeSigilToAwakenHoM(DefaultOnToggle):
    """Require Life Sigil to Awaken Hall of Malice."""
    display_name = "Life Sigil to Awaken HoM"

class RemoveIcefireTreetopStatue(DefaultOnToggle):
    """Remove Icefire Treetop Statue for more accessibility."""
    display_name = "Remove Icefire Treetop Statue"

class WriteSeedFile(Toggle):
    """Writes a seed.lm2r file for backwards compatibility. Note that the original randomizer will not feature custom filler or prevent you from using Guardian Specific Ankh Jewels freely."""
    display_name = "Write Legacy Seed File."

# --- Entrance Randomizer ---
class HorizontalEntrances(Toggle):
    """Shuffle horizontal entrances."""
    display_name = "Horizontal Entrances"

class VerticalEntrances(Toggle):
    """Shuffle vertical entrances."""
    display_name = "Vertical Entrances"

class GateEntrances(Toggle):
    """Shuffle gate entrances."""
    display_name = "Gate Entrances"

class UniqueTransitions(Toggle):
    """Shuffle unique transitions."""
    display_name = "Unique Transitions"

class SoulGateEntrances(Toggle):
    """Shuffle soul gate entrances."""
    display_name = "Soul Gate Entrances"

class IncludeNineSoulGates(Toggle):
    """Include nine soul gates in randomization."""
    display_name = "Include Nine Soul Gates"

class RandomSoulGateValue(Toggle):
    """Randomize soul gate cost values."""
    display_name = "Random Soul Gate Value"

class FullRandomEntrances(Toggle):
    """Fully randomize all entrances across area types."""
    display_name = "Full Random Entrances"

class PreventAreaLoops(Toggle):
    """Prevent entrance randomization from pairing exits within the same area."""
    display_name = "Prevent Area Loops"

# --- Starting Area ---
class StartingArea(Choice):
    """Starting area for the player. Use weighted YAML to randomize, e.g.
        starting_area:
          village_of_departure: 25
          annwfn: 50
          immortal_battlefield: 50

    Some areas require specific entrance randomizer options to be enabled. If the chosen area's
    prerequisites aren't met, a uniform re-roll is performed across the remaining valid areas
    (a warning is logged); if no valid options remain, falls back to Village of Departure.

    Requires vertical_entrances: icefire_treetop.
    Requires gate_entrances: divine_fortress, shrine_of_the_frost_giants, takamagahara_shrine,
    valhalla, dark_star_lords_mausoleum, ancient_chaos, hall_of_malice."""
    display_name = "Starting Area"
    option_village_of_departure = 0
    option_roots_of_yggdrasil = 1
    option_annwfn = 2
    option_immortal_battlefield = 3
    option_icefire_treetop = 4
    option_divine_fortress = 5
    option_shrine_of_the_frost_giants = 6
    option_takamagahara_shrine = 7
    option_valhalla = 8
    option_dark_star_lords_mausoleum = 9
    option_ancient_chaos = 10
    option_hall_of_malice = 11
    default = 0

# --- Starting Weapon ---
class StartingWeapon(Choice):
    """Starting weapon for the player. Use weighted YAML to randomize, e.g.
        starting_weapon:
          leather_whip: 1
          katana: 3"""
    display_name = "Starting Weapon"
    option_leather_whip = 0
    option_knife = 1
    option_rapier = 2
    option_axe = 3
    option_katana = 4
    option_shuriken = 5
    option_rolling_shuriken = 6
    option_earth_spear = 7
    option_flare = 8
    option_caltrops = 9
    option_chakram = 10
    option_bomb = 11
    option_pistol = 12
    option_claydoll_suit = 13
    default = 0

# --- Range Definitions ---

class GuardianKills(Range):
    """Number of Guardians required to be defeated to seal the Corridor of Blood."""
    display_name = "Required Guardian Kills"
    range_start = 0
    range_end = 9
    default = 5

class RequiredSkulls(Range):
    """Number of Crystal Skulls required for Nibiru Dissonance."""
    display_name = "Nibiru Dissonance Skulls"
    range_start = 1
    range_end = 12
    default = 6

class CursedChestCount(Range):
    """Number of Cursed Chests to randomize."""
    display_name = "Cursed Chests"
    range_start = 0
    range_end = 86
    default = 4

class StartingMoney(Range):
    """Starting money amount."""
    display_name = "Starting Money"
    range_start = 0
    range_end = 999
    default = 200

class StartingWeights(Range):
    """Starting weights amount."""
    display_name = "Starting Weights"
    range_start = 0
    range_end = 100
    default = 10

# --- Main Options Class ---

@dataclass
class LM2Options(PerGameCommonOptions):

    accessibility: ItemsAccessibility

    # Item Shuffle
    random_grail: RandomGrail
    random_scanner: RandomScanner
    random_codices: RandomCodex
    random_fdc: RandomFDC
    random_ring: RandomRing
    random_shell_horn: RandomShellHorn
    random_maps_software: RandomMapsSoftware
    mantra_placement: MantraPlacement
    shop_placement: ShopPlacement

    # Check Removal
    remove_research: RemoveResearch
    remove_maps: RemoveMaps
    remove_excess_skulls: RemoveSkulls

    # Logic & Difficulty
    guardian_specific_ankhs: GuardianSpecificAnkhJewels
    logic_difficulty: LogicDifficulty
    echidna_difficulty: EchidnaDifficulty
    costume_clip: CostumeClip
    random_research: RandomResearch
    random_dissonance: RandomDissonance
    require_fdc: RequireFDC
    dlc_item_logic: DLCItemLogic
    life_sigil_to_awaken_hom: LifeSigilToAwakenHoM
    remove_icefire_treetop_statue: RemoveIcefireTreetopStatue

    # Requirements
    required_guardians: GuardianKills
    required_skulls: RequiredSkulls
    random_cursed_chests: RandomCursedChests
    cursed_chests: CursedChestCount

    # Sanities
    potsanity: Potsanity

    # Entrance Randomizer
    horizontal_entrances: HorizontalEntrances
    vertical_entrances: VerticalEntrances
    gate_entrances: GateEntrances
    unique_transitions: UniqueTransitions
    soul_gate_entrances: SoulGateEntrances
    include_nine_soul_gates: IncludeNineSoulGates
    random_soul_gate_value: RandomSoulGateValue
    full_random_entrances: FullRandomEntrances
    prevent_area_loops: PreventAreaLoops

    # Starting Area / Weapon
    starting_area: StartingArea
    starting_weapon: StartingWeapon

    # QoL
    auto_scan: AutoScan
    auto_skulls: AutoSkulls
    starting_money: StartingMoney
    starting_weights: StartingWeights
    item_chest_color: ItemChestColor
    filler_chest_color: FillerChestColor
    ap_chest_color: APChestColor

    write_seed_file: WriteSeedFile

    death_link: DeathLink
