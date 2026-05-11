from typing import Dict
from dataclasses import dataclass
from Options import Choice, Toggle, DefaultOnToggle, Range, ItemsAccessibility, PerGameCommonOptions, DeathLink

# --- Choice Definitions ---

class StartingArea(Choice):
    """Starting area for the player.
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

class StartingWeapon(Choice):
    """Starting weapon for the player."""
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

class RandomGrail(Choice):
    """Randomize the Holy Grail."""
    display_name = "Random Grail"
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

class RandomFDC(Choice):
    """Randomize the Future Development Company software."""
    display_name = "Random FDC"
    option_starting = 0
    option_shuffled = 1
    default = 0

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
    """Randomize Maps & Mapping Software."""
    display_name = "Random Maps & Mapping Software"
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
    original: Shops keep vanilla items.
    Note: If [original] is selected, FDC, Codices and Hand Scanner cannot not be randomized."""
    display_name = "Shop Placement"
    option_original = 0
    option_at_least_one = 1
    option_shuffled = 2
    default = 2

class RandomResearch(DefaultOnToggle):
    """Add all Kosugi Research Papers into the AP item pool.
    If disabled, they will be static untracked locations in-game."""
    display_name = "Random Research"

class RemoveResearch(Toggle):
    """Remove Kosugi Research Notes from the item pool.
    This means that 10 filler items will take their place."""
    display_name = "Remove Research Notes"

class RemoveMaps(Toggle):
    """Removes maps from the item pool.
    This means that 16 filler items will take their place."""
    display_name = "Remove Maps"

class RequiredSkulls(Range):
    """Number of Crystal Skulls required for Nibiru Dissonance."""
    display_name = "Nibiru Dissonance Skulls"
    range_start = 1
    range_end = 12
    default = 6

class RemoveSkulls(Toggle):
    """Remove Excess Crystal Skulls from the item pool."""
    display_name = "Remove Skulls"

class RandomDissonance(DefaultOnToggle):
    """All 6 dissonance locations are converted into chests and turns the Beherit into 7 progressive items.
    If true, sealing the Corridor of Blood requires all 7 Progressive Beherit in addition to the set GuardianKills.
    If false, sealing the Corridor of Blood requires absorbing all dissonance from their original locations."""
    display_name = "Random Dissonance"

class GuardianKills(Range):
    """Only applies if RandomDissonance is on.
    Number of Guardians required to be defeated to seal the Corridor of Blood.
    Note: the Spiral Boat soul gate value will be adjusted to be at or below this value.
    This way, you will always be able to reach the final area without requiring additional guardians."""
    display_name = "Required Guardian Kills"
    range_start = 0
    range_end = 9
    default = 5

class Potsanity(Toggle):
    """Include pots as randomized location checks (WIP).
   As of April 2026, 49 pot locations containing filler rewards (coins, weights, ammo). 
   Not compatible with legacy seed files."""
    display_name = "Potsanity"

class GuardianSpecificAnkhJewels(DefaultOnToggle):
    """Makes Ankhs only usable at their designated bosses."""
    display_name = "Guardian Specific Ankh Jewels"

class LogicDifficulty(Choice):
    """Logic difficulty setting.
    - standard: intuitive logic - certain HP / damage thresholds required for bosses.
    - hard: minimal logic - as long as bosses can be theoretically beaten. """
    display_name = "Logic Difficulty"
    option_standard = 0
    option_hard = 1
    default = 0

class EchidnaDifficulty(Choice):
    """The Boss Echidna phase difficulty."""
    display_name = "Echidna Difficulty"
    option_child = 0
    option_teenager = 1
    option_young_adult = 2
    option_adult = 3
    option_normal = 4
    default = 4

class CostumeClip(Toggle):
    """Include Glitched logic (i.e. costume clip).
    Costume Clip: jump and pause on the same frame.
    Once you hear the jump SFX as you open the menu, switch costumes.
    This allows you to clip into objects like pots which can push you through walls."""
    display_name = "Costume Clip"

class RequireFDC(DefaultOnToggle):
    """Require Future Development Company for backsides."""
    display_name = "Require FDC"

class DLCItemLogic(Toggle):
    """Considers the DLC Item for accessibility."""
    display_name = "DLC Item Logic"

class LifeSigilToAwakenHoM(DefaultOnToggle):
    """Require Life Sigil to Awaken Hall of Malice.
    If enabled, will consider access to the grail point in logic."""
    display_name = "Life Sigil to Awaken HoM"

class RemoveIcefireTreetopStatue(DefaultOnToggle):
    """Remove Icefire Treetop Statue for more accessibility."""
    display_name = "Remove Icefire Treetop Statue"

