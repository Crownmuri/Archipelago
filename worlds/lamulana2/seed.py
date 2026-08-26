from __future__ import annotations

import struct
from typing import BinaryIO, Dict, Iterable, List, Tuple

from .ids import ItemID, LocationID, ExitID, SHOP_WRITE_ORDER, AP_ITEM_PLACEHOLDER, BASE_ITEM_ID, potsanity_pools_enabled, POT_FLAG_MAP, LEGACY_LOCATION_IDS

# ============================================================
# AP item -> LM2 seed encoding (write-time only)
# ============================================================

# def _is_ap_placeholder_item_id(raw_item_id: int) -> bool:
#     # AP placeholders live in [410000, 420000)
#     return AP_ITEM_PLACEHOLDER <= raw_item_id < BASE_ITEM_ID

# ============================================================
# .lm2ap format constants
# ============================================================
# Magic ASCII "LM2A" so the mod can validate the file before reading.
LM2AP_MAGIC = b"LM2A"
# Bump when the layout below changes in a non-backwards-compatible way.
# v2: appended location_labels section after pot_flag_map.
# v3: appended greedy_charon bool.
# v4: appended game_difficulty int32.
# v5: appended ap_placements (Glossary, Costumes, DLC)
LM2AP_VERSION = 5

# Pot LocationIDs are written here, not in the legacy items section,
# so seed.lm2r stays compatible with the original LM2 randomizer mod.
# Derived from POT_FLAG_MAP rather than an id range: pot ids are 400-716,
# but Glossary ids start at 2000, so a bare ">= 400" test also swallows
# every glossary location and files it as a pot.
POT_LOCATION_IDS = frozenset(int(loc_id) for loc_id in POT_FLAG_MAP)
_LEGACY_IDS = frozenset(int(loc_id) for loc_id in LEGACY_LOCATION_IDS)

# ============================================================
# Low-level writers (C# BinaryWriter parity)
# ============================================================

def _write_i32(f: BinaryIO, value: int):
    f.write(struct.pack("<i", int(value)))


def _write_bool(f: BinaryIO, value: bool):
    # C# BinaryWriter.Write(bool) = 1 byte
    f.write(struct.pack("<?", bool(value)))


def _write_string(f: BinaryIO, value: str):
    # i32 length prefix + UTF-8 bytes. Pairs with C# ReadInt32 + ReadBytes
    # + Encoding.UTF8.GetString. (We don't use BinaryWriter.Write(string)
    # because that uses 7-bit-encoded length, which is fiddly to emit
    # from Python.)
    encoded = value.encode("utf-8")
    _write_i32(f, len(encoded))
    f.write(encoded)


def _is_pot_location_id(loc_id: int) -> bool:
    return int(loc_id) in POT_LOCATION_IDS


