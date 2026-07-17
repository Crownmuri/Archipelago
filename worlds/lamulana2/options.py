from typing import Dict
from dataclasses import dataclass
from Options import Choice, Toggle, DefaultOnToggle, Range, ItemsAccessibility, PerGameCommonOptions, DeathLink

# --- Choice Definitions ---

class Goal(Choice):
    """Victory condition for the seed.
    - beat_the_game: Defeat the Ninth Child and escape (default, vanilla goal).
    - beat_the_dlc: Defeat the final boss in the in the Tower of Oannes DLC.
      Requires Oannesanity.
    - glossary_hunt: Collect a set number of AP shuffled Glossary entries. 
      You will start off with the Ruins Encyclopedia which tracks your progress.
      Requires at least one Glossanity category to be enabled.
    If the chosen goal's prerequisites aren't met, falls back to beat_the_game."""
    display_name = "Goal"
    option_beat_the_game = 0
    option_beat_the_dlc = 1
    option_glossary_hunt = 2
    default = 0

class GlossaryHuntCount(Range):
    """Number of Glossary entries required to win when the goal is glossary_hunt.
    The maximum value is automatically lowered to the number of Glossary entries
    shuffled based on the enabled Glossanity options (and Oannesanity, for DLC glossary)"""
    display_name = "Glossary Hunt Count"
    range_start = 1
    range_end = 244
    default = 50

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

class ReplaceResearchWithOrbs(Range):
    """Replace X Kosugi Research Papers with additional Sacred Orbs (max. 10)
    Requires Random Research to be enabled (otherwise research isn't in the pool)
    The remaining research items stay in the pool as normal.
    Remove Research Notes will not remove Sacred Orbs; only remaining research items."""
    display_name = "Research to Sacred Orbs"
    range_start = 0
    range_end = 10
    default = 0

class RemoveResearch(Toggle):
    """Remove Kosugi Research Notes from the item pool.
    Any remaining research item will be converted to filler."""
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
    If false, sealing the Corridor of Blood requires beating Anu and absorbing all dissonance from their original locations.
    (Effectively requires beating at least Vritra, Aten-Ra, Anu, Echidna and Hel based on just this flag)."""
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

# --- Potsanity (partitioned into per-content sub-pools) ------------------------
# Each toggle adds that subset of the 307 item pots as randomized checks.

class PotsanityLowValue(Toggle):
    """Potsanity: add Low Value item pots as checks. (144 pots)
    39 x 1 Weight Pots
    74 x 10 Coins Pots
    31 x 30 Coins Pots
    """
    display_name = "Potsanity - Low Value Pots"

class PotsanityHighValue(Toggle):
    """Potsanity: add High Value item pots as checks. (24 pots)
    8 x 50 Coins Pots
    7 x 80 Coins Pots
    9 x 100 Coins Pots"""
    display_name = "Potsanity - High Value Pots"

class PotsanityShuriken(Toggle):
    """Potsanity: add all Shuriken ammo pots as checks. (23 pots)"""
    display_name = "Potsanity - Shuriken Pots"

class PotsanityRollingShuriken(Toggle):
    """Potsanity: add all Rolling Shuriken ammo pots as checks. (16 pots)"""
    display_name = "Potsanity - Rolling Shuriken Pots"

class PotsanityEarthSpear(Toggle):
    """Potsanity: add all Earth Spear ammo pots as checks. (23 pots)"""
    display_name = "Potsanity - Earth Spear Pots"

class PotsanityFlare(Toggle):
    """Potsanity: add all Flare ammo pots as checks. (24 pots)"""
    display_name = "Potsanity - Flare Pots"

class PotsanityCaltrops(Toggle):
    """Potsanity: add all Caltrops ammo pots as checks. (17 pots)"""
    display_name = "Potsanity - Caltrops Pots"

class PotsanityChakram(Toggle):
    """Potsanity: add all Chakram ammo pots as checks. (10 pots)"""
    display_name = "Potsanity - Chakram Pots"

class PotsanityBomb(Toggle):
    """Potsanity: add all Bomb ammo pots as checks. (26 pots)"""
    display_name = "Potsanity - Bomb Pots"

# --- Glossanity (partitioned by glossary entry type) ---------------------------
# Each toggle adds that subset of the 244 glossary chips as randomized checks.

class GlossanityFreestanding(Toggle):
    """Glossanity: add all Freestanding Glossary entries. (51+5 entries)
    Note: DLC Glossary is only shuffled if Oannesanity is turned on."""
    display_name = "Glossanity - Freestanding"

class GlossanityScannable(Toggle):
    """Glossanity: add all Scannable Glossary entries that require Hand Scanner. (26 entries)"""
    display_name = "Glossanity - Scannable"

class GlossanityNPC(Toggle):
    """Glossanity: add all NPC Glossary entries as checks. (78 entries)"""
    display_name = "Glossanity - NPC"

class GlossanityEnemy(Toggle):
    """Glossanity: add all Enemy Glossary entries as checks. (77+7 entries)
    Note: DLC Glossary is only shuffled if Oannesanity is turned on."""
    display_name = "Glossanity - Enemy"

class Costumesanity(Toggle):
    """Add the costume chests (4+1) and their correlating costumes into the pool.
    At the start of the seed you will not have your costumes available.
    The chests are openable by default and do not require a key.
    This option will impact logic relating to glitches and DLC. 
    Note: DLC Item is only shuffled if Oannesanity is turned on."""
    display_name = "Costumesanity"

class Oannesanity(Toggle):
    """DLC Required. Enabling this may add the following checks based off of other options:
    - 1 Item Chest (Comes with this option)
    - 5 Freestanding Glossary (Glossanity - Freestanding Required)
    - 7 Enemy Glossary (Glossanity - Enemy Required)
    - 1 Costume Chest (Costumesanity Required)
    - 12 Entrance Pairs (Include DLC Entrances Required)
    """
    display_name = "Oannesanity"


class GuardianSpecificAnkhJewels(DefaultOnToggle):
    """Makes Ankhs only usable at their designated bosses."""
    display_name = "Guardian Specific Ankh Jewels"

class LogicDifficulty(Choice):
    """Logic difficulty setting.
    - normal: intuitive logic - certain HP / damage thresholds required for (mini-)bosses.
    - tricky: includes some shenanigans such as precise jumps, janky hitboxes or damage boosting.
    - minimal: in addition to tricky logic, sets minimal combat requirements for (mini-)bosses."""
    display_name = "Logic Difficulty"
    option_normal = 0
    option_tricky = 1
    option_minimal = 2
    default = 0

class GameDifficulty(Choice):
    """In-game difficulty.
    - normal: default game difficulty.
    - hard: difficulty level +3 (normally toggled by scanning a specific tablet twice).
    Note: Logic is unaffected — this is a QoL (?) feature for those wanting to play on Hard Mode."""
    display_name = "Game Difficulty"
    option_normal = 0
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
    """Consider the DLC item in logic.
    When enabled, the DLC item is assumed as collected from the start, unless it is
    randomized by Costumesanity, in which case it must be obtained first.
    When disabled, the DLC item is never considered in logic."""
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
    - DestinyTabletChest (Anzu)
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

class IncludeDLCEntrances(Toggle):
    """Requires DLC. Include DLC entrances in the pool.
    Note: Combat logic to survive in the DLC areas is still minimal."""
    display_name = "Include DLC Entrances"

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
    If Soul Gate Entrances is vanilla (false): only shuffle values, keep vanilla pairing.
    If Soul Gate Entrances is shuffled (true): shuffle values along with the pairing."""
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

