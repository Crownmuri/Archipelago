from __future__ import annotations

import json
import importlib.resources as resources
from dataclasses import dataclass
from typing import Dict, List, Set, Optional

from BaseClasses import Item, ItemClassification

from . import _log
from .ids import USELESS_ITEM_IDS, ItemID, BASE_ITEM_ID, SHOP_ITEM_IDS, FILLER_ITEM_IDS,TRAP_ITEM_IDS, GUARDIAN_ANKHS_ITEMS, GLOSSARY_ITEM_IDS, LOGIC_FLAG_MAP, LOGIC_FLAG_ITEM_IDS, AP_ITEM_PLACEHOLDER, ITEM_MAP, DLC_ITEM_IDS, DLC_GLOSSARY_IDS, COSTUME_ITEM_IDS, POT_POOL_BY_LOC, POT_REWARD_BY_LOC, GLOSSARY_POOLS_BY_ID, potsanity_pools_enabled, glossanity_pools_enabled
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
    
    # Area/boss-labeled names ("Sacred Orb (VoD)", "Crystal Skull (RoY)",
    # "Map (Annwfn)", "Ankh Jewel (Fafnir)", ...) are the canonical datapackage
    # names (item_name_to_id is built from ITEM_MAP), each tied to a distinct
    # game id. The POOL builder, however, emits these items under their generic
    # ItemDef name ("Sacred Orb", "Crystal Skull", "Map") — only guardian ankhs
    # are renamed, and only when guardian_specific_ankhs is on. The logic
    # follows the pool: OrbCount/SkullCount/AnkhCount compile to
    # state.count("Sacred Orb"/"Crystal Skull"/"Ankh Jewel"), while guardian
    # access compiles to Has("Ankh Jewel (Boss)").
    #
    # Anything recreating an item from the network by its datapackage name
    # (Universal Tracker rebuilding received items) gets the labeled name, so
    # we must map it back to the SAME name the pool used, or those items won't
    # match the compiled rules and progression silently vanishes from logic.
    if name not in ITEM_DEFS_BY_NAME:
        mapped_id = ITEM_MAP.get(name)
        if mapped_id is not None:
            base_def = next(
                (d for d in ITEM_DEFS if d.game_id == mapped_id.value), None)
            if (mapped_id in GUARDIAN_ANKHS_ITEMS
                    and getattr(world.options, "guardian_specific_ankhs", False)):
                pool_name = name                      # keep "Ankh Jewel (Boss)"
            elif base_def is not None:
                pool_name = base_def.name             # generic "Sacred Orb" etc.
            else:
                pool_name = name
            classification = (
                _get_classification(base_def) if base_def is not None
                else ItemClassification.progression
            )
            item = LM2Item(
                name=pool_name,
                classification=classification,
                code=BASE_ITEM_ID + mapped_id.value,
                player=world.player,
            )
            item.lm2_game_id = mapped_id
            return item

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
    
    # Normal LM2 items (glossary ROMs are now real ItemID members — no special-casing)
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
    # Dedupe by AP code (unique per game_id), not name — multiple distinct
    # items can share a display name (e.g. all 16 area maps are "Map").
    existing_precollected = {item.code for item in world.multiworld.precollected_items[world.player]}

    for item_id in get_starting_item_ids(world):
        ap_id = BASE_ITEM_ID + int(item_id)
        item_def = ITEM_DEFS_BY_AP_ID.get(ap_id)

        if not item_def:
            _log(f"Warning: Starting item {item_id} (AP ID {ap_id}) not found in Items.json")
            continue

        if ap_id in existing_precollected:
            continue

        world.multiworld.push_precollected(create_item(world, item_def.name, game_id=item_def.game_id))
        existing_precollected.add(ap_id)


# ============================================================
# Main item pool construction
# ============================================================