def _is_legacy_location_id(loc_id: int) -> bool:
    """
    True if the ORIGINAL La-Mulana 2 randomizer knows this location.

    seed.lm2r may only carry these. Everything else -- pots, glossary, DLC,
    costumes -- is an AP addition and belongs in seed.lm2ap. The split is not
    an id range: the DLC boss reward chest is id 61, inside the legacy chest
    band, while plenty of higher ids are legacy.
    """
    return int(loc_id) in _LEGACY_IDS


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
    Exact Python equivalent of FileUtils.WriteSeedFile().

    Writes the legacy LaMulana2Randomizer seed.lm2r format so the original
    randomizer mod can load AP-generated seeds for solo play. Pot placements
    are filtered out here (they live in seed.lm2ap); everything else mirrors
    the C# layout byte-for-byte.

    This function performs NO logic.
    It assumes all inputs are final and valid.
    """

    # Only placements the original randomizer can parse belong here; pots,
    # glossary, DLC and costumes are AP additions and travel in the .lm2ap
    # companion instead.
    legacy_item_placements = [
        (loc_id, item_id) for loc_id, item_id in item_placements
        if _is_legacy_location_id(loc_id)
    ]

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
        _write_i32(f, len(legacy_item_placements))

        # foreach(var item in items)
        # {
        #     br.Write((int)item.Item1);
        #     br.Write((int)item.Item2);
        # }
        for location_id, item_id in legacy_item_placements:
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


def write_ap_seed_file(
    *,
    path: str,
    settings,
    item_placements: List[Tuple[LocationID, ItemID]],
    pot_flag_map: Dict[int, int],
    location_labels: Dict[int, str],
):
    """
    Write the AP-extended companion file `seed.lm2ap`.

    Holds settings and data the legacy seed format can't express: AP-specific
    toggles, pot placements (LocationIDs >= 400), and the LocationID -> in-game
    potFlagNo mapping the mod needs to apply pot rewards.

    Layout (little-endian, C# BinaryReader compatible):
        magic[4]        = "LM2A"
        version int32   = LM2AP_VERSION
        --- AP settings ---
        guardian_specific_ankhs   bool
        potsanity                 bool
        ap_chest_color            int32
        logic_difficulty          int32
        costume_clip              bool
        dlc_item_logic            bool
        life_sigil_to_awaken_hom  bool
        random_research           bool
        death_link                bool
        --- Pot placements (same shape as the legacy items section) ---
        pot_count int32
        for each: location_id int32, item_id int32
        --- Pot flag map ---
        pot_flag_count int32
        for each: location_id int32, pot_flag_no int32
        --- Location labels (v2+) ---
        Display name per LocationID. Covers AP-foreign items (where the C#
        mod has no other source of truth in offline mode) and own items
        whose AP name diverges from the vanilla BoxName, e.g. the
        guardian-specific "Ankh Jewel (Vritra)".
        label_count int32
        for each: location_id int32, name_byte_count int32, name UTF-8 bytes
        --- v3+ QoL toggles ---
        greedy_charon             bool
        --- v4+ Difficulty ---
        game_difficulty           int32
        --- v5+ AP placements ---
        ap_placement_count        int32
        [ location_id int32, item_id int32 ] * ap_placement_count
    """

    pot_placements = [
        (loc_id, item_id) for loc_id, item_id in item_placements
        if _is_pot_location_id(loc_id)
    ]
    # Every other AP-added placement: glossary, DLC, costumes. Anything the
    # original randomizer does not know and that is not already a pot.
    ap_placements = [
        (loc_id, item_id) for loc_id, item_id in item_placements
        if not _is_legacy_location_id(loc_id) and not _is_pot_location_id(loc_id)
    ]

    with open(path, "wb") as f:
        f.write(LM2AP_MAGIC)
        _write_i32(f, LM2AP_VERSION)

        # --- AP-only settings -------------------------------------------
        _write_bool(f, settings.guardian_specific_ankhs)
        # Potsanity is partitioned; the mod only needs "any pool active".
        _write_bool(f, bool(potsanity_pools_enabled(settings)))
        _write_i32(f, settings.ap_chest_color)
        _write_i32(f, settings.logic_difficulty)
        _write_bool(f, settings.costume_clip)
        _write_bool(f, settings.dlc_item_logic)
        _write_bool(f, settings.life_sigil_to_awaken_hom)
        _write_bool(f, settings.random_research)
        _write_bool(f, settings.death_link)

        # --- Pot placements ---------------------------------------------
        _write_i32(f, len(pot_placements))
        for location_id, item_id in pot_placements:
            _write_i32(f, int(location_id))
            _write_i32(f, int(item_id))

        # --- Pot flag map -----------------------------------------------
        flag_entries = [(int(loc_id), int(flag_no)) for loc_id, flag_no in pot_flag_map.items()]
        _write_i32(f, len(flag_entries))
        for location_id, flag_no in flag_entries:
            _write_i32(f, location_id)
            _write_i32(f, flag_no)

        # --- Location labels (v2+) --------------------------------------
        label_entries = sorted(location_labels.items())
        _write_i32(f, len(label_entries))
        for location_id, name in label_entries:
            _write_i32(f, int(location_id))
            _write_string(f, name)

        # --- v3+ QoL toggles --------------------------------------------
        _write_bool(f, settings.greedy_charon)

        # --- v4+ Difficulty ---------------------------------------------
        _write_i32(f, settings.game_difficulty)

        # --- AP placements (v5+) ----------------------------------------
        # Glossary / DLC / costume checks. These used to fall through into
        # seed.lm2r, which the legacy mod cannot read, so they were lost for
        # solo replay.
        _write_i32(f, len(ap_placements))
        for location_id, item_id in ap_placements:
            _write_i32(f, int(location_id))
            _write_i32(f, int(item_id))
