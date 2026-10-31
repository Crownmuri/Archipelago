"""Every way of creating an item must agree with the item pool.

The pool is the reference: whatever build_item_pool emits for a game id is the
item's one true shape (name, AP code, classification, game id). The other
creation paths -- create_item by name (Universal Tracker, plando) and by game id
(shops, mantras, starting inventory) -- must produce that same shape, or
name/code matching silently fails (duplicate orbs from plando, UT items that
don't satisfy logic, the server naming an orb by its variant label).
"""
import unittest

from BaseClasses import ItemClassification
from test.general import setup_solo_multiworld
from worlds.AutoWorld import call_all

from .. import LaMulana2World
from ..ids import BASE_ITEM_ID, GLOSSARY_ITEM_IDS, LOGIC_FLAG_MAP
from ..items import create_item, get_game_item_id

# Option sets that change how pool items are named or collapsed.
OPTION_SETS = (
    {},
    {"guardian_specific_ankhs": 0},
    {"replace_research_with_orbs": 3, "random_dissonance": 0},
    {"random_maps_software": 1, "random_grail": 1, "mantra_placement": 2},
    {"goal": 2, "glossanity_freestanding": 1, "glossanity_npc": 1, "glossanity_enemy": 1,
     "glossanity_scannable": 1, "costumesanity": 1, "oannesanity": 1, "dlc_item_logic": 1,
     "costume_clip": 1, "shuffle_guardian_souls": 1, "include_expensive_shop_item": 1},
)


_GLOSSARY_CODES = {BASE_ITEM_ID + int(g) for g in GLOSSARY_ITEM_IDS}


def _shape(item, pool_item=None):
    """(name, code, classification). The one sanctioned difference: on a
    glossary_hunt seed _demote_surplus_glossary randomly demotes the ROMs past
    the hunt count to filler in the pool, which no per-item path can know."""
    ref = pool_item or item
    if (ref.code in _GLOSSARY_CODES
            and ref.classification == ItemClassification.filler
            and item.classification == ItemClassification.progression_skip_balancing):
        return item.name, item.code, ItemClassification.filler
    return item.name, item.code, item.classification


def _build(options):
    mw = setup_solo_multiworld(LaMulana2World, (), seed=1)
    world = mw.worlds[1]
    for name, value in options.items():
        getattr(world.options, name).value = value
    for step in ("generate_early", "create_regions", "create_items"):
        call_all(mw, step)
    return mw, world


class TestItemShape(unittest.TestCase):
    def test_create_by_game_id_matches_pool(self):
        for options in OPTION_SETS:
            mw, world = _build(options)
            for pool_item in mw.itempool:
                if pool_item.player != 1:
                    continue
                game_id = get_game_item_id(pool_item)
                with self.subTest(options=options, item=pool_item.name, game_id=game_id):
                    made = create_item(world, pool_item.name, game_id=game_id)
                    self.assertEqual(_shape(made, pool_item), _shape(pool_item))
                    self.assertEqual(get_game_item_id(made), game_id)

    def test_create_by_name_matches_pool(self):
        for options in OPTION_SETS:
            mw, world = _build(options)
            seen = set()
            for pool_item in mw.itempool:
                if pool_item.player != 1 or pool_item.name in seen:
                    continue
                seen.add(pool_item.name)
                with self.subTest(options=options, item=pool_item.name):
                    self.assertEqual(_shape(world.create_item(pool_item.name), pool_item), _shape(pool_item))

    def test_placed_labels_match_server_names(self):
        """After a full fill, every own item's label (location_labels, read
        offline) is its AP name, and that name is what the server prints for
        its code -- so online and offline say the same thing."""
        from Fill import distribute_items_restrictive
        server_name = {code: name for name, code in LaMulana2World.item_name_to_id.items()}
        for options in OPTION_SETS + ({"shop_placement": 0, "mantra_placement": 0,
                                       "guardian_specific_ankhs": 0},):
            mw, world = _build(options)
            for step in ("set_rules", "connect_entrances", "pre_fill"):
                call_all(mw, step)
            distribute_items_restrictive(mw)
            labels = world._location_labels()
            for loc in mw.get_filled_locations(1):
                item = loc.item
                if item.player != 1 or item.code is None or not hasattr(loc, "game_location_id"):
                    continue
                with self.subTest(options=options, location=loc.name, item=item.name):
                    self.assertEqual(server_name.get(item.code), item.name)
                    self.assertEqual(labels[int(loc.game_location_id)], item.name)

    def test_every_datapackage_name_matches_pool(self):
        for options in OPTION_SETS:
            mw, world = _build(options)
            pool = {(i.name, i.code) for i in mw.itempool if i.player == 1}
            pool_names = {name for name, _ in pool}
            for name in LaMulana2World.item_name_to_id:
                if name in LOGIC_FLAG_MAP:
                    continue
                with self.subTest(options=options, name=name):
                    made = world.create_item(name)
                    if made.name in pool_names:
                        self.assertIn((made.name, made.code), pool)