def build_item_pool(world) -> List[Item]:
    
    pool: List[Item] = []

    starting_items: Set[ItemID] = set(get_starting_item_ids(world))
    if hasattr(world, "starting_weapon"):
        starting_items.add(world.starting_weapon)

    for item_def in ITEM_DEFS:

        # glossary ROMs: pool the placed ones as filler when that glossary
        # category's glossanity toggle is on. DLC glossaries (fish + Gyonin)
        # additionally require oannesanity.
        if item_def.game_id in GLOSSARY_ITEM_IDS:
            is_dlc_gloss = item_def.game_id in DLC_GLOSSARY_IDS
            cat = GLOSSARY_POOLS_BY_ID.get(int(item_def.game_id))
            cat_on = cat is not None and getattr(world.options, f"glossanity_{cat}")
            if (cat_on and (not is_dlc_gloss or world.options.oannesanity)):
                pool.append(LM2Item(name=item_def.name,
                                    classification=ItemClassification.filler,
                                    code=item_def.ap_id, player=world.player))
            continue

        game_item_id = ItemID(item_def.game_id)

        # Skip DLC items unless the player opts in.
        if game_item_id in DLC_ITEM_IDS and not world.options.oannesanity:
            continue

        # Skip costume unlocks unless costumesanity is on. (Fish Suit is also in
        # DLC_ITEM_IDS above, so it additionally requires oannesanity.)
        if game_item_id in COSTUME_ITEM_IDS and not world.options.costumesanity:
            continue

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

        # Crystal Skulls - skip excess skulls beyond required_skulls when enabled
        if item_def.name == "Crystal Skull" and world.options.remove_excess_skulls:
            required = world.options.required_skulls.value
            skull_index = game_item_id.value - ItemID.CrystalSkull1.value
            if skull_index >= required:
                continue

        # Handle mantras
        if item_def.name in ["Heaven", "Earth", "Sun", "Moon", "Fire", "Sea", "Wind", "Mother", "Child", "Night"]:
            if world.options.mantra_placement.value == 0:  # original
                continue
        
        # Handle research
        if "Research" in item_def.name:
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
            item = create_item(world, item_def.name, game_id=item_def.game_id)
            # Glossary gating: Has() only sees progression items, so the items
            # that gate glossary checks must be progression when the relevant
            # glossanity is on (otherwise those checks are never reachable).
            # Ruins Encyclopedia gates every glossary check (any glossanity cat);
            # Perfume gates the single Blue Skeleton enemy-glossary check.
            if item_def.name == "Ruins Encyclopedia" and glossanity_pools_enabled(world.options):
                item.classification = ItemClassification.progression
            elif item_def.name == "Perfume" and world.options.glossanity_enemy:
                item.classification = ItemClassification.progression
            # Rebirth Sigil gates the only path into the Tower of Oannes
            # (Spring in the Sky ladder up) and Fish-Gear mk-2 turboR. It is a
            # DLC item, so it is only pooled when oannesanity is on, and it must
            # be progression there or the entire DLC area is unreachable.
            elif item_def.name == "Rebirth Sigil" and world.options.oannesanity:
                item.classification = ItemClassification.progression
            pool.append(item)

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
# AP-Facing Filler Definitions (IDs 901-917, see ItemID "AP Trash")
# ============================================================

AP_FILLER: list[tuple[str, ItemID]] = [
    ("1 Coin",            ItemID.Coin1),
    ("10 Coins",          ItemID.Coin10),
    ("30 Coins",          ItemID.Coin30),
    ("50 Coins",          ItemID.Coin50),
    ("80 Coins",          ItemID.Coin80),
    ("100 Coins",         ItemID.Coin100),
    ("1 Weight",          ItemID.Weight1),
    ("5 Weights",         ItemID.Weight5),
    ("10 Weights",        ItemID.Weight10),
    ("20 Weights",        ItemID.Weight20),
    ("10 Shuriken",       ItemID.ShurikenBundle),
    ("10 Rolling Shuriken", ItemID.RollingShurikenBundle),
    ("10 Earth Spears",   ItemID.EarthSpearBundle),
    ("10 Flares",         ItemID.FlareBundle),
    ("10 Caltrops",       ItemID.CaltropsBundle),
    ("1 Chakram",         ItemID.ChakramBundle),
    ("3 Bombs",           ItemID.BombBundle),
]

