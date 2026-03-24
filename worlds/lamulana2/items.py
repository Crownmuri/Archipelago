from __future__ import annotations

import json
import importlib.resources as resources
from dataclasses import dataclass
from typing import Dict, List, Set, Optional

from BaseClasses import Item, ItemClassification

from .ids import USELESS_ITEM_IDS, ItemID, BASE_ITEM_ID, SHOP_ITEM_IDS, FILLER_ITEM_IDS,TRAP_ITEM_IDS, GUARDIAN_ANKHS_ITEMS, LOGIC_FLAG_MAP, LOGIC_FLAG_ITEM_IDS, AP_ITEM_PLACEHOLDER 
from .locations import LocationType

# ============================================================
# JSON-backed LM2 item definition
# ============================================================

@dataclass(frozen=True)
class ItemDef:
    name: str
    game_id: int          # game ItemID
    ap_id: int           # Archipelago ID
    required: bool
    count: int = 1
    shop: bool = False


# ============================================================
# LM2Item subclass — allows storing lm2_game_id for seed writing
# Needed because BaseClasses.Item uses __slots__
# ============================================================

class LM2Item(Item):
    game = "La-Mulana 2"
    __slots__ = ("lm2_game_id",)


# ============================================================
# Load Items.json
# ============================================================

ITEM_DEFS: list[ItemDef] = []
ITEM_DEFS_BY_NAME: dict[str, ItemDef] = {}
ITEM_DEFS_BY_AP_ID: dict[int, ItemDef] = {}

def _load_items_json() -> None:
    """Load items from Items.json."""
    with resources.files(__package__ + ".data").joinpath("Items.json").open(
        "r", encoding="utf-8"
    ) as f:
        raw = json.load(f)

    for entry in raw:
        game_id = entry["id"]
        ap_id = BASE_ITEM_ID + game_id

        item_def = ItemDef(
            name=entry["name"],
            game_id=game_id,
            ap_id=ap_id,
            required=entry.get("isRequired", False),
            count=entry.get("count", 1),
            shop=entry.get("shop", False),
        )

        ITEM_DEFS.append(item_def)
        ITEM_DEFS_BY_NAME[item_def.name] = item_def
        ITEM_DEFS_BY_AP_ID[item_def.ap_id] = item_def

# Load items at module import time
_load_items_json()

# ============================================================
# Handle Progressive / Same Name Items as Single ID on AP end
# ============================================================

PROGRESSIVE_BASE = {
    ItemID.Whip1: ("Progressive Whip", ItemID.Whip1),
    ItemID.Whip2: ("Progressive Whip", ItemID.Whip1),
    ItemID.Whip3: ("Progressive Whip", ItemID.Whip1),
    ItemID.Shield1: ("Progressive Shield", ItemID.Shield1),
    ItemID.Shield2: ("Progressive Shield", ItemID.Shield1),
    ItemID.Shield3: ("Progressive Shield", ItemID.Shield1),
}

# Not grouped yet, using unique labels from ids.py for now
CRYSTALSKULL_BASE = {
    ItemID.CrystalSkull1: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull2: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull3: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull4: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull5: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull6: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull7: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull8: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull9: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull10: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull11: ("Crystal Skull", ItemID.CrystalSkull1),
    ItemID.CrystalSkull12: ("Crystal Skull", ItemID.CrystalSkull1),
}

ANKHJEWEL_BASE = {
    ItemID.AnkhJewel1: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel2: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel3: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel4: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel5: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel6: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel7: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel8: ("Ankh Jewel", ItemID.AnkhJewel1),
    ItemID.AnkhJewel9: ("Ankh Jewel", ItemID.AnkhJewel1),
}

SACREDORB_BASE = {
    ItemID.SacredOrb0: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb1: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb2: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb3: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb4: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb5: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb6: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb7: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb8: ("Sacred Orb", ItemID.SacredOrb0),
    ItemID.SacredOrb9: ("Sacred Orb", ItemID.SacredOrb0),
}

