from __future__ import annotations

# =============================================================================
# Debug logging toggle
# Set DEBUG = True to enable verbose logging during AP generation.
# Leave False for public/alpha builds to suppress [ER], [DEBUG], etc. output.
# =============================================================================
DEBUG = True

def _log(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

import logging
import os
import zipfile
from typing import Dict, List, Tuple

from BaseClasses import Region, ItemClassification, Tutorial, CollectionState, LocationProgressType
from worlds.AutoWorld import World, WebWorld
from worlds.generic.Rules import set_rule, add_rule
from Options import Accessibility

from .options import LM2Options, StartingArea, StartingWeapon
from .ids import ItemID, LocationID, BASE_ITEM_ID, BASE_LOCATION_ID, ITEM_MAP, ITEM_LABEL_BY_ID, GUARDIAN_ANKHS_ITEMS, LOGIC_FLAG_LOCATION_IDS, POT_FLAG_MAP, GLOSSARY_FLAG_MAP, GLOSSARY_ITEM_IDS, DLC_LOCATION_IDS, COSTUME_LOCATION_IDS, DLC_AREA_IDS, POT_POOL_BY_LOC, GLOSSARY_POOLS_BY_ID, potsanity_pools_enabled, glossanity_pools_enabled, MISSABLE_LOCATION_IDS
from .items import (
    create_item, build_item_pool, apply_starting_inventory,
    ITEM_DEFS, AP_FILLER, AP_FILLER_NAMES, FILLER_DISTRIBUTION,
    create_filler_item, POT_FILLER_DISTRIBUTION, INTERNAL_ID_TO_REWARD,
    build_pot_filler_pool, build_item_name_groups
)
from .locations import (
    LM2Location, AreaID, create_locations, LOCATION_DEFS, LocationType,
    LOCATION_DEFS_BY_AP_ID, LOCATION_DEFS_BY_NAME, LM2LocationDef,
    AP_LOCATION_DEFS, build_location_name_groups
)
from .regions import create_regions
from .rules import set_rules
from .randomizer import LM2RandomizerCore
from .seed import write_seed_file, write_ap_seed_file

GAME_NAME = "La-Mulana 2"


# =============================================================================
# Web World (optional, minimal)
# =============================================================================

class LaMulana2WebWorld(WebWorld):
    game = GAME_NAME
    theme = "ruins"
    tutorials = []


# =============================================================================
# Starting Area / Weapon resolution tables
# =============================================================================

_STARTING_AREA_MAP: Dict[int, AreaID] = {
    StartingArea.option_village_of_departure: AreaID.VoD,
    StartingArea.option_roots_of_yggdrasil: AreaID.RoY,
    StartingArea.option_annwfn: AreaID.AnnwfnMain,
    StartingArea.option_immortal_battlefield: AreaID.IBMain,
    StartingArea.option_icefire_treetop: AreaID.ITLeft,
    StartingArea.option_divine_fortress: AreaID.DFMain,
    StartingArea.option_shrine_of_the_frost_giants: AreaID.SotFGGrail,
    StartingArea.option_takamagahara_shrine: AreaID.TSLeft,
    StartingArea.option_valhalla: AreaID.ValhallaMain,
    StartingArea.option_dark_star_lords_mausoleum: AreaID.DSLMMain,
    StartingArea.option_ancient_chaos: AreaID.ACTablet,
    StartingArea.option_hall_of_malice: AreaID.HoMTop,
}

_STARTING_AREA_PREREQS: Dict[int, Tuple[str, ...]] = {
    StartingArea.option_icefire_treetop: ("vertical_entrances",),
    StartingArea.option_divine_fortress: ("gate_entrances",),
    StartingArea.option_shrine_of_the_frost_giants: ("gate_entrances",),
    StartingArea.option_takamagahara_shrine: ("gate_entrances",),
    StartingArea.option_valhalla: ("gate_entrances",),
    StartingArea.option_dark_star_lords_mausoleum: ("gate_entrances",),
    StartingArea.option_ancient_chaos: ("gate_entrances",),
    StartingArea.option_hall_of_malice: ("gate_entrances",),
}

_STARTING_WEAPON_MAP: Dict[int, ItemID] = {
    StartingWeapon.option_leather_whip: ItemID.Whip1,
    StartingWeapon.option_knife: ItemID.Knife,
    StartingWeapon.option_rapier: ItemID.Rapier,
    StartingWeapon.option_axe: ItemID.Axe,
    StartingWeapon.option_katana: ItemID.Katana,
    StartingWeapon.option_shuriken: ItemID.Shuriken,
    StartingWeapon.option_rolling_shuriken: ItemID.RollingShuriken,
    StartingWeapon.option_earth_spear: ItemID.EarthSpear,
    StartingWeapon.option_flare: ItemID.Flare,
    StartingWeapon.option_caltrops: ItemID.Caltrops,
    StartingWeapon.option_chakram: ItemID.Chakram,
    StartingWeapon.option_bomb: ItemID.Bomb,
    StartingWeapon.option_pistol: ItemID.Pistol,
    StartingWeapon.option_claydoll_suit: ItemID.ClaydollSuit,
}


# =============================================================================
# Main World
# =============================================================================

class LaMulana2World(World):
    game = GAME_NAME
    web = LaMulana2WebWorld()
    options_dataclass = LM2Options
    topology_present = True

    # Universal Tracker: allow tracking without the player's YAML.
    # All generation-affecting options are echoed into slot_data["options"]
    # and read back in generate_early().
    ut_can_gen_without_yaml = True

    @staticmethod
    def interpret_slot_data(slot_data: dict) -> dict:
        # Returning the slot_data tells Universal Tracker to do a full
        # regeneration with multiworld.re_gen_passthrough[GAME_NAME] = slot_data.
        # We need that path because LM2's entrance randomization mutates
        # both region connections and entrance logic strings — easier to
        # bypass randomization than to reverse it after the fact.
        return slot_data

    # -------------------------------------------------------------------------
    # AP ID maps (pure AP-facing)
    # -------------------------------------------------------------------------

    item_name_to_id: Dict[str, int] = {
        item_def.name: item_def.ap_id
        for item_def in ITEM_DEFS
    }
    item_name_to_id.update({
        name: BASE_ITEM_ID + item_id.value
        for name, item_id in ITEM_MAP.items()
    })
    # Pin progressives to their base IDs explicitly
    item_name_to_id["Progressive Whip"]    = BASE_ITEM_ID + ItemID.Whip1.value
    item_name_to_id["Progressive Shield"]  = BASE_ITEM_ID + ItemID.Shield1.value
    item_name_to_id["Progressive Beherit"] = BASE_ITEM_ID + ItemID.ProgressiveBeherit1.value

    # Pin multi-ID same-label families to a single AP ID
    # Currently using unique labels for every item below -- not implemented.
    #item_name_to_id["Sacred Orb"] = BASE_ITEM_ID + ItemID.SacredOrb0.value
    #item_name_to_id["Ankh Jewel"] = BASE_ITEM_ID + ItemID.AnkhJewel1.value
    #item_name_to_id["Crystal Skull"] = BASE_ITEM_ID + ItemID.CrystalSkull1.value
    #item_name_to_id["Kosugi Research Papers"] = BASE_ITEM_ID + ItemID.Research1.value

    for _ankh_item_id, _ankh_specific_name in GUARDIAN_ANKHS_ITEMS.items():
        item_name_to_id[_ankh_specific_name] = BASE_ITEM_ID + _ankh_item_id.value

    # Register Coin/Weight filler items so the AP server can display their names
    for _filler_name, _filler_id in AP_FILLER:
        item_name_to_id[_filler_name] = BASE_ITEM_ID + _filler_id.value

    location_name_to_id: Dict[str, int] = {
        AP_LOCATION_DEFS.get(loc_id, loc_def.name): loc_def.ap_id
        for loc_id, loc_def in LOCATION_DEFS.items()
        if loc_id not in LOGIC_FLAG_LOCATION_IDS
    }
    location_name_to_id.update({
        "[RANDO] Starting Shop 1": BASE_LOCATION_ID + LocationID.StartingShop1.value,
        "[RANDO] Starting Shop 2": BASE_LOCATION_ID + LocationID.StartingShop2.value,
        "[RANDO] Starting Shop 3": BASE_LOCATION_ID + LocationID.StartingShop3.value,
    })

    item_name_groups: Dict[str, set] = build_item_name_groups()
    location_name_groups: Dict[str, set] = build_location_name_groups()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def generate_early(self) -> None:
        """
        Called before any item or location creation.
        Resolve options that affect world structure.
        """
        super().generate_early()

        ut_data = self._ut_passthrough()
        if ut_data is not None:
            # Universal Tracker regen: restore every option from slot_data
            # so anything downstream that reads self.options matches the
            # server. Uses Option.from_any to round-trip values produced by
            # Options.as_dict (which serializes to the option's "any" form).
            opts_dict = ut_data.get("options") or {}
            for key, value in opts_dict.items():
                current_opt = getattr(self.options, key, None)
                if current_opt is None:
                    continue
                try:
                    setattr(self.options, key, current_opt.from_any(value))
                except Exception:
                    pass
            # Use the resolved starting area/weapon from slot_data instead of
            # re-rolling — _choose_starting_area can use multiworld.random,
            # which would diverge from the server's RNG state.
            try:
                self.starting_area = AreaID(int(ut_data["starting_area"]))
            except (KeyError, ValueError, TypeError):
                self.starting_area = self._choose_starting_area()
            try:
                self.starting_weapon = ItemID(int(ut_data["starting_weapon"]))
            except (KeyError, ValueError, TypeError):
                self.starting_weapon = self._choose_starting_weapon()
        else:
            # Resolve starting area
            self.starting_area = self._choose_starting_area()

            # Resolve starting weapon
            self.starting_weapon = self._choose_starting_weapon()

        # DLC entrances may only be shuffled when Oannesanity is enabled.
        # Without Oannesanity the DLC areas contain no reachable locations
        # (see the DLC_AREA_IDS skip in create_items / build_location_pool),
        # so folding their entrances into the ER pool produces dead regions
        # and unsolvable seeds. Force the option off when the prerequisite
        # is missing rather than generate a broken world.
        if self.options.include_dlc_entrances and not self.options.oannesanity:
            logging.warning(
                f"[La-Mulana 2] {self.player_name}: 'Include DLC Entrances' requires "
                f"Oannesanity, which is disabled. Disabling DLC entrance shuffling."
            )
            self.options.include_dlc_entrances.value = 0

        # Add starting weapon to precollected items
        starting_weapon_name = self._get_weapon_name(self.starting_weapon)
        if starting_weapon_name:
            self.multiworld.push_precollected(
                create_item(self, starting_weapon_name)
            )

        apply_starting_inventory(self)

        # Resolve the victory condition (validates prereqs + clamps the
        # glossary-hunt count). Deterministic from options, so the UT regen
        # path re-derives the same result from restored options.
        self._resolve_goal()

        # The glossary_hunt goal begins with the Ruins Encyclopedia already in inventory.
        # _resolve_goal downgrades to beat_the_game when no glossanity category is enabled.
        from .options import Goal
        if self.goal == Goal.option_glossary_hunt:
            ruins_enc = create_item(self, "Ruins Encyclopedia")
            ruins_enc.classification = ItemClassification.progression
            self.multiworld.push_precollected(ruins_enc)

    def create_regions(self) -> None:
        regions = create_regions(self)
        self.regions_by_area_id = regions
        all_locations = create_locations(self)

        if self.starting_area != AreaID.VoD:
            all_locations.update(self._get_starting_shop_locations())

        included_locations = {}

        for key, loc in all_locations.items():
            if not self._should_include_location(loc):
                continue

            region = regions[loc.parent_area]
            region.locations.append(loc)
            loc.parent_region = region

            # Missable one-time glossary spawns must never hold progression —
            # if the check despawns, the seed would be uncompletable.
            if loc.game_location_id in MISSABLE_LOCATION_IDS:
                loc.progress_type = LocationProgressType.EXCLUDED

            included_locations[key] = loc

        self.locations = included_locations

    def create_item(self, name: str):
        # AP base hook used by plando_items (and create_filler).
        # Delegate to the module-level factory in items.py.
        return create_item(self, name)

    def create_items(self) -> None:
        """
        Create the item pool.
        Called by AP after create_regions, before setting rules.
        """
        self._debug_dump_settings()

        # Build the base item pool
        pool = build_item_pool(self)

        # Add pot filler items for whichever potsanity pools are enabled
        if potsanity_pools_enabled(self.options):
            pool += build_pot_filler_pool(self)

        # Add items to multiworld's item pool
        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        """
        Set access rules for locations and completion condition.
        This is THE critical method that makes AP understand LM2's logic.
        """
        # First, do any special pre-placements
        self.randomizer = LM2RandomizerCore(self)
        self.randomizer.setup_preplaced_items()

        # Set access rules using our logic trees
        set_rules(self)

    def pre_fill(self) -> None:
        mw = self.multiworld
        player = self.player

        # ── POST-RULES DIAGNOSTIC ─────────────────────────────────────
        try:
            from .entrances import _build_omniscient_state
            from BaseClasses import CollectionState as CS
            state = _build_omniscient_state(self)
            if hasattr(state, 'stale'):
                state.stale[player] = True

            # Check location-level with omniscient state
            unreachable = []
            for loc in mw.get_locations(player):
                if loc.parent_region is None:
                    continue
                try:
                    if hasattr(loc, 'can_reach') and not loc.can_reach(state):
                        unreachable.append(loc.name)
                except Exception:
                    unreachable.append(loc.name)

            # Count sphere-0 (precollected only) — unfilled slots
            s0 = CS(mw)
            for it in mw.precollected_items[player]:
                s0.collect(it)
            if hasattr(s0, 'stale'):
                s0.stale[player] = True
            sphere0_total = 0
            sphere0_unfilled = 0
            for loc in mw.get_locations(player):
                if loc.parent_region is None:
                    continue
                try:
                    if hasattr(loc, 'can_reach') and loc.can_reach(s0):
                        sphere0_total += 1
                        if loc.item is None:
                            sphere0_unfilled += 1
                except Exception:
                    pass

            total = sum(1 for _ in mw.get_locations(player))
            if unreachable:
                _log(f"[ER-DIAG] POST-RULES: {len(unreachable)} locations FAIL "
                      f"omniscient check: {unreachable[:10]}")
            _log(f"[ER-DIAG] POST-RULES: {total} locs total, "
                  f"sphere-0: {sphere0_total} accessible / {sphere0_unfilled} unfilled")
        except Exception as e:
            _log(f"[ER-DIAG] diagnostic failed: {e}")

        # ── Item/location balancing ───────────────────────────────────
        # Count fillable locations for this player
        # Top up filler by counting LM2 locations and LM2 items.
        all_locations = [
            loc for loc in mw.get_locations(player)
            if loc.player == player
        ]

        # Locations already holding one of OUR items (locked items + events).
        own_placed = [
            loc for loc in all_locations
            if loc.item is not None and loc.item.player == player
        ]

        # Our items still waiting in the pool.
        items = [
            item for item in mw.itempool
            if item.player == player
        ]

        missing = len(all_locations) - len(own_placed) - len(items)

        if missing > 0:
            from .items import build_pre_filler
            for _ in range(missing):
                mw.itempool.append(build_pre_filler(self))

    def connect_entrances(self) -> None:
        """
        AP lifecycle hook: called after create_regions/create_items, before set_rules.

        Structural ER and soul gate ER are run together in an outer retry loop.
        If soul gates cannot find a valid configuration for a given structural
        layout (some layouts are fundamentally incompatible), the entire
        structural layout is regenerated and both are retried.
        """
        ut_data = self._ut_passthrough()
        if ut_data is not None:
            # Universal Tracker regen: skip randomization, replay server's
            # exact layout from slot_data.
            self._apply_ut_layout(ut_data)
            return
        if self._is_ut_fake_gen():
            # UT's initial fake gen, before it has slot_data. The regen will
            # come next with the real layout; randomizing here just wastes
            # time and risks failing the retry budget.
            return

        opts = self.options
        any_structural = (
            opts.horizontal_entrances
            or opts.vertical_entrances
            or opts.gate_entrances
            or opts.unique_transitions
            or opts.full_random_entrances
        )
        # Value-only soul gate pass: vanilla pairings, but values may
        # still need rewriting (random_soul_gate_value, include_nine_soul_gates,
        # or random_dissonance N9 floor).
        sg_value_only = (not opts.soul_gate_entrances) and (
            opts.random_soul_gate_value
            or opts.include_nine_soul_gates
            or opts.random_dissonance
        )
        any_er = (any_structural
                   or opts.soul_gate_entrances
                   or sg_value_only)

        if not any_er:
            return

        OUTER_MAX = 10  # structural layout retries

        for outer in range(OUTER_MAX):
            # ── Structural ER ─────────────────────────────────────────────
            if any_structural:
                from .entrances import custom_structural_er
                try:
                    custom_structural_er(self)
                except RuntimeError as e:
                    if outer < OUTER_MAX - 1:
                        _log(f"[ER] Outer retry {outer + 1}: {e}")
                        continue
                    raise

            # ── Soul gate ER ──────────────────────────────────────────────
            if opts.soul_gate_entrances or sg_value_only:
                import random as _random
                from .entrances import SoulGateRandomizer, _validate_starting_cluster

                seed_val = self.multiworld.seed + outer  # vary RNG per outer attempt
                rng = _random.Random(seed_val)

                all_entrances = [
                    e for region in self.multiworld.get_regions(self.player)
                    for e in region.exits
                    if hasattr(e, 'game_exit_id')
                ]
                sgr = SoulGateRandomizer(rng, all_entrances, self)
                if sgr.randomize():
                    # Soul gates inject GuardianKills(N) logic which can shrink
                    # the reachable sphere-0.  Revalidate the starting cluster
                    # to ensure it's still viable after soul gate placement.
                    cluster_ok, cluster_msg = _validate_starting_cluster(self)
                    if not cluster_ok:
                        _log(f"[ER] Outer retry {outer + 1}: starting cluster "
                              f"collapsed after soul gates ({cluster_msg}), "
                              f"regenerating...")
                        continue

                    self._sg_pairs = sgr.soul_gate_pairs
                    return  # success — both structural and soul gates valid
                else:
                    # Soul gates exhausted retries on this structural layout.
                    # Retry with a new structural layout (only meaningful
                    # when structural ER is in play; value-only failures
                    # don't depend on the structural layout).
                    if not any_structural:
                        raise RuntimeError(
                            "Soul gate value-only randomization failed.")
                    if outer < OUTER_MAX - 1:
                        _log(f"[ER] Outer retry {outer + 1}: structural layout "
                              f"incompatible with soul gates, regenerating...")
                    continue
            else:
                return  # no soul gates, structural ER alone is sufficient

        raise RuntimeError(
            f"Entrance randomization failed after {OUTER_MAX} full retries "
            f"(structural + soul gates)."
        )

    def generate_basic(self) -> None:
        """
        Called after set_rules, before AP's fill algorithm.
        This is where we can do final setup before AP fills items.
        """
        # Nothing needed here - AP will handle the fill
        pass

    def post_fill(self) -> None:
        """
        Called after AP has filled all items.
        Do any post-processing here.
        """
        # Fix filler items with proper location type
        self.randomizer._fix_empty_locations()

    def pre_output(self) -> None:
        # balance_multiworld_progression (Main.py) runs between post_fill
        # and pre_output and may swap items between players' locations.
        # Anything that snapshots loc.item must run here, after balancing,
        # but pre_output is still synchronous — mutations to loc.item are
        # visible to write_multidata in the thread pool that follows.
        if self.randomizer.shop_entries:
            self.randomizer._adjust_shop_prices()

        self.randomizer.precompute_filler_ids()

    def fill_slot_data(self) -> dict:
        """
        Return data to be sent to the client.
        This is used by the game client to apply the randomization.
        With the standalone BepInEx mod, this replaces the seed.lm2r file entirely.
        """
        # Collect shop entries (location, item, price multiplier)
        shop_entries = []
        for entry in self.randomizer.shop_entries:
            shop_entries.append({
                "location": int(entry.location_id),
                "item": int(entry.item_id),
                "price": entry.price_multiplier
            })

        # Full item placements (location -> item mapping)
        item_placements = [
            {"location": int(loc_id), "item": int(item_id)}
            for loc_id, item_id in self.randomizer.get_item_placements()
        ]

        # Shop placements with prices
        shop_placements = [
            {"location": int(loc_id), "item": int(item_id), "price": price}
            for loc_id, item_id, price in self.randomizer.get_shop_placements()
        ]

        # Display name per LocationID — same data as the lm2ap labels
        # section, sent here so the online path can also override the
        # vanilla BoxName (e.g. show "Ankh Jewel (Vritra)" instead of
        # the generic "Ankh Jewel").
        # Prefer the descriptive ITEM_MAP label (so e.g. a Map item
        # carries "Map (Roots of Yggdrasil)" rather than the generic
        # AP name "Map"); fall back to loc.item.name for foreign items
        # and anything not registered in ITEM_MAP.
        slot_location_labels: Dict[str, str] = {}
        for loc in self.multiworld.get_filled_locations(self.player):
            if not hasattr(loc, "game_location_id"):
                continue
            if loc.item is None:
                continue
            slot_location_labels[str(int(loc.game_location_id))] = (
                self._label_for_location(loc)
            )

        _enabled_pot_pools = potsanity_pools_enabled(self.options)
        _enabled_gloss_cats = glossanity_pools_enabled(self.options)

        return {
            # Existing fields
            "starting_area": int(self.starting_area),
            "starting_weapon": int(self.starting_weapon),
            "goal": int(getattr(self, "goal", 0)),
            "glossary_hunt_count": int(getattr(self, "glossary_hunt_count", 0)),
            "starting_items": [int(item_id) for item_id in self.randomizer.get_starting_items()],
            "cursed_locations": [int(loc_id) for loc_id in self.randomizer.cursed_locations],
            "item_placements": item_placements,
            "shop_placements": shop_placements,
            "shop_entries": shop_entries,
            "entrance_pairs": self.randomizer.get_entrance_pairs(),
            "soul_gate_pairs": self.randomizer.get_soul_gate_pairs(),

            # Seed header settings
            "random_dissonance": int(self.options.random_dissonance),
            "random_research": int(self.options.random_research),
            "required_guardians": int(self.options.required_guardians),
            "required_skulls": int(self.options.required_skulls),
            "remove_it_statue": int(self.options.remove_icefire_treetop_statue),
            "echidna": int(self.options.echidna_difficulty),
            "auto_scan_tablets": int(self.options.auto_scan),
            "greedy_charon": int(self.options.greedy_charon),
            "logic_difficulty": int(self.options.logic_difficulty),
            "game_difficulty": int(self.options.game_difficulty),
            "costume_clip": int(self.options.costume_clip),
            "costumesanity": int(self.options.costumesanity),
            "dlc_item_logic": int(self.options.dlc_item_logic),
            "life_sigil_to_awaken_hom": int(self.options.life_sigil_to_awaken_hom),
            "auto_place_skull": int(self.options.auto_skulls),
            "starting_money": int(self.options.starting_money),
            "starting_weights": int(self.options.starting_weights),
            "item_chest_color": int(self.options.item_chest_color),
            "filler_chest_color": int(self.options.filler_chest_color),
            "ap_chest_color": int(self.options.ap_chest_color),

            # AP unique settings
            "guardian_specific_ankhs": int(self.options.guardian_specific_ankhs),

            # Potsanity (partitioned) — mod just needs "active"; the pot_flag_map
            # is restricted to the pots whose pool is enabled.
            "potsanity": int(bool(_enabled_pot_pools)),
            "pot_flag_map": {str(k): v for k, v in POT_FLAG_MAP.items()
                             if POT_POOL_BY_LOC.get(k) in _enabled_pot_pools},

            # Glossanity (partitioned) — only the PLACED locations are live AP checks.
            # The flag map is restricted to entries whose category is enabled.
            "glossanity": int(bool(_enabled_gloss_cats)),
            "glossary_flag_map": {str(k): v for k, v in GLOSSARY_FLAG_MAP.items()
                                  if k in GLOSSARY_ITEM_IDS
                                  and GLOSSARY_POOLS_BY_ID.get(int(k)) in _enabled_gloss_cats},

            # Per-location display names — see comment above the dict build.
            "location_labels": slot_location_labels,

            # AP settings
            "death_link": int(self.options.death_link),

            # Universal Tracker: full option dump so UT can re-run generation
            # without the player's YAML (ut_can_gen_without_yaml = True).
            # Read back in generate_early() via re_gen_passthrough.
            "options": self.options.as_dict(
                "accessibility",
                "goal", "glossary_hunt_count",
                "starting_area", "starting_weapon",
                "random_grail", "random_scanner", "random_codices", "random_fdc",
                "random_ring", "random_shell_horn", "random_maps_software",
                "mantra_placement", "shop_placement",
                "random_research", "remove_research", "replace_research_with_orbs", "remove_maps",
                "required_skulls", "remove_excess_skulls", "random_dissonance",
                "potsanity_low_value", "potsanity_high_value", "potsanity_shuriken",
                "potsanity_rolling_shuriken", "potsanity_earth_spear", "potsanity_flare",
                "potsanity_caltrops", "potsanity_chakram", "potsanity_bomb",
                "glossanity_freestanding", "glossanity_scannable",
                "glossanity_npc", "glossanity_enemy", "oannesanity", "costumesanity",
                "required_guardians", "guardian_specific_ankhs", "logic_difficulty",
                "game_difficulty",
                "echidna_difficulty", "costume_clip", "require_fdc",
                "dlc_item_logic", "life_sigil_to_awaken_hom",
                "remove_icefire_treetop_statue", "random_cursed_chests", "cursed_chests",
                "horizontal_entrances", "vertical_entrances", "gate_entrances",
                "unique_transitions", "full_random_entrances", "prevent_area_loops",
                "include_dlc_entrances",
                "soul_gate_entrances", "include_nine_soul_gates", "random_soul_gate_value",
                "auto_scan", "auto_skulls", "greedy_charon",
                "starting_money", "starting_weights",
                "item_chest_color", "filler_chest_color", "ap_chest_color",
                "write_seed_file", "death_link",
            ),
        }

    def write_spoiler(self, spoiler_handle):
        """Write spoiler log information."""
        spoiler_data = self.get_spoiler_log_data()
        
        # Write header
        spoiler_handle.write(f"\nLa-Mulana 2 Randomizer Spoiler Log\n")
        spoiler_handle.write(f"=" * 80 + "\n")
        spoiler_handle.write(f"Seed: {spoiler_data['seed']}\n")
        spoiler_handle.write(f"Player: {spoiler_data['player']}\n\n")
        
        # Write settings
        spoiler_handle.write(f"Settings:\n")
        spoiler_handle.write(f"-" * 40 + "\n")
        spoiler_handle.write(f"Starting Area: {spoiler_data['starting_area']}\n")
        spoiler_handle.write(f"Starting Weapon: {spoiler_data['starting_weapon']}\n")
        spoiler_handle.write(f"Starting Items: {', '.join(spoiler_data['starting_items']) if spoiler_data['starting_items'] else 'None'}\n\n")
        
        # Write cursed locations
        if spoiler_data['cursed_locations']:
            spoiler_handle.write(f"Cursed Locations ({len(spoiler_data['cursed_locations'])}):\n")
            spoiler_handle.write(f"-" * 40 + "\n")
            for loc in sorted(spoiler_data['cursed_locations']):
                spoiler_handle.write(f"  {loc}\n")
            spoiler_handle.write("\n")
        
        # Write entrances  
        exit_name: Dict[int, str] = {}
        for e in self.multiworld.get_entrances(self.player):
            if hasattr(e, "game_exit_id"):
                try:
                    exit_name[int(e.game_exit_id)] = e.name
                except Exception:
                    pass

        def _exit_label(x: int) -> str:
            return exit_name.get(int(x), f"Exit {int(x)}")

        # ----------------------------------------------------------------------
        # Entrances (original-rando style)
        # ----------------------------------------------------------------------
        if spoiler_data["entrances"]:
            spoiler_handle.write('Entrances:\n')
            spoiler_handle.write('-' * 40 + '\n')

            # spoiler_data["entrances"] is List[Tuple[int,int]]
            pairs = sorted(spoiler_data["entrances"], key=lambda p: (_exit_label(p[0]), _exit_label(p[1])))

            for a, b in pairs:
                spoiler_handle.write(f'  "{_exit_label(a)}": "{_exit_label(b)}"\n')
            spoiler_handle.write("\n")

        # ----------------------------------------------------------------------
        # Soul Gates (grouped by soul amount, original-rando style)
        # ----------------------------------------------------------------------
        if spoiler_data["soul_gates"]:
            spoiler_handle.write('Soul Gates:\n')
            spoiler_handle.write('-' * 40 + '\n')

            # spoiler_data["soul_gates"] is List[Tuple[int,int,int]] -> (gate1, gate2, souls)
            by_cost: Dict[int, List[Tuple[int, int]]] = {}
            for g1, g2, cost in spoiler_data["soul_gates"]:
                by_cost.setdefault(int(cost), []).append((int(g1), int(g2)))

            for cost in sorted(by_cost.keys()):
                spoiler_handle.write(f'  "{cost}":\n')
                # Print both directions like the original JSON mapping
                for g1, g2 in sorted(by_cost[cost], key=lambda p: (_exit_label(p[0]), _exit_label(p[1]))):
                    spoiler_handle.write(f'    "{_exit_label(g1)}": "{_exit_label(g2)}"\n')
                    spoiler_handle.write(f'    "{_exit_label(g2)}": "{_exit_label(g1)}"\n')
            spoiler_handle.write("\n")

        # Write all locations
        spoiler_handle.write(f"\nAll Locations:\n")
        spoiler_handle.write(f"=" * 80 + "\n")
        
        all_locations = []
        for loc in self.multiworld.get_locations(self.player):
            if loc.item and loc.item.player == self.player and hasattr(loc, 'game_location_id'):
                all_locations.append((loc.game_location_id.value, loc.name, loc.item.name))
        
        # Sort by LocationID
        all_locations.sort(key=lambda x: x[0])
        
        for _, loc_name, item_name in all_locations:
            spoiler_handle.write(f"{loc_name:40} -> {item_name}\n")

    def get_spoiler_log_data(self) -> dict:
        """Collect spoiler log data."""
        return {
            "seed": self.multiworld.seed,
            "player": self.player,
            "starting_area": self.starting_area.name if hasattr(self.starting_area, 'name') else str(self.starting_area),
            "starting_weapon": self._get_weapon_name(self.starting_weapon),
            "starting_items": [item.name for item in self.multiworld.precollected_items[self.player]],
            "cursed_locations": [loc.name for loc in self.multiworld.get_locations(self.player) if hasattr(loc, 'game_location_id') and loc.game_location_id in self.randomizer.cursed_locations],
            "entrances": self.randomizer.get_entrance_pairs(),
            "soul_gates": self.randomizer.get_soul_gate_pairs()
        }
    
    # -------------------------------------------------------------------------

    def generate_output(self, output_directory: str) -> None:
        if self._is_ut_fake_gen():
            return

        if self.options.write_seed_file:
            import os
            import json
            import zipfile
            import tempfile
            import Utils

            mw = self.multiworld
            player = self.player

            manifest = {
            "game": "La-Mulana 2",
            "player": player,
            "patch_file_ending": ".zip"
            }

            output_path = os.path.join(
                output_directory,
                f"AP-{mw.seed_name}-P{player}-{mw.get_file_safe_player_name(player)}_{Utils.__version__}.zip"
            )

            item_placements = self.randomizer.get_item_placements()

            with tempfile.TemporaryDirectory() as tmpdir:
                lm2r_path = os.path.join(tmpdir, "seed.lm2r")
                lm2ap_path = os.path.join(tmpdir, "seed.lm2ap")

                # Legacy LM2 randomizer seed (chests/shops/entrances/soul gates).
                # Pot placements are stripped inside write_seed_file so the
                # original-rando mod can still parse this file.
                write_seed_file(
                    path=lm2r_path,
                    starting_weapon=self.randomizer.starting_weapon,
                    starting_area=self.randomizer.starting_area,
                    settings=self.options,
                    starting_items=self.randomizer.get_starting_items(),
                    item_placements=item_placements,
                    shop_placements=self.randomizer.get_shop_placements(),
                    cursed_locations=self.randomizer.get_cursed_locations(),
                    entrance_pairs=self.randomizer.get_entrance_pairs(),
                    soul_gate_pairs=self.randomizer.get_soul_gate_pairs(),
                )

                # AP-extended companion: AP-only settings, pot placements,
                # and pot LocationID -> in-game potFlagNo map. Pot data is
                # only meaningful when potsanity is enabled, but settings
                # are always worth carrying for solo replay.
                _seed_pot_pools = potsanity_pools_enabled(self.options)
                pot_flag_map = {
                    int(k): int(v) for k, v in POT_FLAG_MAP.items()
                    if POT_POOL_BY_LOC.get(k) in _seed_pot_pools
                }

                # Display name per LocationID — captures every filled
                # location (own + foreign) so the C# mod can label items
                # in offline mode and so guardian-specific Ankh names
                # survive in place of the vanilla BoxName.
                # See _label_for_location for the ITEM_MAP-first / loc.item.name
                # fallback rationale (matches slot_data["location_labels"]).
                location_labels: Dict[int, str] = {}
                for loc in mw.get_filled_locations(player):
                    if not hasattr(loc, "game_location_id"):
                        continue
                    if loc.item is None:
                        continue
                    location_labels[int(loc.game_location_id)] = (
                        self._label_for_location(loc)
                    )

                write_ap_seed_file(
                    path=lm2ap_path,
                    settings=self.options,
                    item_placements=item_placements,
                    pot_flag_map=pot_flag_map,
                    location_labels=location_labels,
                )

                # Package both seed files plus manifest into the AP zip
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, True, 9) as output_zip:
                    output_zip.write(lm2r_path, arcname="seed.lm2r")
                    output_zip.write(lm2ap_path, arcname="seed.lm2ap")
                    output_zip.writestr(
                        "archipelago.json",
                        json.dumps(manifest).encode("utf-8")
                    )

    # =============================================================================
    # Helpers
    # =============================================================================

    def _label_for_location(self, loc) -> str:
        """
        Player-facing label for the item at this location.

        Prefers the descriptive ITEM_MAP entry keyed by the underlying game
        ItemID (so e.g. Maps and Sacred Orbs carry their area-specific names
        rather than the generic AP display name), and falls back to
        loc.item.name when the item isn't registered there — that catches
        foreign-player items, AP filler bundles, and any one-offs that don't
        have an ITEM_MAP entry.

        For LM2Items carrying lm2_game_id (Progressive Whip/Shield/Beherit and
        the guardian-specific Ankh Jewels), we look up by the underlying
        per-tier game ID first; ITEM_MAP doesn't have entries for the
        intermediate progressive IDs, so the lookup naturally falls through
        to loc.item.name (which is the AP-side label like "Progressive Whip"
        or "Ankh Jewel (Vritra)").
        """
        item = loc.item
        # LM2Item-specific game ID (preserves progressives + guardian ankhs).
        game_id = getattr(item, "lm2_game_id", None)
        if game_id is None:
            code = getattr(item, "code", None)
            if isinstance(code, int) and code >= BASE_ITEM_ID:
                try:
                    game_id = ItemID(code - BASE_ITEM_ID)
                except ValueError:
                    game_id = None
        if game_id is not None:
            label = ITEM_LABEL_BY_ID.get(game_id)
            if label:
                return label
        return item.name

    def _should_include_location(self, loc) -> bool:
        """Determine if a location should be included in the pool."""
        """
        from .locations import is_shop_location, is_mural_location

        # Skip shops if using original placement
        if is_shop_location(loc) and self.options.shop_placement.value == 0:
            return False

        if is_mural_location(loc) and self.options.mantra_placement.value == 0:
            return False

        # Skip research if not enabled
        if "Research" in loc.name and not self.options.random_research:
            return False
        """
        # Skip starting shops if we're starting in Village (they're in the base game)
        if self.starting_area == AreaID.VoD and "Starting Shop" in loc.name:
            return False

        # Skip pot locations whose content pool's potsanity toggle is off
        if loc.location_type == LocationType.Pot:
            pool = POT_POOL_BY_LOC.get(loc.game_location_id)
            if pool is None or not getattr(self.options, f"potsanity_{pool}"):
                return False

        # Skip glossary locations whose category's glossanity toggle is off
        if loc.location_type == LocationType.Glossary:
            cat = GLOSSARY_POOLS_BY_ID.get(int(loc.game_location_id))
            if cat is None or not getattr(self.options, f"glossanity_{cat}"):
                return False

        # Skip DLC locations unless the player opts in
        if loc.game_location_id in DLC_LOCATION_IDS and not self.options.oannesanity:
            return False

        # Skip every location in a DLC region (Spring in the Sky / Tower of
        # Oannes / Bailey / Eden) unless oannesanity — covers DLC minibosses
        # (logic-flag events) and any chest/glossary in those areas. Without
        # the DLC there is no reachable path into these regions.
        if loc.parent_area in DLC_AREA_IDS and not self.options.oannesanity:
            return False

        # Skip costume closets unless costumesanity is on. (Fish Suit is also in
        # DLC_LOCATION_IDS above, so it additionally requires oannesanity.)
        if loc.game_location_id in COSTUME_LOCATION_IDS and not self.options.costumesanity:
            return False

        return True

    def _get_starting_shop_locations(self):
        """Create and return starting shop locations specific to this player's starting area."""
        shops = {}
        starting_shop_names = ["[RANDO] Starting Shop 1", "[RANDO] Starting Shop 2", "[RANDO] Starting Shop 3"]
        starting_shop_ids = [LocationID.StartingShop1, LocationID.StartingShop2, LocationID.StartingShop3]
        
        for name, loc_id in zip(starting_shop_names, starting_shop_ids):
            ap_id = BASE_LOCATION_ID + loc_id.value
            
            loc_def = LM2LocationDef(
                name=name,
                game_id=loc_id,
                location_type=LocationType.Shop,
                logic="True",
                tricky_logic=None,
                minimal_logic=None,
                parent_area=self.starting_area,
                ap_id=ap_id,
            )
            
            shops[loc_id] = LM2Location(self, loc_def)
            
        return shops

    # =============================================================================
    # Universal Tracker helpers
    # =============================================================================

    def _ut_passthrough(self) -> "dict | None":
        rgp = getattr(self.multiworld, "re_gen_passthrough", None)
        if not rgp:
            return None
        return rgp.get(self.game)

    def _is_ut_fake_gen(self) -> bool:
        return getattr(self.multiworld, "generation_is_fake", False)

    def _apply_ut_layout(self, slot_data: dict) -> None:
        """Apply server-provided entrance + soul-gate layout (UT regen path).

        Bypasses the randomized custom_structural_er / SoulGateRandomizer flow:
        we already know the exact pairings from slot_data, so we just replay
        them onto the freshly-created (vanilla-connected) regions.
        """
        from .ids import ExitID
        from .entrances import (
            EntrancePair, SoulGatePair, SoulGateRandomizer,
        )

        all_entrances = [
            e for region in self.multiworld.get_regions(self.player)
            for e in region.exits
            if hasattr(e, "game_exit_id")
        ]
        entrances_by_id = {int(e.game_exit_id): e for e in all_entrances}

        # ── Structural entrance pairs ─────────────────────────────────
        # _er_pairs holds ONE tuple per logical pair; both directions are
        # rewired here (mirrors entrances._apply_pairings at line 1874).
        er_pairs_raw = slot_data.get("entrance_pairs") or []
        applied_er: list = []
        for raw in er_pairs_raw:
            try:
                from_id = int(raw[0])
                to_id = int(raw[1])
            except (TypeError, ValueError, IndexError):
                continue
            e_from = entrances_by_id.get(from_id)
            e_to = entrances_by_id.get(to_id)
            if e_from is None or e_to is None:
                continue
            # Disconnect both from their current (vanilla) targets first.
            for e in (e_from, e_to):
                if e.connected_region is not None:
                    try:
                        e.connected_region.entrances.remove(e)
                    except ValueError:
                        pass
                    e.connected_region = None
            e_from.connect(e_to.parent_region)
            e_to.connect(e_from.parent_region)
            applied_er.append(EntrancePair(
                from_exit=e_from.game_exit_id,
                to_exit=e_to.game_exit_id,
            ))
        self._er_pairs = applied_er

        # ── Soul gate pairs ───────────────────────────────────────────
        # Two distinct server behaviours, replayed differently:
        #
        #  * Structural (soul_gate_entrances ON): gates were physically
        #    re-paired, so we must swap regions and re-inject cross-gate
        #    logic via _apply_gate_pair — same as the speculative path.
        #
        #  * Value-only (soul_gate_entrances OFF, but random_dissonance /
        #    random_soul_gate_value / include_nine): gates keep their
        #    vanilla destinations and vanilla logic from World.json; the
        #    server only rewrote the GuardianKills(N) literal. Calling
        #    _apply_gate_pair here would wrongly swap regions and append
        #    duplicate / partner clauses, so we override the literal only.
        sg_pairs_raw = slot_data.get("soul_gate_pairs") or []
        sgr = SoulGateRandomizer(rng=None, entrances=all_entrances, world=self)
        structural_sg = bool(self.options.soul_gate_entrances)
        applied_sg: list = []
        for raw in sg_pairs_raw:
            try:
                gate1_id = int(raw[0])
                gate2_id = int(raw[1])
                soul_amount = int(raw[2])
            except (TypeError, ValueError, IndexError):
                continue
            gate1 = entrances_by_id.get(gate1_id)
            gate2 = entrances_by_id.get(gate2_id)
            if gate1 is None or gate2 is None:
                continue
            if structural_sg:
                # Match the server's force_override condition (entrances.py:2482).
                is_nine_pair = (
                    gate1.game_exit_id == ExitID.f03GateN9
                    or gate2.game_exit_id == ExitID.f03GateN9
                )
                force_override = bool(self.options.random_dissonance) and is_nine_pair
                sgr._apply_gate_pair(
                    gate1, gate2, soul_amount,
                    swap_regions=True,
                    force_override=force_override,
                )
            else:
                # Value-only: gates already sit on their vanilla pairing
                # with vanilla logic; just rewrite the kill cost. Net logic
                # is equivalent to the server's (Setting(Random Soul Gates)
                # is False here, so the vanilla "or Setting(...)" branch is
                # dead and the GuardianKills literal alone governs access).
                sgr._override_guardian_kills(gate1, soul_amount)
                sgr._override_guardian_kills(gate2, soul_amount)
            applied_sg.append(SoulGatePair(
                gate1=gate1.game_exit_id,
                gate2=gate2.game_exit_id,
                soul_amount=soul_amount,
            ))
        self._sg_pairs = applied_sg

    def _available_glossary_count(self) -> int:
        """Number of Glossary ROM entries that will actually be shuffled, given
        the enabled Glossanity categories (and Oannesanity for DLC glossary).
        Mirrors the pool-building filter in items.build_item_pool so the
        glossary-hunt count can be clamped to something achievable."""
        from .ids import GLOSSARY_ITEM_IDS, DLC_GLOSSARY_IDS, GLOSSARY_POOLS_BY_ID
        count = 0
        for gid in GLOSSARY_ITEM_IDS:
            cat = GLOSSARY_POOLS_BY_ID.get(gid)
            if cat is None or not getattr(self.options, f"glossanity_{cat}"):
                continue
            if gid in DLC_GLOSSARY_IDS and not self.options.oannesanity:
                continue
            count += 1
        return count

    def _resolve_goal(self) -> None:
        """Resolve and validate the goal option.

        Sets self.goal (int, possibly downgraded to beat_the_game) and
        self.glossary_hunt_count (int, clamped to the achievable glossary
        count; 0 when the goal isn't glossary_hunt). Both are echoed into
        slot_data so the client knows which victory condition to send.
        """
        from .options import Goal
        goal = self.options.goal.value
        self.glossary_hunt_count = 0

        if goal == Goal.option_beat_the_dlc and not self.options.oannesanity:
            logging.warning(
                f"[La-Mulana 2] {self.player_name}: goal 'beat_the_dlc' requires "
                f"Oannesanity, which is disabled. Falling back to 'beat_the_game'."
            )
            goal = Goal.option_beat_the_game
        elif goal == Goal.option_glossary_hunt:
            available = self._available_glossary_count()
            if available <= 0:
                logging.warning(
                    f"[La-Mulana 2] {self.player_name}: goal 'glossary_hunt' requires "
                    f"at least one Glossanity category, but none are enabled. "
                    f"Falling back to 'beat_the_game'."
                )
                goal = Goal.option_beat_the_game
            else:
                requested = self.options.glossary_hunt_count.value
                self.glossary_hunt_count = min(requested, available)
                if self.glossary_hunt_count < requested:
                    logging.warning(
                        f"[La-Mulana 2] {self.player_name}: glossary_hunt_count "
                        f"{requested} exceeds the {available} Glossary entries shuffled "
                        f"by the enabled Glossanity options. Lowered to {available}."
                    )

        self.goal = goal

    def _starting_area_prereqs_met(self, area_value: int) -> bool:
        prereqs = _STARTING_AREA_PREREQS.get(area_value, ())
        return all(getattr(self.options, name).value for name in prereqs)

    def _choose_starting_area(self) -> AreaID:
        """Resolve the chosen starting area, re-rolling uniformly across valid
        areas if the picked one's entrance prerequisites aren't satisfied."""
        chosen = self.options.starting_area.value
        if self._starting_area_prereqs_met(chosen):
            return _STARTING_AREA_MAP[chosen]

        chosen_name = StartingArea.name_lookup[chosen]
        valid = [v for v in _STARTING_AREA_MAP if self._starting_area_prereqs_met(v)]
        if valid:
            rerolled = self.multiworld.random.choice(valid)
            logging.warning(
                f"[La-Mulana 2] {self.player_name}: starting area '{chosen_name}' requires "
                f"entrance options that are disabled. Re-rolled to '{StartingArea.name_lookup[rerolled]}'."
            )
            return _STARTING_AREA_MAP[rerolled]

        logging.warning(
            f"[La-Mulana 2] {self.player_name}: no valid starting area available with the "
            f"current entrance options. Falling back to Village of Departure."
        )
        return AreaID.VoD

    # -------------------------------------------------------------------------

    def _choose_starting_weapon(self) -> ItemID:
        """Resolve the chosen starting weapon."""
        return _STARTING_WEAPON_MAP[self.options.starting_weapon.value]

    def _get_weapon_name(self, weapon_id: ItemID) -> str:
        """Get the name of a weapon from its ID."""
        weapon_map = {
            ItemID.Whip1: "Progressive Whip",
            ItemID.Knife: "Knife",
            ItemID.Rapier: "Rapier",
            ItemID.Axe: "Axe",
            ItemID.Katana: "Katana",
            ItemID.Shuriken: "Shuriken",
            ItemID.RollingShuriken: "Rolling Shuriken",
            ItemID.EarthSpear: "Earth Spear",
            ItemID.Flare: "Flare Gun",
            ItemID.Caltrops: "Caltrops",
            ItemID.Chakram: "Chakram",
            ItemID.Bomb: "Bomb",
            ItemID.Pistol: "Pistol",
            ItemID.ClaydollSuit: "Claydoll Suit",
        }
        return weapon_map.get(weapon_id, "Progressive Whip")

    def get_filler_item_name(self) -> str:
        """
        Called by AP when it needs to generate a filler item for this world.
        We use our FILLER_DISTRIBUTION to ensure that even 'extra' items 
        added by the server follow our intended rarity (e.g. rare 100 Coins).
        """
        # Create a weighted list of names to pick from
        # e.g. ["1 Coin", "1 Coin", "10 Coins", "10 Coins", "10 Coins" ...]
        weights = [name for name, count in FILLER_DISTRIBUTION for _ in range(count)]
        
        # self.random is the seed-synced random provided by AutoWorld
        return self.random.choice(weights)

    def _debug_dump_settings(self):
        opts = self.options

        def opt(name):
            return getattr(opts, name).value if hasattr(getattr(opts, name), "value") else getattr(opts, name)

        _log("\n========== LM2 AP DEBUG: SEED SETTINGS ==========")

        # --- Starting Info ---
        _log("[START]")
        _log(f"  Starting Area: {getattr(self, 'starting_area', 'UNKNOWN')}")
        _log(f"  Starting Weapon: {getattr(self, 'starting_weapon', 'UNKNOWN')}")

        # If you track starting inventory explicitly
        starting_items = getattr(self, "starting_items", [])
        if starting_items:
            _log(f"  Starting Items: {[item.name for item in starting_items]}")
        else:
            _log("  Starting Items: None/Not yet assigned")

        # --- Core Options ---
        _log("\n[CORE OPTIONS]")
        _log(f"  Accessibility: {opt('accessibility')}")
        _log(f"  Progression Balancing: {opt('progression_balancing')}")
        _log(f"  Logic Difficulty: {opt('logic_difficulty')}")
        _log(f"  Game Difficulty: {opt('game_difficulty')}")
        _log(f"  Guardian Specific Ankhs: {opt('guardian_specific_ankhs')}")

        # --- Shops ---
        _log("\n[SHOPS]")
        _log(f"  Shop Placement: {opt('shop_placement')}")

        # --- Mantras ---
        _log("\n[MANTRAS]")
        _log(f"  Mantra Placement: {opt('mantra_placement')}")

        # --- Item Pool ---
        _log("\n[ITEM POOL]")
        _log(f"  Random Research: {opt('random_research')}")
        _log(f"  Remove Research: {opt('remove_research')}")
        _log(f"  Research to Sacred Orbs: {opt('replace_research_with_orbs')}")
        _log(f"  Remove Maps: {opt('remove_maps')}")
        _log(f"  Random Dissonance: {opt('random_dissonance')}")
        _log(f"  Required Guardians: {opt('required_guardians')}")
        _log(f"  Required Skulls: {opt('required_skulls')}")

        # --- Entrance Randomization ---
        _log("\n[ENTRANCE RANDOMIZER]")
        _log(f"  Horizontal Entrances: {opt('horizontal_entrances')}")
        _log(f"  Vertical Entrances: {opt('vertical_entrances')}")
        _log(f"  Gate Entrances: {opt('gate_entrances')}")
        _log(f"  Unique Transitions: {opt('unique_transitions')}")
        _log(f"  Soul Gate Entrances: {opt('soul_gate_entrances')}")
        _log(f"  Include 9 Gates: {opt('include_nine_soul_gates')}")
        _log(f"  Random Soul Gate Values: {opt('random_soul_gate_value')}")
        _log(f"  Full Random Entrances: {opt('full_random_entrances')}")
        _log(f"  Prevent Area Loops: {opt('prevent_area_loops')}")

        # --- QoL ---
        _log("\n[QOL]")
        _log(f"  Auto Scan: {opt('auto_scan')}")
        _log(f"  Auto Skulls: {opt('auto_skulls')}")
        _log(f"  Greedy Charon: {opt('greedy_charon')}")
        _log(f"  Starting Money: {opt('starting_money')}")
        _log(f"  Starting Weights: {opt('starting_weights')}")

        _log("================================================\n")