class RandomCursedChests(DefaultOnToggle):
    """Randomize Cursed Chests
    Vanilla:
    - FlameTorcChest (Surtr)
    - GiantsFluteChest (Echidna)
    - DestinyTabletChest (Anu)
    - PowerBandChest (Belial)"""
    display_name = "Random Cursed Chests"

class CursedChestCount(Range):
    """Number of Cursed Chests to randomize."""
    display_name = "Cursed Chests"
    range_start = 0
    range_end = 86
    default = 4

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
    """Shuffle unique transitions.
    (e.g. Annwfn -> Immortal Battlefield / Takamagahara Shrine -> Heaven's Labyrinth)"""
    display_name = "Unique Transitions"

class FullRandomEntrances(Toggle):
    """Mix the enabled randomized entrances across area types."""
    display_name = "Full Random Entrances"

class PreventAreaLoops(Toggle):
    """Prevent entrance randomization from pairing exits within the same area.
    May increase fill success rate if you're having issues with generation."""
    display_name = "Prevent Area Loops"

class SoulGateEntrances(Toggle):
    """Shuffle [1,2,3,5] soul gate entrances with each other.
    Note: does not mix with regular the above regular entrances and transitions."""
    display_name = "Soul Gate Entrances"

class RandomSoulGateValue(Toggle):
    """Randomize soul gate cost values.
    If Soul Gate Entrances is shuffled: shuffle values along with pairing
    If Soul Gate Entrances is vanilla: only shuffle values, keep vanilla pairing."""
    display_name = "Random Soul Gate Value"

class IncludeNineSoulGates(Toggle):
    """Include the two [9] soul gates (HoM to IB Boat) in the Soul Gate pool.
    Can work with Soul Gate Entrances and Random Soul Gate Values separately.
    Note: [9] soul gate is floored to be reachable depending on player set
    RequiredGuardians value if RandomDissonance is enabled."""
    display_name = "Include Nine Soul Gates"

# --- Quality of Life ---

class AutoScan(DefaultOnToggle):
    """Automatically scan tablets when read.
    Requires Hand Scanner in logic if disabled."""
    display_name = "Auto Scan Tablets"

class AutoSkulls(DefaultOnToggle):
    """Auto-Place Crystal Skulls in Nibiru."""
    display_name = "Auto Place Skulls"

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

# --- Other ---

class WriteSeedFile(Toggle):
    """Writes a seed.lm2r file for backwards compatibility. 
    Play AP seeds offline through using the in-game GUI to turn AP filler and Guardian Ankhs on or off.
    The mod can also play original randomizer seeds (will use the original filler and ankh jewel system)
    Does not support Potsanity."""
    display_name = "Write Seed File."

@dataclass
class LM2Options(PerGameCommonOptions):

    accessibility: ItemsAccessibility

    # Starting Location & Items
    starting_area: StartingArea
    starting_weapon: StartingWeapon
    random_grail: RandomGrail
    random_scanner: RandomScanner
    random_codices: RandomCodex
    random_fdc: RandomFDC
    random_ring: RandomRing
    random_shell_horn: RandomShellHorn
    random_maps_software: RandomMapsSoftware
    mantra_placement: MantraPlacement
    shop_placement: ShopPlacement

    # Item Pool Adjustments
    random_research: RandomResearch
    remove_research: RemoveResearch
    remove_maps: RemoveMaps
    required_skulls: RequiredSkulls
    remove_excess_skulls: RemoveSkulls
    random_dissonance: RandomDissonance

    # Sanities
    potsanity: Potsanity

    # Logic & Difficulty
    required_guardians: GuardianKills
    guardian_specific_ankhs: GuardianSpecificAnkhJewels
    logic_difficulty: LogicDifficulty
    echidna_difficulty: EchidnaDifficulty
    costume_clip: CostumeClip
    require_fdc: RequireFDC
    dlc_item_logic: DLCItemLogic
    life_sigil_to_awaken_hom: LifeSigilToAwakenHoM
    remove_icefire_treetop_statue: RemoveIcefireTreetopStatue
    random_cursed_chests: RandomCursedChests
    cursed_chests: CursedChestCount

    # Entrance Randomizer
    horizontal_entrances: HorizontalEntrances
    vertical_entrances: VerticalEntrances
    gate_entrances: GateEntrances
    unique_transitions: UniqueTransitions
    full_random_entrances: FullRandomEntrances
    prevent_area_loops: PreventAreaLoops
    soul_gate_entrances: SoulGateEntrances
    include_nine_soul_gates: IncludeNineSoulGates
    random_soul_gate_value: RandomSoulGateValue

    # Quality of Life
    auto_scan: AutoScan
    auto_skulls: AutoSkulls
    starting_money: StartingMoney
    starting_weights: StartingWeights
    item_chest_color: ItemChestColor
    filler_chest_color: FillerChestColor
    ap_chest_color: APChestColor

    # Other
    write_seed_file: WriteSeedFile
    death_link: DeathLink