RESEARCH_BASE = {
    ItemID.Research1: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research2: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research3: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research4: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research5: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research6: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research7: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research8: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research9: ("Kosugi Research Papers", ItemID.Research1),
    ItemID.Research10: ("Kosugi Research Papers", ItemID.Research1),
}

# ============================================================
# Append Logic Checks to ITEM_DEFS
# ============================================================

def _register_logic_items():
    """
    Create ItemDef entries for logic-only items (boss kills, puzzles, fairies, etc.)
    This keeps a single authoritative item ontology for all logic & pool code paths.
    """
    # LOGIC_FLAG_MAP maps human name -> ItemID (enum) in ids.py
    for name, itemid in LOGIC_FLAG_MAP.items():
        game_id = int(itemid)  # ItemID enum -> raw int
        ap_id = BASE_ITEM_ID + game_id

        # Avoid duplicates if already present
        if ap_id in ITEM_DEFS_BY_AP_ID:
            continue

        item_def = ItemDef(
            name=name,
            game_id=game_id,
            ap_id=ap_id,
            required=True,   # logic items must be treated as progression
            count=1,
            shop=False
        )

        ITEM_DEFS.append(item_def)
        ITEM_DEFS_BY_NAME[item_def.name] = item_def
        ITEM_DEFS_BY_AP_ID[item_def.ap_id] = item_def

# call registration after Items.json is loaded
_register_logic_items()

# ============================================================
# Item creation helpers
# ============================================================

def create_item(world, name: str, game_id: Optional[int] = None) -> Item:
    """Create an Archipelago Item from an item name."""
    # If game_id is provided, use it directly
    if game_id is not None:
        ap_id = BASE_ITEM_ID + game_id
        # Find the item def
        for item_def in ITEM_DEFS:
            if item_def.game_id == game_id:
                classification = _get_classification(item_def)
                return Item(
                    name=item_def.name,
                    classification=classification,
                    code=ap_id,
                    player=world.player,
                )
        # If not found, create with default
        return Item(
            name=name,
            classification=ItemClassification.progression if "Ankh Jewel" in name else ItemClassification.progression_skip_balancing,
            code=ap_id,
            player=world.player,
        )
    
    matching_defs = [d for d in ITEM_DEFS if d.name == name]
    
    if not matching_defs:
        raise KeyError(f"No item def found for name: {name}")
    
    # Use the first definition
    selected_def = matching_defs[0]
    classification = _get_classification(selected_def)
    
    return Item(
        name=selected_def.name,
        classification=classification,
        code=selected_def.ap_id,
        player=world.player,
    )

def _get_classification(item_def: ItemDef) -> ItemClassification:
    """Get classification for an item definition."""

    # 1. Force endgame/collectathon items to skip balancing so they don't choke sphere 0
    skip_balancing_items = {"Crystal Skull"}
    if item_def.name in skip_balancing_items:
        return ItemClassification.progression_skip_balancing

    # 2. Standard classifications
    if item_def.required:
        return ItemClassification.progression
    elif item_def.game_id in USELESS_ITEM_IDS:
        return ItemClassification.filler
    elif item_def.game_id in FILLER_ITEM_IDS:
        return ItemClassification.filler
    elif item_def.game_id in TRAP_ITEM_IDS:
        return ItemClassification.trap
    else:
        return ItemClassification.useful

def create_filler_item(world, name: str, game_item_id: int) -> Item:
    """
    Create a non-logic filler item backed only by a game ItemID.
    Uses the game's ItemID enum value and converts to AP ID.
    """
    ap_id = BASE_ITEM_ID + game_item_id
    
    return Item(
        name=name,
        classification=ItemClassification.filler,
        code=ap_id,
        player=world.player
    )

