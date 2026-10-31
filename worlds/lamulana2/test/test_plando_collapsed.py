"""Plando of a collapsed item family must take a real pool instance.

Core expands the "Sacred Orb" item group into its members before generation,
so plando arrives naming a variant like "Sacred Orb (GotD)". The pool only holds
items named "Sacred Orb", so without remapping plando minted an extra orb whose
game id duplicated one already in the pool (two locations on one client flag).
"""
import unittest
from collections import Counter

from Fill import distribute_planned_blocks, parse_planned_blocks, resolve_early_locations_for_planned
from Options import PlandoItem
from test.general import setup_solo_multiworld
from worlds.AutoWorld import call_all

from .. import LaMulana2World
from ..ids import BASE_ITEM_ID, ItemID
from ..items import create_item, get_game_item_id

ORB_CODE = BASE_ITEM_ID + ItemID.SacredOrb.value
LOC_A = "[ROY C-5] Glossary in Wall Above Korobock"
LOC_B = "[ROY E-4] NPC Glossary (Vili)"


def _orbs(items):
    return [i for i in items if i.player == 1 and i.code == ORB_CODE]


class TestPlandoCollapsedFamily(unittest.TestCase):
    def _build(self, blocks):
        mw = setup_solo_multiworld(LaMulana2World, (), seed=1)
        w = mw.worlds[1]
        w.options.glossanity_npc.value = 1
        w.options.glossanity_freestanding.value = 1
        w.options.plando_items.value = blocks
        for step in ("generate_early", "create_regions", "create_items", "set_rules"):
            call_all(mw, step)
        orbs_before = len(_orbs(mw.itempool))
        mw.plando_item_blocks = parse_planned_blocks(mw)
        call_all(mw, "connect_entrances")
        call_all(mw, "generate_basic")
        resolve_early_locations_for_planned(mw)
        distribute_planned_blocks(mw, [b for p in mw.plando_item_blocks for b in mw.plando_item_blocks[p]])
        return mw, orbs_before

    def test_variant_orbs_take_pool_instances(self):
        # The exact shape core hands us after expanding the "Sacred Orb" group.
        mw, orbs_before = self._build([
            PlandoItem(items={"Sacred Orb (GotD)": 1}, locations=[LOC_A], force=True),
            PlandoItem(items=["Sacred Orb (Bonus #6)"], locations=[LOC_B], force=True),
        ])
        for loc_name in (LOC_A, LOC_B):
            item = mw.get_location(loc_name, 1).item
            self.assertIsNotNone(item, loc_name)
            self.assertEqual(item.name, "Sacred Orb")
            self.assertEqual(item.code, ORB_CODE)

        placed = [loc.item for loc in mw.get_locations(1) if loc.item is not None]
        all_orbs = _orbs(mw.itempool) + _orbs(placed)
        self.assertEqual(len(all_orbs), orbs_before, "plando changed the orb count")
        dupes = {k: v for k, v in Counter(get_game_item_id(i) for i in all_orbs).items() if v > 1}
        self.assertEqual(dupes, {}, "orb game ids must stay unique")

    def test_create_item_labeled_member_matches_pool_shape(self):
        mw = setup_solo_multiworld(LaMulana2World, (), seed=1)
        w = mw.worlds[1]
        call_all(mw, "generate_early")
        orb = create_item(w, "Sacred Orb (GotD)")
        self.assertEqual((orb.name, orb.code), ("Sacred Orb", ORB_CODE))
        skull = create_item(w, "Crystal Skull (RoY)")
        self.assertEqual((skull.name, skull.code),
                         ("Crystal Skull", BASE_ITEM_ID + ItemID.CrystalSkull.value))
        # Maps keep their per-area name and id, like the pool.
        roy_map = create_item(w, "Map (Roots of Yggdrasil)")
        self.assertEqual((roy_map.name, roy_map.code),
                         ("Map (Roots of Yggdrasil)", BASE_ITEM_ID + ItemID.Map1.value))
