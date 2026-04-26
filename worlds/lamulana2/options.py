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

# --- Starting Area Pool ---
class StartVillageOfDeparture(Toggle):
    """Include Village of Departure in the starting area pool."""
    display_name = "Start: Village of Departure"

class StartRootsOfYggdrasil(Toggle):
    """Include Roots of Yggdrasil in the starting area pool."""
    display_name = "Start: Roots of Yggdrasil"

class StartAnnwfn(Toggle):
    """Include Annwfn in the starting area pool."""
    display_name = "Start: Annwfn"

class StartImmortalBattlefield(Toggle):
    """Include Immortal Battlefield in the starting area pool."""
    display_name = "Start: Immortal Battlefield"

class StartIcefireTreetop(Toggle):
    """Include Icefire Treetop in the starting area pool. Requires vertical_entrances."""
    display_name = "Start: Icefire Treetop"

class StartDivineFortress(Toggle):
    """Include Divine Fortress in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Divine Fortress"

class StartShrineOfTheFrostGiants(Toggle):
    """Include Shrine of the Frost Giants in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Shrine of the Frost Giants"

class StartTakamagaharaShrine(Toggle):
    """Include Takamagahara Shrine in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Takamagahara Shrine"

class StartValhalla(Toggle):
    """Include Valhalla in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Valhalla"

class StartDarkStarLordsMausoleum(Toggle):
    """Include Dark Star Lord's Mausoleum in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Dark Star Lord's Mausoleum"

class StartAncientChaos(Toggle):
    """Include Ancient Chaos in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Ancient Chaos"

class StartHallOfMalice(Toggle):
    """Include Hall of Malice in the starting area pool. Requires gate_entrances."""
    display_name = "Start: Hall of Malice"

# --- Starting Weapon Pool ---
class StartLeatherWhip(Toggle):
    """Include Leather Whip in the starting weapon pool."""
    display_name = "Start: Leather Whip"

class StartKnife(Toggle):
    """Include Knife in the starting weapon pool."""
    display_name = "Start: Knife"

class StartRapier(Toggle):
    """Include Rapier in the starting weapon pool."""
    display_name = "Start: Rapier"

class StartAxe(Toggle):
    """Include Axe in the starting weapon pool."""
    display_name = "Start: Axe"

class StartKatana(Toggle):
    """Include Katana in the starting weapon pool."""
    display_name = "Start: Katana"

class StartShuriken(Toggle):
    """Include Shuriken in the starting weapon pool."""
    display_name = "Start: Shuriken"

class StartRollingShuriken(Toggle):
    """Include Rolling Shuriken in the starting weapon pool."""
    display_name = "Start: Rolling Shuriken"

class StartEarthSpear(Toggle):
    """Include Earth Spear in the starting weapon pool."""
    display_name = "Start: Earth Spear"

class StartFlare(Toggle):
    """Include Flare in the starting weapon pool."""
    display_name = "Start: Flare"

class StartCaltrops(Toggle):
    """Include Caltrops in the starting weapon pool."""
    display_name = "Start: Caltrops"

class StartChakram(Toggle):
    """Include Chakram in the starting weapon pool."""
    display_name = "Start: Chakram"

class StartBomb(Toggle):
    """Include Bomb in the starting weapon pool."""
    display_name = "Start: Bomb"

class StartPistol(Toggle):
    """Include Pistol in the starting weapon pool."""
    display_name = "Start: Pistol"

class StartClaydollSuit(Toggle):
    """Include Claydoll Suit in the starting weapon pool."""
    display_name = "Start: Claydoll Suit"

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
    range_start = 0
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

    # Starting Area Pool
    start_village_of_departure: StartVillageOfDeparture
    start_roots_of_yggdrasil: StartRootsOfYggdrasil
    start_annwfn: StartAnnwfn
    start_immortal_battlefield: StartImmortalBattlefield
    start_icefire_treetop: StartIcefireTreetop
    start_divine_fortress: StartDivineFortress
    start_shrine_of_the_frost_giants: StartShrineOfTheFrostGiants
    start_takamagahara_shrine: StartTakamagaharaShrine
    start_valhalla: StartValhalla
    start_dark_star_lords_mausoleum: StartDarkStarLordsMausoleum
    start_ancient_chaos: StartAncientChaos
    start_hall_of_malice: StartHallOfMalice

    # Starting Weapon Pool
    start_leather_whip: StartLeatherWhip
    start_knife: StartKnife
    start_rapier: StartRapier
    start_axe: StartAxe
    start_katana: StartKatana
    start_shuriken: StartShuriken
    start_rolling_shuriken: StartRollingShuriken
    start_earth_spear: StartEarthSpear
    start_flare: StartFlare
    start_caltrops: StartCaltrops
    start_chakram: StartChakram
    start_bomb: StartBomb
    start_pistol: StartPistol
    start_claydoll_suit: StartClaydollSuit

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