def create_logic_flag_item(world, item_name: str) -> Item:
    """
    Return an Archipelago Item for the named logic flag.
    Must exist in ITEM_DEFS (registered by _register_logic_items).
    """
    item_def = ITEM_DEFS_BY_NAME.get(item_name)
    if item_def is None:
        raise KeyError(f"Logic item '{item_name}' is not registered in ITEM_DEFS")

    classification = _get_classification(item_def)
    return Item(
        name=item_def.name,
        classification=classification,
        code=None,   # None = event item: AP auto-collects when location is reachable
        player=world.player
    )

def get_game_item_id(item: Item) -> ItemID:
    # Preserve Progressive Item original ID for seed writing
    if hasattr(item, 'lm2_game_id'):
        return item.lm2_game_id

    # Handle logic flag items (code=None)
    if item.code is None:
        raise KeyError(
            f"Logic flag item '{item.name}' has no game ItemID (code=None)"
        )
    
    # Normal LM2 items
    for item_def in ITEM_DEFS:
        if item.code == BASE_ITEM_ID + item_def.game_id:
            return ItemID(item_def.game_id)

    # Filler fallback: AP code format is BASE_ITEM_ID + game_item_id
    if item.code >= BASE_ITEM_ID:
        return ItemID(item.code - BASE_ITEM_ID)

    raise KeyError(
        f"Item with code {item.code} not found in ITEM_DEFS "
        f"(name={item.name}, classification={item.classification})"
    )

# ============================================================
# Starting inventory logic
# ============================================================

def get_starting_item_ids(world) -> List[ItemID]:
    """
    Mirrors original lm2_seed_writer starting item logic.
    Returns ItemIDs ONLY.
    """
    result: List[ItemID] = []

    if world.options.random_grail.value == 0:
        result.append(ItemID.HolyGrail)

    if world.options.random_scanner.value == 0:
        result.append(ItemID.HandScanner)

    if world.options.random_fdc.value == 0:
        result.append(ItemID.FutureDevelopmentCompany)

    if world.options.random_codices.value == 0:
        result.append(ItemID.Codices)

    if world.options.random_ring.value == 0:
        result.append(ItemID.Ring)

    if world.options.random_shell_horn.value == 0:
        result.append(ItemID.ShellHorn)

    if world.options.random_maps_software.value == 0:
        result.append(ItemID.YagooMapReader)
        result.append(ItemID.YagooMapStreet)
        for map_num in range(1, 17):
            result.append(ItemID(ItemID.Map1.value + map_num - 1))

    return result


def apply_starting_inventory(world):
    """Add starting items to the player's precollected items."""
    existing_precollected = {item.name for item in world.multiworld.precollected_items[world.player]}
    
    for item_id in get_starting_item_ids(world):
        ap_id = BASE_ITEM_ID + int(item_id)
        item_def = ITEM_DEFS_BY_AP_ID.get(ap_id)
        
        if not item_def:
            print(f"Warning: Starting item {item_id} (AP ID {ap_id}) not found in Items.json")
            continue
        
        if item_def.name in existing_precollected:
            continue
            
        world.multiworld.push_precollected(create_item(world, item_def.name, game_id=item_def.game_id))


# ============================================================
# Main item pool construction
# ============================================================