AP_FILLER_NAMES: frozenset[str] = frozenset(name for name, _ in AP_FILLER)

FILLER_DISTRIBUTION = [
    ("1 Coin", 15), ("10 Coins", 20), ("30 Coins", 15),
    ("50 Coins", 6), ("80 Coins", 3), ("100 Coins", 1),
    ("1 Weight", 24), ("5 Weights", 12), ("10 Weights", 3), ("20 Weights", 1)
]

# Pot filler distribution
POT_FILLER_DISTRIBUTION = [
    ("1 Weight", 39),            # 38 + 1
    ("10 Coins", 74),           # 67 + 7
    ("30 Coins", 31),           # 30 + 1
    ("50 Coins", 8),            # 6 + 2
    ("80 Coins", 7),            # 6 + 1
    ("100 Coins", 9),           # 8 + 1
    ("10 Shuriken", 23),        # 23 + 0
    ("10 Rolling Shuriken", 16),# 15 + 1
    ("10 Earth Spears", 23),    # 20 + 3
    ("10 Flares", 24),          # 22 + 2
    ("10 Caltrops", 17),        # 16 + 1
    ("1 Chakram", 10),          # 8 + 2
    ("3 Bombs", 26),            # 18 + 8
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
    # 1. Chests (100 items) & FakeItems (100 items)
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
    for i, (name, _) in enumerate(FILLER_DISTRIBUTION):
        ap_id = next(iid for n, iid in AP_FILLER if n == name)
        key = (LocationType.Dialogue, ap_id)
        INTERNAL_POOL_BY_REWARD.setdefault(key, []).append(ItemID(ItemID.NPCMoney01.value + i))

    # 3. Fake Scans / Murals (15 items)
    fs_names = [
        "1 Coin", "10 Coins", "10 Coins", "30 Coins", "30 Coins",
        "30 Coins", "50 Coins", "80 Coins", "100 Coins",
        "1 Weight", "5 Weights", "5 Weights", "10 Weights", "10 Weights", "20 Weights"
    ]
    for i, name in enumerate(fs_names):
        ap_id = next(iid for n, iid in AP_FILLER if n == name)
        key = (LocationType.Mural, ap_id)
        INTERNAL_POOL_BY_REWARD.setdefault(key, []).append(ItemID(ItemID.FakeScan01.value + i))

    # 4. Pot Filler (one internal ID per pot)
    idx = 0
    for name, count in POT_FILLER_DISTRIBUTION:
        ap_id = next(iid for n, iid in AP_FILLER if n == name)
        for _ in range(count):
            key = (LocationType.Pot, ap_id)
            INTERNAL_POOL_BY_REWARD.setdefault(key, []).append(ItemID(ItemID.PotFiller01.value + idx))
            idx += 1

# Initialize the pools immediately
_build_internal_pools()

# ============================================================
# Reverse Lookup: Internal ID -> Reward Name & AP Filler ID
# ============================================================
# Derived directly from INTERNAL_POOL_BY_REWARD so there is a single
# source of truth for the distribution. Each internal ID appears under
# exactly one (category, ap_id) key, and the reward name is uniquely
# recoverable from the AP filler ID. Used by _get_unique_filler_id to
# sync the AP item name after a random pool pick.

_AP_ID_TO_NAME: dict[ItemID, str] = {iid: name for name, iid in AP_FILLER}

INTERNAL_ID_TO_REWARD: dict[ItemID, tuple[str, ItemID]] = {
    internal_id: (_AP_ID_TO_NAME[ap_id], ap_id)
    for (_category, ap_id), internal_ids in INTERNAL_POOL_BY_REWARD.items()
    for internal_id in internal_ids
}

# ============================================================
# Generation Function
# ============================================================

def build_pot_filler_pool(world) -> list[Item]:
    """
    Creates one pot filler item per INCLUDED pot location (i.e. pots whose
    content pool's potsanity toggle is enabled), each using the pot's own
    reward (Coin10, ShurikenBundle, etc.) so the spoiler shows the correct
    name. Emitting exactly one filler per included pot keeps the item count
    balanced with the included pot locations. The internal PotFiller IDs are
    assigned later by precompute_filler_ids when items land at Pot locations.
    """
    enabled = potsanity_pools_enabled(world.options)
    pool: list[Item] = []
    for loc_id, reward in POT_REWARD_BY_LOC.items():
        if POT_POOL_BY_LOC.get(loc_id) not in enabled:
            continue
        item_id = next(iid for n, iid in AP_FILLER if n == reward)
        pool.append(Item(
            name=reward,
            classification=ItemClassification.filler,
            code=BASE_ITEM_ID + int(item_id),
            player=world.player,
        ))
    return pool


def build_pre_filler(world) -> Item:
    """
    Creates a generic AP filler item (IDs 901-917) for placement.
    Translation to unique internal IDs happens later in randomizer.py.
    """
    # Create a weighted list of names based on FILLER_DISTRIBUTION
    weighted_names = [name for name, weight in FILLER_DISTRIBUTION for _ in range(weight)]
    name = world.random.choice(weighted_names)

    # Get the generic AP ItemID (901-917)
    item_id = next(iid for n, iid in AP_FILLER if n == name)

    return Item(
        name=name,
        classification=ItemClassification.filler,
        code=BASE_ITEM_ID + int(item_id),
        player=world.player,
    )


# ============================================================
# Item name groups (AP hint targets)
# ============================================================
# Group names must not collide with any individual item name.
# Members must match names registered in LaMulana2World.item_name_to_id.

_WEAPON_NAMES: frozenset[str] = frozenset({
    "Progressive Whip", "Knife", "Rapier", "Axe", "Katana", "Pistol",
})

_SUBWEAPON_NAMES: frozenset[str] = frozenset({
    "Shuriken", "Rolling Shuriken", "Earth Spear", "Flare",
    "Caltrops", "Chakram", "Bomb", "Claydoll Suit",
})

_MANTRA_NAMES: frozenset[str] = frozenset({
    "Heaven", "Earth", "Sun", "Moon", "Fire",
    "Sea", "Wind", "Mother", "Child", "Night",
})

_SIGIL_NAMES: frozenset[str] = frozenset({
    "Origin Sigil", "Birth Sigil", "Life Sigil", "Death Sigil",
})

# Names match Items.json exactly 
_SOFTWARE_NAMES: frozenset[str] = frozenset({
    "Xelputter", "Yagoo Map Reader", "Yagoo Map Street",
    "TextTrax 2", "Ruins Encyclopedia", "Mantra", "Guild",
    "Enga Musica", "Beo Eg-Lana", "Alert", "Snapshot",
    "Skull Reader", "Race Scanner", "Death Village",
    "Rose and Camellia", "Space Capstar II",
    "Lonely House Moving", "Mekuri Master", "Bounce Shot",
    "Miracle Witch", "Future Development Company",
    "La-Mulana", "La-Mulana 2",
})


def build_item_name_groups() -> Dict[str, Set[str]]:
    """Build item_name_groups for AP hinting."""
    from .ids import GUARDIAN_ANKHS_ITEMS

    all_names = {d.name for d in ITEM_DEFS}

    return {
        "Weapons": set(_WEAPON_NAMES),
        "Subweapons": set(_SUBWEAPON_NAMES),
        "Maps": {n for n in all_names if n.startswith("Map")},
        "Research": {n for n in all_names if "Research" in n},
        "Ammo": {n for n in all_names if n.endswith(" Ammo")},
        "Crystal Skulls": {"Crystal Skull"},
        "Skulls":{"Crystal Skull"},
        "Ankh Jewels": {"Ankh Jewel"} | set(GUARDIAN_ANKHS_ITEMS.values()),
        "Mantras": set(_MANTRA_NAMES),
        "Sacred Orbs": {"Sacred Orb"},
        "HP":{"Sacred Orb"},
        "Software": set(_SOFTWARE_NAMES),
        "Sigils": set(_SIGIL_NAMES),
        "Seals": set(_SIGIL_NAMES),
    }