class GreedyCharon(DefaultOnToggle):
    """AP coin grants can be sent by another player at any point, 
    which may not be ideal in synced playthroughs. 
    Turning this on will make Charon take all your coins as payment, 
    so you don't get bricked with additional coins while trying to get to Charon."""
    display_name = "Greedy Charon"

class PersistentInventory(Toggle):
    """Keep everything you have locally collected after a death or a save load.
    Normally only AP items get regranted upon loading; this option extends to ALL items.
    In other words, turning this on keeps your inventory fully synced with AP's CollectionState.
    Own world items are silently recovered and checked locations remain checked.
    Note: Puzzle progression flags will not persist."""
    display_name = "Persistent Inventory"

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
    """Writes seed.lm2r (standalone compatible) and a seed.lm2ap
    For those who wish to play solo seeds outside of AP.
    AP generated seeds require both files to play the seed solo offline.
    Standalone generated seeds can also be played (will use the original
    filler and ankh jewel system).
    Seed files need to be placed in La-Mulana 2/LaMulana2Randomizer/Seed"""
    display_name = "Write Seed File."

@dataclass
class LM2Options(PerGameCommonOptions):

    accessibility: ItemsAccessibility

    # Goal
    goal: Goal
    glossary_hunt_count: GlossaryHuntCount

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
    replace_research_with_orbs: ReplaceResearchWithOrbs
    remove_maps: RemoveMaps
    required_skulls: RequiredSkulls
    remove_excess_skulls: RemoveSkulls
    random_dissonance: RandomDissonance

    # Sanities
    costumesanity: Costumesanity
    # Potsanity is partitioned into per-content sub-pools (no single master toggle).
    potsanity_low_value: PotsanityLowValue
    potsanity_high_value: PotsanityHighValue
    potsanity_shuriken: PotsanityShuriken
    potsanity_rolling_shuriken: PotsanityRollingShuriken
    potsanity_earth_spear: PotsanityEarthSpear
    potsanity_flare: PotsanityFlare
    potsanity_caltrops: PotsanityCaltrops
    potsanity_chakram: PotsanityChakram
    potsanity_bomb: PotsanityBomb
    # Glossanity is partitioned by entry type (no single master toggle).
    glossanity_freestanding: GlossanityFreestanding
    glossanity_scannable: GlossanityScannable
    glossanity_npc: GlossanityNPC
    glossanity_enemy: GlossanityEnemy
    oannesanity: Oannesanity

    # Logic & Difficulty
    required_guardians: GuardianKills
    guardian_specific_ankhs: GuardianSpecificAnkhJewels
    logic_difficulty: LogicDifficulty
    game_difficulty: GameDifficulty
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
    include_dlc_entrances: IncludeDLCEntrances
    prevent_area_loops: PreventAreaLoops
    soul_gate_entrances: SoulGateEntrances
    include_nine_soul_gates: IncludeNineSoulGates
    random_soul_gate_value: RandomSoulGateValue

    # Quality of Life
    auto_scan: AutoScan
    auto_skulls: AutoSkulls
    greedy_charon: GreedyCharon
    persistent_inventory: PersistentInventory
    starting_money: StartingMoney
    starting_weights: StartingWeights
    item_chest_color: ItemChestColor
    filler_chest_color: FillerChestColor
    ap_chest_color: APChestColor

    # Other
    write_seed_file: WriteSeedFile
    death_link: DeathLink