def build_item_pool(world) -> List[Item]:
    
    pool: List[Item] = []

    starting_items: Set[ItemID] = set(get_starting_item_ids(world))
    if hasattr(world, "starting_weapon"):
        starting_items.add(world.starting_weapon)

    for item_def in ITEM_DEFS:
        
        game_item_id = ItemID(item_def.game_id)
        
        # Skip starting items
        if game_item_id in starting_items:
            continue

        # Handle dissonance
        if item_def.name == "Dissonance":
            continue

        # Collapse Progressive Whip and Shield to base AP ID
        if game_item_id in PROGRESSIVE_BASE:
            display_name, base_id = PROGRESSIVE_BASE[game_item_id]
            item = LM2Item(
                name=display_name,
                classification=ItemClassification.progression,
                code=BASE_ITEM_ID + base_id.value,
                player=world.player,
            )
            item.lm2_game_id = game_item_id
            pool.append(item)
            continue

        # Handle ProgressiveBeherit based on RandomDissonance setting
        if game_item_id == ItemID.ProgressiveBeherit1:
            count = 7 if world.options.random_dissonance else 1
            for i in range(count):
                actual_id = ItemID(ItemID.ProgressiveBeherit1.value + i)
                item = LM2Item(
                    name="Progressive Beherit",
                    classification=ItemClassification.progression,
                    code=BASE_ITEM_ID + ItemID.ProgressiveBeherit1.value,
                    player=world.player,
                )
                item.lm2_game_id = actual_id
                pool.append(item)
            continue              
        
        # Skip logic flags (placed separately)
        if game_item_id in LOGIC_FLAG_ITEM_IDS:
            continue
        
        # Skip filler (created on demand)
        if game_item_id in FILLER_ITEM_IDS:
            continue

        # Skip traps (created on demand)
        if game_item_id in TRAP_ITEM_IDS:
            continue
        
        # Handle shop items
        if game_item_id in SHOP_ITEM_IDS:
            continue

        # Maps - skip if remove_maps is true
        if world.options.remove_maps and item_def.name.startswith("Map"):
            continue

        # Handle mantras
        if item_def.name in ["Heaven", "Earth", "Sun", "Moon", "Fire", "Sea", "Wind", "Mother", "Child", "Night"]:
            if world.options.mantra_placement.value == 0:  # original
                continue
        
        # Handle research
        if item_def.name in "Research":
            if not world.options.random_research:
                continue
            if world.options.remove_research:
                continue

        # Handle Ankh Jewels — when guardian_specific_ankhs is ON each of the
        # 9 numbered game IDs (AnkhJewel1–9) must appear in the pool with its
        # boss-specific AP name (e.g. "Ankh Jewel (Fafnir)") so that the
        # Has("Ankh Jewel (Fafnir)") logic appended by _fix_ankh_logic can
        # actually be satisfied by the fill algorithm.
        #
        # Items.json stores all 9 as plain "Ankh Jewel", so we must override
        # the name here rather than rely on item_def.name.
        if item_def.name == "Ankh Jewel" and getattr(world.options, "guardian_specific_ankhs", False):
            specific_name = GUARDIAN_ANKHS_ITEMS.get(game_item_id)
            if specific_name:
                for _ in range(item_def.count):
                    item = LM2Item(
                        name=specific_name,
                        classification=ItemClassification.progression,
                        code=BASE_ITEM_ID + game_item_id.value,
                        player=world.player,
                    )
                    item.lm2_game_id = game_item_id
                    pool.append(item)
                continue
            # Unmapped ankh jewel (shouldn't happen) — fall through to generic

        # Add to pool
        for _ in range(item_def.count):
            pool.append(create_item(world, item_def.name, game_id=item_def.game_id))
    
    return pool


# ============================================================
# Shop item pool
# ============================================================

def build_shop_item_ids(world) -> List[ItemID]:
    """
    Returns ItemIDs eligible for shop placement.
    Placement logic lives in shops.py.
    """
    if world.options.shop_placement.value == 0:  # Original
        return []

    result: List[ItemID] = []

    for item_def in ITEM_DEFS:
        if not item_def.shop:
            continue

        if item_def.name == "Hand Scanner" and world.options.random_scanner.value == 0:
            continue
        if item_def.name == "Codices" and world.options.random_codices.value == 0:
            continue
        if item_def.name == "Ring" and world.options.random_ring.value == 0:
            continue

        result.append(ItemID(item_def.game_id))

    return result

# ============================================================
# AP-Facing Filler Definitions (IDs 300-309)
# ============================================================

