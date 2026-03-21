from typing import Dict
from dataclasses import dataclass
from Options import Choice, Toggle, Range, ItemsAccessibility, PerGameCommonOptions, DeathLink

# --- Choice Definitions ---

class AutoScan(Toggle):
    """Automatically scan tablets when read."""
    display_name = "Auto Scan Tablets"
    default = True

class AutoSkulls(Toggle):
    """Auto-Place Crystal Skulls in Nibiru."""
    display_name = "Auto Place Skulls"
    default = True

class ItemPlacementOption(Choice):
    option_starting = 0
    option_shuffled = 1
    # option_available_at_start = 2
    default = 0

class MantraPlacement(Choice):
    """random: Mantras can be anywhere.
    only_murals: Mantras are restricted to mural locations.
    original: Mantras stay in their vanilla mural locations."""
    display_name = "Mantra Placement"
    option_original = 0
    option_only_murals = 1
    option_shuffled = 2
    default = 0

class ShopPlacement(Choice):
    """random: All shop items are shuffled.
    at_least_one: Each shop is guaranteed at least one non-ammo/weight item.
    original: Shops keep vanilla items."""
    display_name = "Shop Placement"
    option_original = 0
    option_at_least_one = 1
    option_shuffled = 2
    default = 0

class EchidnaDifficulty(Choice):
    display_name = "Echidna Difficulty"
    option_child = 0
    option_teenager = 1
    option_young_adult = 2
    option_adult = 3
    option_normal = 4
    default = 4

class ItemChestColor(Choice):
    display_name = "Item Chest Color"
    option_blue = 0
    option_turquoise = 1
    option_red = 2
    option_pink = 3
    option_yellow = 4
    default = 0

class FillerChestColor(Choice):
    display_name = "Filler Chest Color"
    option_blue = 0
    option_turquoise = 1
    option_red = 2
    option_pink = 3
    option_yellow = 4
    default = 0

class APChestColor(Choice):
    display_name = "AP Chest Color"
    option_blue = 0
    option_turquoise = 1
    option_red = 2
    option_pink = 3
    option_yellow = 4
    default = 0

# --- Logic Changes ---
class LogicDifficulty(Choice):
    display_name = "Logic Difficulty"
    option_standard = 0
    option_hard = 1
    default = 0

class GuardianSpecificAnkhJewels(Toggle):
    """Makes Ankhs only usable at their designated bosses."""
    display_name = "Guardian Specific Ankh Jewels"
    default = True

# --- Remove Checks ---
class RemoveResearch(Toggle):
    """Remove Research Notes from the item pool."""
    display_name = "Remove Research Notes"
    default = False

class RemoveMaps(Toggle):
    """Remove Map Software items from the item pool."""
    display_name = "Remove Maps"
    default = False

class RemoveSkulls(Toggle):
    """Remove Excess Crystal Skulls from the item pool."""
    display_name = "Remove Skulls"
    default = False

# --- Range Definitions ---

class GuardianKills(Range):
    """Number of Guardians required to be defeated."""
    display_name = "Required Guardian Kills"
    range_start = 0
    range_end = 8
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
    display_name = "Starting Money"
    range_start = 0
    range_end = 999
    default = 25

class StartingWeights(Range):
    display_name = "Starting Weights"
    range_start = 0
    range_end = 100
    default = 5

# --- Main Options Class ---

@dataclass
class LM2Options(PerGameCommonOptions):

    accessibility: ItemsAccessibility

    # Item Shuffle
    random_grail: ItemPlacementOption
    random_scanner: ItemPlacementOption
    random_codices: ItemPlacementOption
    random_fdc: ItemPlacementOption
    random_ring: ItemPlacementOption
    random_shell_horn: ItemPlacementOption
    random_maps_software: ItemPlacementOption
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
    costume_clip: Toggle
    random_research: Toggle
    random_dissonance: Toggle
    require_fdc: Toggle
    dlc_item_logic: Toggle
    life_sigil_to_awaken_hom: Toggle
    remove_icefire_treetop_statue: Toggle
    
    # Requirements
    required_guardians: GuardianKills
    required_skulls: RequiredSkulls
    random_cursed_chests: Toggle
    cursed_chests: CursedChestCount

    # Entrance Randomizer
    horizontal_entrances: Toggle
    vertical_entrances: Toggle
    gate_entrances: Toggle
    unique_transitions: Toggle
    soul_gate_entrances: Toggle
    include_nine_soul_gates: Toggle
    random_soul_gate_value: Toggle
    full_random_entrances: Toggle 
    prevent_area_loops: Toggle

    # Starting Area Pool
    start_village_of_departure: Toggle
    start_roots_of_yggdrasil: Toggle
    start_annwfn: Toggle 
    start_immortal_battlefield: Toggle
    start_icefire_treetop: Toggle
    start_divine_fortress: Toggle
    start_shrine_of_the_frost_giants: Toggle
    start_takamagahara_shrine: Toggle 
    start_valhalla: Toggle
    start_dark_star_lords_mausoleum: Toggle
    start_ancient_chaos: Toggle
    start_hall_of_malice: Toggle

    # Starting Weapon Pool
    start_leather_whip: Toggle
    start_knife: Toggle
    start_rapier: Toggle
    start_axe: Toggle
    start_katana: Toggle 
    start_shuriken: Toggle 
    start_rolling_shuriken: Toggle
    start_earth_spear: Toggle
    start_flare: Toggle
    start_caltrops: Toggle
    start_chakram: Toggle 
    start_bomb: Toggle
    start_pistol: Toggle
    start_claydoll_suit: Toggle

    # QoL
    auto_scan: AutoScan
    auto_skulls: AutoSkulls 
    starting_money: StartingMoney 
    starting_weights: StartingWeights
    item_chest_color: ItemChestColor
    filler_chest_color: FillerChestColor
    ap_chest_color: APChestColor

    death_link: DeathLink