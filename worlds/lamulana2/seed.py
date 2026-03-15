from __future__ import annotations

import struct
from typing import BinaryIO, Iterable, List, Tuple

from .ids import ItemID, LocationID, ExitID, SHOP_WRITE_ORDER, AP_ITEM_PLACEHOLDER, BASE_ITEM_ID

# ============================================================
# AP item -> LM2 seed encoding (write-time only)
# ============================================================

# def _is_ap_placeholder_item_id(raw_item_id: int) -> bool:
#     # AP placeholders live in [410000, 420000)
#     return AP_ITEM_PLACEHOLDER <= raw_item_id < BASE_ITEM_ID

# ============================================================
# Low-level writers (C# BinaryWriter parity)
# ============================================================

def _write_i32(f: BinaryIO, value: int):
    f.write(struct.pack("<i", int(value)))


def _write_bool(f: BinaryIO, value: bool):
    # C# BinaryWriter.Write(bool) = 1 byte
    f.write(struct.pack("<?", bool(value)))


# ============================================================
# Public API
# ============================================================

def write_seed_file(
    *,
    path: str,
    starting_weapon: ItemID,
    starting_area: int,
    settings,
    starting_items: List[ItemID],
    item_placements: List[Tuple[LocationID, ItemID]],
    shop_placements: List[Tuple[LocationID, ItemID, int]],
    cursed_locations: List[LocationID],
    entrance_pairs: List[Tuple[ExitID, ExitID]],
    soul_gate_pairs: List[Tuple[ExitID, ExitID, int]],
):
    """
    Exact Python equivalent of FileUtils.WriteSeedFile()

    This function performs NO logic.
    It assumes all inputs are final and valid.
    """

    with open(path, "wb") as f:
        # ----------------------------------------------------
        # Header / Settings
        # ----------------------------------------------------
        # br.Write((int)randomiser.StartingWeapon.ID);
        _write_i32(f, starting_weapon)

        # br.Write((int)randomiser.StartingArea.ID);
        _write_i32(f, starting_area)

        # br.Write(randomiser.Settings.RandomDissonance);
        _write_bool(f, settings.random_dissonance)

        # br.Write(randomiser.Settings.RequiredGuardians);
        _write_i32(f, settings.required_guardians)

        # br.Write(randomiser.Settings.RequiredSkulls);
        _write_i32(f, settings.required_skulls)

        # br.Write(randomiser.Settings.RemoveITStatue);
        _write_bool(f, settings.remove_icefire_treetop_statue)

        # br.Write((int)randomiser.Settings.ChosenEchidna);
        _write_i32(f, settings.echidna_difficulty)

        # br.Write(randomiser.Settings.AutoScanTablets);
        _write_bool(f, settings.auto_scan)

        # br.Write(randomiser.Settings.AutoPlaceSkulls);
        _write_bool(f, settings.auto_skulls)

        # br.Write(randomiser.Settings.StartingMoney);
        _write_i32(f, settings.starting_money)

        # br.Write(randomiser.Settings.StartingWeights);
        _write_i32(f, settings.starting_weights)

        # br.Write((int)randomiser.Settings.ItemChestColour);
        _write_i32(f, settings.item_chest_color)

        # br.Write((int)randomiser.Settings.WeightChestColour);
        _write_i32(f, settings.filler_chest_color)

        # ----------------------------------------------------
        # Starting items
        # ----------------------------------------------------
        # br.Write(randomiser.StartingItems.Count);
        _write_i32(f, len(starting_items))

        # foreach (var item in randomiser.StartingItems)
        #     br.Write((int)item.ID);
        for item_id in starting_items:
            _write_i32(f, item_id)

        # ----------------------------------------------------
        # Normal item placements
        # ----------------------------------------------------
        # br.Write(items.Count);
        _write_i32(f, len(item_placements))

        # foreach(var item in items)
        # {
        #     br.Write((int)item.Item1);
        #     br.Write((int)item.Item2);
        # }
        for location_id, item_id in item_placements:
            location_id = LocationID(location_id)
            raw_item_id = int(item_id)

            _write_i32(f, location_id)
            _write_i32(f, raw_item_id)

        # ----------------------------------------------------
        # Shop placements
        # ----------------------------------------------------
        # br.Write(shopItems.Count);
        _write_i32(f, len(shop_placements))

        # foreach (var item in shopItems)
        # {
        #     br.Write((int)item.Item1);
        #     br.Write((int)item.Item2);
        #     br.Write(item.Item3);
        # }

        # Create a dictionary for quick lookup
        shop_dict = {loc_id: (item_id, price) for loc_id, item_id, price in shop_placements}
        
        # Write in the correct order from SHOP_WRITE_ORDER
        for location_id in SHOP_WRITE_ORDER:
            if location_id in shop_dict:
                item_id, price_multiplier = shop_dict[location_id]
                raw_item_id = int(item_id)

                _write_i32(f, location_id)
                _write_i32(f, raw_item_id)
                _write_i32(f, price_multiplier)

        # ----------------------------------------------------
        # Cursed locations
        # ----------------------------------------------------
        # br.Write(randomiser.CursedLocations.Count);
        _write_i32(f, len(cursed_locations))

        # foreach (Location location in randomiser.CursedLocations)
        #     br.Write((int)location.ID);
        for location_id in cursed_locations:
            _write_i32(f, location_id)

        # ----------------------------------------------------
        # Entrance pairs
        # ----------------------------------------------------
        # br.Write(randomiser.EntrancePairs.Count);
        _write_i32(f, len(entrance_pairs))

        # foreach(var d in randomiser.EntrancePairs)
        # {
        #     br.Write((int)d.Item1.ID);
        #     br.Write((int)d.Item2.ID);
        # }
        for exit_a, exit_b in entrance_pairs:
            _write_i32(f, exit_a)
            _write_i32(f, exit_b)

        # ----------------------------------------------------
        # Soul gate pairs
        # ----------------------------------------------------
        # br.Write(randomiser.SoulGatePairs.Count);
        _write_i32(f, len(soul_gate_pairs))

        # foreach (var s in randomiser.SoulGatePairs)
        # {
        #     br.Write((int)s.Item1.ID);
        #     br.Write((int)s.Item2.ID);
        #     br.Write(s.Item3);
        # }
        for exit_a, exit_b, requirement in soul_gate_pairs:
            _write_i32(f, exit_a)
            _write_i32(f, exit_b)
            _write_i32(f, requirement)