AP_FILLER: list[tuple[str, ItemID]] = [
    ("1 Coin",     ItemID.Coin1),
    ("10 Coins",   ItemID.Coin10),
    ("30 Coins",   ItemID.Coin30),
    ("50 Coins",   ItemID.Coin50),
    ("80 Coins",   ItemID.Coin80),
    ("100 Coins",  ItemID.Coin100),
    ("1 Weight",   ItemID.Weight1),
    ("5 Weights",  ItemID.Weight5),
    ("10 Weights", ItemID.Weight10),
    ("20 Weights", ItemID.Weight20),
]

AP_FILLER_NAMES: frozenset[str] = frozenset(name for name, _ in AP_FILLER)

# The intended distribution per 40 items (Total = 40)
FILLER_DISTRIBUTION = [
    ("1 Coin", 3), ("10 Coins", 6), ("30 Coins", 8),
    ("50 Coins", 3), ("80 Coins", 2), ("100 Coins", 1),
    ("1 Weight", 4), ("5 Weights", 10), ("10 Weights", 2), ("20 Weights", 1)
]

# ============================================================
# Internal Mapping Logic (Sub-Pools)
# ============================================================

# This maps (LocationType, AP_ItemID) -> List[Internal_ItemID]
# e.g. (LocationType.Chest, ItemID.Coin100) -> [ItemID.ChestWeight25]
INTERNAL_POOL_BY_REWARD: dict[tuple[LocationType, ItemID], list[ItemID]] = {}

def _build_internal_pools():
    """
    Categorizes every unique internal game ID by its reward value 
    based on your distribution logic.
    """
    # 1. Chests (40 items) & FakeItems (40 items)
    # Both use the standard 40-item FILLER_DISTRIBUTION
    for category, base_id in [(LocationType.Chest, ItemID.ChestWeight01), 
                             (LocationType.FreeStanding, ItemID.FakeItem01)]:
        idx = 0
        for name, count in FILLER_DISTRIBUTION:
            ap_id = next(iid for n, iid in AP_FILLER if n == name)
            for _ in range(count):
                key = (category, ap_id)
                INTERNAL_POOL_BY_REWARD.setdefault(key, []).append(ItemID(base_id.value + idx))
                idx += 1

    # 2. NPC Money / Dialogue (10 items)
    # Distribution: One of each reward (since there are 10 rewards and 10 IDs)
    for i, (name, _) in enumerate(FILLER_DISTRIBUTION):
        ap_id = next(iid for n, iid in AP_FILLER if n == name)
        key = (LocationType.Dialogue, ap_id)
        INTERNAL_POOL_BY_REWARD.setdefault(key, []).append(ItemID(ItemID.NPCMoney01.value + i))

    # 3. Fake Scans / Murals (15 items)
    # Using your specific manual distribution for Murals
    fs_names = [
        "1 Coin", "10 Coins", "10 Coins", "30 Coins", "30 Coins", 
        "30 Coins", "50 Coins", "80 Coins", "100 Coins",
        "1 Weight", "5 Weights", "5 Weights", "10 Weights", "10 Weights", "20 Weights"
    ]
    for i, name in enumerate(fs_names):
        ap_id = next(iid for n, iid in AP_FILLER if n == name)
        key = (LocationType.Mural, ap_id)
        INTERNAL_POOL_BY_REWARD.setdefault(key, []).append(ItemID(ItemID.FakeScan01.value + i))

# Initialize the pools immediately
_build_internal_pools()

# ============================================================
# Generation Function
# ============================================================

def build_pre_filler(world) -> Item:
    """
    Creates a generic AP filler item (300-309) for placement.
    Translation to unique internal IDs happens later in randomizer.py.
    """
    # Create a weighted list of names based on FILLER_DISTRIBUTION
    weighted_names = [name for name, weight in FILLER_DISTRIBUTION for _ in range(weight)]
    name = world.random.choice(weighted_names)
    
    # Get the generic AP ItemID (300-309)
    item_id = next(iid for n, iid in AP_FILLER if n == name)

    return Item(
        name=name,
        classification=ItemClassification.filler,
        code=BASE_ITEM_ID + int(item_id),
        player=world.player,
    )