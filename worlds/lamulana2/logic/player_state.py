from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional, Dict, Set
import re
import weakref

from ..ids import AreaID, LocationID, ItemID, get_item_name_from_id

if TYPE_CHECKING:
    from BaseClasses import CollectionState, MultiWorld
    from ..locations import LM2Location, LocationType
    from ..regions import LM2Entrance

import weakref as _weakref
# WeakKeyDictionary so entries are GC'd when the CollectionState is discarded.
# Structure: { CollectionState -> { player_id -> (prog_count, PlayerStateAdapter) } }
_adapter_cache: "_weakref.WeakKeyDictionary[object, dict]" = _weakref.WeakKeyDictionary()


def get_cached_adapter(state, player: int, multiworld, options) -> "PlayerStateAdapter":
    """
    Return a PlayerStateAdapter for (state, player), rebuilding only when
    the player's prog_items total has changed (i.e. an item was collected).

    This means the expensive _initialize_from_state() loop runs at most
    once per sphere step instead of once per access-rule check.
    """
    state_cache = _adapter_cache.get(state)
    if state_cache is None:
        state_cache = {}
        _adapter_cache[state] = state_cache

    # Use the total count of collected advancement items as a cheap staleness key.
    current_count: int = sum(state.prog_items.get(player, {}).values())

    entry = state_cache.get(player)
    if entry is not None and entry[0] == current_count:
        return entry[1]

    # Rebuild
    adapter = PlayerStateAdapter(state, player, multiworld, options)
    world = multiworld.worlds[player]
    if adapter.starting_area is None:
        adapter.starting_area = getattr(world, "starting_area", None)

    state_cache[player] = (current_count, adapter)
    return adapter


class PlayerStateAdapter:
    """
    Archipelago-facing adapter for LM2 PlayerState logic.
    """
    
    BOSS_NAMES = {
        "Fafnir", "Surtr", "Vritra", "Kujata", "Aten Ra", 
        "Jormungand", "Anu", "Echidna", "Hel"
    }

    def __init__(self, state: "CollectionState", player: int, multiworld: "MultiWorld", options):
        self.state = state
        self.player = player
        self.multiworld = multiworld
        self.options = multiworld.worlds[player].options
        
        # Caching like C# PlayerState
        self.area_checks: Dict[int, bool] = {}
        self._checking_areas: Set[AreaID] = set()
        self.entrance_checks: Dict[str, bool] = {}
        self.collected_locations: Set[int] = set()
        
        # State flags
        self.softlock_check = False
        self.ignore_false_checks = False
        self.ignore_guardians = False
        self.escape_check = False
        
        self.starting_area = None
        
        world = multiworld.worlds[player]
        self.starting_weapon = getattr(world, 'starting_weapon', None)
        
        # Collected items tracking
        self._collected_items: Dict[str, int] = {}
        
        # Initialize from state
        self._initialize_from_state(state)

        # Setting overrides and region mappings
        self.setting_overrides = {
            "FDCForBacksides": "require_fdc",
            "AutoScan": "auto_scan",
            "AutoPlaceSkulls": "auto_skulls",
            "RandomDissonance": "random_dissonance",
            "RandomResearch": "random_research",
            "CostumeClip": "costume_clip",
            "HardBosses": "logic_difficulty",
            "RemoveITStatue": "remove_icefire_treetop_statue",
            "LifeForHoM": "life_sigil_to_awaken_hom",
            "DLCItem": "dlc_item_logic",
            "RandomCurses": "random_cursed_chests",
            "RequiredGuardians": "required_guardians",
            "RequiredSkulls": "required_skulls",
        }

        # Region ID mapping
        self.regions_by_id = {
            "VoD": "Village of Departure",
            "VoDLadder": "Village of Departure Ladder",
            "Start": "Starting Area",
            "InfernoCavern": "Inferno Cavern",
            "GateofGuidance": "Gate of Guidance",
            "GateofGuidanceLeft": "Gate of Guidance Left",
            "MausoleumofGiants": "Mausoleum of Giants",
            "MausoleumofGiantsRubble": "Mausoleum of Giants Left Door",
            "EndlessCorridor": "Endless Corridor",
            "GateofIllusion": "Gate of Illusion",
            "RoY": "Roots of Yggdrasil",
            "RoYTopLeft": "Roots of Yggdrasil Left Switch Gate",
            "RoYTopRight": "Roots of Yggdrasil Birth Sigil Gate",
            "RoYTopMiddle": "Roots of Yggdrasil Nidhogg Gate",
            "RoYMiddle": "Roots of Yggdrasil Middle",
            "RoYBottom": "Roots of Yggdrasil Bottom",
            "RoYBottomLeft": "Roots of Yggdrasil Bottom Left",
            "AnnwfnMain": "Annwfn Main",
            "AnnwfnOneWay": "Annwfn One Way Corridor",
            "AnnwfnSG": "Annwfn Soul Gate",
            "AnnwfnPoison": "Annwfn Poison",
            "AnnwfnRight": "Annwfn Right",
            "IBBifrost": "Immortal Battlefield Bifrost",
            "IBTop": "Immortal Battlefield Top",
            "IBTopLeft": "Immortal Battlefield Top Left",
            "IBCetusLadder": "Immortal Battlefield Cetus Ladder",
            "IBMain": "Immortal Battlefield Main",
            "IBRight": "Immortal Battlefield Right",
            "IBBottom": "Immortal Battlefield Bottom",
            "IBLeft": "Immortal Battlefield Left",
            "IBLeftSG": "Immortal Battlefield Left Soul Gate",
            "IBBattery": "Immortal Battlefield Battery",
            "IBDinosaur": "Immortal Battlefield Dinosaur",
            "IBMoon": "Immortal Battlefield Moon",
            "IBLadder": "Immortal Battlefield Ladder",
            "IBBoat": "Immortal Battlefield Spiral Boat",
            "Cavern": "Cavern",
            "Cliff": "Cliff",
            "AltarLeft": "Altar Left",
            "AltarRight": "Altar Right",
            "ITEntrance": "Icefire Treetop Entrance",
            "ITBottom": "Icefire Treetop Bottom",
            "ITSinmara": "Icefire Treetop Sinmara",
            "ITLeft": "Icefire Treetop Left",
            "ITRight": "Icefire Treetop Right",
            "ITRightLeftLadder": "Icefire Treetop Right Left Ladder",
            "ITVidofnir": "Icefire Treetop Vidofnir",
            "DFEntrance": "Divine Fortress Entrance",
            "DFRight": "Divine Fortress Right",
            "DFMain": "Divine Fortress Main",
            "DFTop": "Divine Fortress Top",
            "SotFGMain": "Shrine of the Frost Giants Main",
            "SotFGGrail": "Shrine of the Frost Giants Grail",
            "SotFGTop": "Shrine of the Frost Giants Top",
            "SotFGBalor": "Shrine of the Frost Giants Balor",
            "SotFGBlood": "Shrine of the Frost Giants Blood",
            "SotFGBloodTez": "Shrine of the Frost Giants Blood Tezcatlipoca",
            "SotFGLeft": "Shrine of the Frost Giants Left",
            "GotD": "Gate of the Dead",
            "GotDWedjet": "Gate of the Dead Wedjet Gate",
            "TSEntrance": "Takamagahara Shrine Entrance",
            "TSMain": "Takamagahara Shrine Main",
            "TSLeft": "Takamagahara Shrine Left",
            "TSNeck": "Takamagahara Shrine Neck",
            "TSNeckEntrance": "Takamagahara Shrine Neck Entrance",
            "TSBottom": "Takamagahara Shrine Bottom",
            "TSBlood": "Takamagahara Shrine Blood",
            "HL": "Heavens Labyrinth",
            "HLGate": "Heavens Labyrinth Gate",
            "HLSpun": "Heavens Labyrinth Spun",
            "HLCog": "Heavens Labyrinth Cog",
            "ValhallaMain": "Valhalla Main",
            "ValhallaTop": "Valhalla Top",
            "ValhallaTopRight": "Valhalla Top Right",
            "DSLMMain": "Dark Lords Mausoleum Main",
            "DSLMTop": "Dark Lords Mausoleum Top",
            "DSLMPyramid": "Dark Star Lords Mausoleum Pyramid",
            "Nibiru": "Nibiru",
            "ACBottom": "Ancient Chaos Bottom",
            "ACWind": "Ancient Chaos Wind",
            "ACTablet": "Ancient Chaos Tablet",
            "ACMain": "Ancient Chaos Main",
            "ACBlood": "Ancient Chaos Blood",
            "HoMTop": "Hall of Malice Top",
            "HoM": "Hall of Malice",
            "HoMAwoken": "Hall of Malice Awoken",
            "EPDEntrance": "Eternal Prison Doom Entrance",
            "EPDMain": "Eternal Prison Doom Main",
            "EPDTop": "Eternal Prison Doom Top",
            "EPDHel": "Eternal Prison Doom Hel",
            "EPG": "Eternal Prison Gloom",
            "SpiralHell": "Spiral Hell",
        }
    
    def _canonicalize_item_name(self, name: str) -> str:
        """
        Collapse AP-unique names back into the logic's pooled names.
        When guardian_specific_ankhs is ON, named ankh jewels keep their
        full name so Has("Ankh Jewel (Fafnir)") etc. work in logic.
        """
        if name.startswith("Ankh Jewel"):
            # Keep "Ankh Jewel (BossName)" intact when mode is active.
            # Plain "Ankh Jewel" (and "Ankh Jewel1"–"9") still collapse.
            guardian_specific = getattr(self.options, "guardian_specific_ankhs", None)
            if guardian_specific and name.startswith("Ankh Jewel ("):
                return name          # e.g. "Ankh Jewel (Fafnir)" stays
            return "Ankh Jewel"      # vanilla: collapse all variants
        if name.startswith("Sacred Orb"):
            return "Sacred Orb"
        if name.startswith("Crystal Skull"):
            return "Crystal Skull"
        return name
        

    def _initialize_from_state(self, state: "CollectionState"):
        """Initialize collected items from Archipelago CollectionState.

        Parity fix:
        - Count each AP item exactly once (canonicalized).
        - Only add derived counters (e.g., "Guardians") separately.
        - Avoid double-counting progressive/stacked/boss items.
        """

        # 1) Add starting weapon to collected items
        if self.starting_weapon:
            starting_weapon_name = get_item_name_from_id(self.starting_weapon)
            starting_weapon_canon = self._canonicalize_item_name(starting_weapon_name)
            self._collected_items[starting_weapon_canon] = self._collected_items.get(starting_weapon_canon, 0) + 1

            # Special case: if starting with subweapon, add corresponding ammo
            ammo_map = {
                ItemID.Shuriken: "Shuriken Ammo",
                ItemID.RollingShuriken: "Rolling Shuriken Ammo",
                ItemID.EarthSpear: "Earth Spear Ammo",
                ItemID.Flare: "Flare Ammo",
                ItemID.Caltrops: "Caltrops Ammo",
                ItemID.Chakram: "Chakram Ammo",
                ItemID.Bomb: "Bomb Ammo",
                ItemID.Pistol: "Pistol Ammo",
            }

            if self.starting_weapon in ammo_map:
                ammo_name = ammo_map[self.starting_weapon]
                ammo_canon = self._canonicalize_item_name(ammo_name)
                # Keep behavior consistent with your prior code: set to 99 (not additive)
                self._collected_items[ammo_canon] = 99

        # 2) Track all items for this player from Archipelago state
        for item_name in state.prog_items[self.player]:
            count = state.count(item_name, self.player)
            if count <= 0:
                continue

            # Add the item ONCE under canonical name (this covers progressive + stacked items too)
            canon = self._canonicalize_item_name(item_name)
            self._collected_items[canon] = self._collected_items.get(canon, 0) + count

            # When guardian_specific_ankhs is ON and this item kept its full
            # "Ankh Jewel (BossName)" form, also increment the generic pool
            # counter so AnkhCount() and _ankh_count() still work correctly
            # for any remaining vanilla logic that counts total jewels held.
            if canon != "Ankh Jewel" and canon.startswith("Ankh Jewel ("):
                self._collected_items["Ankh Jewel"] = (
                    self._collected_items.get("Ankh Jewel", 0) + count
                )

            # Derived counter for GuardianKills (do NOT re-add the boss item again)
            if (item_name in self.BOSS_NAMES) and (not self.ignore_guardians):
                self._collected_items["Guardians"] = self._collected_items.get("Guardians", 0) + count
    
    def set_starting_area(self, area_id):
        """Set the starting area for this player state."""
        self.starting_area = area_id

    # ============================================================================
    # FIXED: Sphere Calculation (C# Parity)
    # ============================================================================
    
    def get_reachable_locations_with_spheres(self, locations: List["LM2Location"]) -> Dict[int, List["LM2Location"]]:
        """
        FIXED: Sphere calculation that properly handles event locations (logic flags).
    
        Key fix: Use Archipelago's CollectionState.collect() method which handles events.
        """
        spheres = {}
        sphere_num = 0

        # Use the actual Archipelago state, not a copy
        # This is CRITICAL because we need events to auto-collect
        sphere_state = self

        max_spheres = 100
        while sphere_num < max_spheres:
            # Get reachable locations
            reachable_in_sphere = []
            for location in locations:
                # Skip already collected
                if location.game_location_id.value in sphere_state.collected_locations:
                    continue
            
                # Check accessibility using the current state
                if location.can_access(sphere_state.state):
                    reachable_in_sphere.append(location)

            if not reachable_in_sphere:
                break

            # Collect items from this sphere
            for location in reachable_in_sphere:
                sphere_state.collect_location(location)
                if location.item:
                    # CRITICAL: Use state.collect() which handles events properly
                    # This ensures event locations (logic flags) auto-collect
                    sphere_state.state.collect(location.item, True)
                
                    # Also update internal tracking
                    sphere_state._collect_item_name(location.item.name)

            spheres[sphere_num] = reachable_in_sphere

            # Clear false checks
            sphere_state.remove_false_checked_areas_and_entrances()

            sphere_num += 1

        return spheres
    
    # ============================================================================
    # Collection Methods
    # ============================================================================
    
    def collect_item(self, item):
        """Collect an item (handles both Item objects and strings)."""
        if isinstance(item, str):
            self._collect_item_name(item)
        else:
            # Handle Item object
            self._collect_item_name(item.name)
            # Also collect in AP state
            self.state.collect(item)
    
    def _collect_item_name(self, item_name: str):
        """FIXED: Matches C# CollectItem(string itemName) exactly."""
        if item_name in self._collected_items:
            self._collected_items[item_name] += 1
        else:
            self._collected_items[item_name] = 1

        # Keep the generic "Ankh Jewel" pool counter in sync when
        # a specific jewel is collected during softlock-fix simulation.
        if item_name.startswith("Ankh Jewel ("):
            self._collected_items["Ankh Jewel"] = (
                self._collected_items.get("Ankh Jewel", 0) + 1
            )
        
        # Track guardians
        if not self.ignore_guardians and item_name in self.BOSS_NAMES:
            if "Guardians" in self._collected_items:
                self._collected_items["Guardians"] += 1
            else:
                self._collected_items["Guardians"] = 1
    
    def collect_location(self, location: "LM2Location"):
        """Mark location as collected."""
        self.collected_locations.add(location.game_location_id.value)
    
    def remove_false_checked_areas_and_entrances(self):
        """Remove false cached values (C# parity)."""
        # Reset areas - keep only true values
        self.area_checks = {k: v for k, v in self.area_checks.items() if v}
        # Reset entrances - keep only true values
        self.entrance_checks = {k: v for k, v in self.entrance_checks.items() if v}
    
    def clear_checked_areas_and_entrances(self):
        """Clear all cached checks."""
        self.area_checks.clear()
        self.entrance_checks.clear()
        
    # ------------------------------
    # Core state management methods (C# parity)
    # ------------------------------
    
    def can_reach(self, target) -> bool:
        """
        Port of C# CanReach methods.
        Can be called with AreaID, string area name, or LM2Entrance.
        """
        if isinstance(target, str):
            return self._can_reach_by_name(target)
        elif hasattr(target, 'game_area_id'):  # AreaID enum
            return self._can_reach_by_area_id(target)
        elif hasattr(target, 'game_exit_id'):  # LM2Entrance
            return self._can_reach_entrance(target)
        else:
            # Assume it's an AreaID integer
            return self._can_reach_by_area_id(target)
    
    def _can_reach_by_area_id(self, area_id) -> bool:
        """Parity with C# PlayerState.CanReach(AreaID): cache + cycle guard + area reach via entrances."""
        # Convert to AreaID enum if needed
        if isinstance(area_id, int):
            try:
                area_id = AreaID(area_id)
            except ValueError:
                return False

        # Starting area always reachable
        if area_id == self.starting_area:
            return True

        # Cache
        if area_id in self.area_checks:
            return self.area_checks[area_id]

        # Cycle guard (parity with area.Checking)
        if area_id in self._checking_areas:
            return False

        self._checking_areas.add(area_id)
        try:
            # Parity with Area.CanReach: derive reachability from entrances.
            # In AP, Region reachability is computed from connected entrances' access_rules.
            world = self.multiworld.worlds[self.player]
            regions_by_area = getattr(world, "regions_by_area_id", None)

            if regions_by_area and area_id in regions_by_area:
                region = regions_by_area[area_id]
                can_reach = self.state.can_reach(region, "Region", self.player)
            else:
                # Fallback: try name mapping (optional)
                region_name = self.regions_by_id.get(area_id.name) or self.regions_by_id.get(area_id.name.replace("AreaID.", ""))
                if not region_name:
                    can_reach = False
                else:
                    region = self.multiworld.get_region(region_name, self.player)
                    can_reach = self.state.can_reach(region, "Region", self.player)

            # Cache (your adapter currently doesn't implement IgnoreFalseChecks; cache both like default C# mode)
            self.area_checks[area_id] = can_reach
            return can_reach

        finally:
            self._checking_areas.remove(area_id)

    def _can_reach_by_name(self, area_name: str) -> bool:
        """Port of C# CanReach(string areaName)"""
        # Remove whitespace like C#
        normalized = re.sub(r'\s+', '', area_name)
        
        try:
            area_id = AreaID[normalized]
            return self._can_reach_by_area_id(area_id)
        except KeyError:
            # Check if it's a specific location name instead of area
            # Some logic checks might use location names
            print(f"[LM2 LOGIC WARNING] Unknown area: {area_name} (normalized: {normalized})")
            return False
    
    def _can_reach_entrance(self, entrance: "LM2Entrance") -> bool:
        """Port of C# CanReach(Exit entrance) — shares adapter so cache/flags/cycle-guard propagate."""
        if entrance.name in self.entrance_checks:
            return self.entrance_checks[entrance.name]

        if getattr(entrance, 'checking', False):
            return False

        entrance.checking = True
        try:
            can_reach = entrance.can_access_with_adapter(self)
            self.entrance_checks[entrance.name] = can_reach
            return can_reach
        except Exception as e:
            print(f"[DEBUG] Error checking entrance {entrance.name}: {e}")
            self.entrance_checks[entrance.name] = False
            return False
        finally:
            entrance.checking = False

    # ============================================================================
    # Item Check Methods
    # ============================================================================  
    
    def _has_item(self, item: str) -> bool:
        """Port of C# HasItem(string itemName)"""
        # 1. Handle progressive items (must check _collected_items counts)
        if "Whip" in item:
            level = {
                "Leather Whip": 1,
                "Chain Whip": 2,
                "Flail Whip": 3,
            }.get(item, 0)
            if "Progressive Whip" in self._collected_items:
                return self._collected_items["Progressive Whip"] >= level
            return False
        
        if item in ("Buckler", "Silver Shield", "Angel Shield"):
            level = {
                "Buckler": 1,
                "Silver Shield": 2,
                "Angel Shield": 3,
            }[item]
            if "Progressive Shield" in self._collected_items:
                return self._collected_items["Progressive Shield"] >= level
            return False
        
        # 2. Check for subweapon ammo variations
        if item.endswith("Ammo"):
            # Support both "Bomb Ammo" and "BombAmmo" spellings, but DO NOT fall back to base weapon.
            if item.endswith(" Ammo"):
                candidates = [item, item.replace(" Ammo", "Ammo")]
            else:
                candidates = [item, item.replace("Ammo", " Ammo")]

            for cand in candidates:
                if cand in self._collected_items:
                    return True
                # If you also want to allow direct AP-state lookup fallback:
                if self.state.has(cand, self.player):
                    return True

            return False
        
        # 3. Check local cache (includes Logic Flags, Dissonance, Bosses)
        if item in self._collected_items:
            return True
            
        # 4. Fallback to Archipelago state
        # This is critical for Assumed Fill where items are in state but maybe not fully synced to cache
        return self.state.has(item, self.player)
    
    # ------------------------------
    # Core rule evaluation entry
    # ------------------------------
    def evaluate_rule(self, name: str, args: List[str]) -> bool:
        """
        Dispatches logic rules to their Python implementations.
        
        Args:
            name: The rule function name (e.g., "Has", "CanReach", "GuardianKills")
            args: List of string arguments for the rule
            
        Returns:
            bool: Whether the rule condition is satisfied
        """
        
        # Item checks
        if name == "Has":
            return self._has_item(args[0])
        
        # Count-based checks
        elif name == "OrbCount":
            return self._orb_count(int(args[0]))
        elif name == "SkullCount":
            return self._skull_count(int(args[0]))
        elif name == "AnkhCount":
            return self._ankh_count_softlock() if self.softlock_check else self._ankh_count(int(args[0]))
        elif name == "GuardianKills":
            return self._guardian_kills(int(args[0]))
        elif name == "IsDead":
            return self._has_item(args[0])
        elif name == "CanKill":
            return self._can_kill(args[0])
        elif name == "CanChant":
            return self._can_chant(args[0])
        elif name == "CanUse":
            return self._can_use(args[0])
        elif name == "CanReach":
            return self._can_reach_by_name(args[0])
        elif name == "CanWarp":
            return self._can_warp()
        elif name == "CanStopTime":
            return self._can_stop_time()
        elif name == "CanSpinCorridor":
            return self._can_spin_corridor()
        elif name == "CanSealCorridor":
            return self._can_seal_corridor()
        elif name == "MeleeAttack":
            return self._melee_attack()
        elif name == "HorizontalAttack":
            return self._horizontal_attack()
        elif name == "Setting":
            return self._setting(args[0])
        elif name == "Start":
            return self._start(args[0])
        elif name == "Glitch":
            return self._glitch(args[0])
        elif name == "PuzzleFinished":
            return self._has_item(args[0])
        elif name == "Dissonance":
            return self._dissonance(int(args[0]) if args else 0)
        elif name == "True":
            return True
        elif name == "False":
            return False
        elif name == "HasMap":
            return True if self.options.remove_maps else self._has_item(args[0])
        elif name == "HasResearch":
            return True if self.options.remove_research else self._has_item(args[0])
        else:
            return False

    def _orb_count(self, count: int) -> bool:
        return self._collected_items.get("Sacred Orb", 0) >= count

    def _skull_count(self, count: int) -> bool:
        owned = self._collected_items.get("Crystal Skull", 0)
        if self.options.remove_excess_skulls:
            max_skulls = self.options.required_skulls.value if hasattr(self.options.required_skulls, "value") else self.options.required_skulls
            owned = min(owned, max_skulls)
        return owned >= count

    def _ankh_count(self, count: int) -> bool:
        return self._collected_items.get("Ankh Jewel", 0) >= count
    
    def _ankh_count_softlock(self) -> bool:
        return "Ankh Jewel" in self._collected_items

    def _guardian_kills(self, required: int) -> bool:
        return self._collected_items.get("Guardians", 0) >= required

    def _can_chant(self, mantra: str) -> bool:
        return self._has_item("Djed Pillar") and self._has_item("Mantra") and self._has_item(mantra)

    def _can_kill(self, boss: str) -> bool:
        boss_key = boss.replace(" ", "")
        try:
            location_id = LocationID[boss_key]
            world = self.multiworld.worlds[self.player]
            location = world.locations.get(location_id)
            if location:
                return location.can_collect_with_adapter(self)
        except (KeyError, AttributeError):
            pass
        return self._melee_attack() or self._horizontal_attack()

    def _can_use(self, item: str) -> bool:
        """Port of C# CanUse(string subWeapon)"""   
        # Check if this is the starting weapon
        if hasattr(self, 'starting_weapon'):
            starting_name = get_item_name_from_id(self.starting_weapon)
            if starting_name == item:
                # Starting with this weapon, we should have it
                # For subweapons, also need ammo check
                if item in ["Shuriken", "Rolling Shuriken", "Earth Spear", "Flare", 
                           "Caltrops", "Chakram", "Bomb", "Pistol"]:
                    return self._has_item(f"{item} Ammo")
                return True
    
        # Pistol special case
        if item == "Pistol":
            return (
                self._has_item("Pistol")
                and self._has_item("Pistol Ammo")
                and self._has_item("Money Fairy")
            )
    
        # Standard subweapon check
        return (
            self._has_item(item)
            and self._has_item(f"{item} Ammo")
        )

    def _can_warp(self) -> bool:
        if self.starting_area is None:
            import warnings
            warnings.warn("[LM2] _can_warp called with starting_area=None; FDC check skipped")
            return self._has_item("Holy Grail")

        # (player_state <- regions <- player_state)
        from ..regions import AREA_DEFS
        area_def = AREA_DEFS.get(self.starting_area)
        if area_def and area_def.is_backside:
            return (
                self._has_item("Holy Grail")
                and self._has_item("Future Development Company")
            )

        return self._has_item("Holy Grail")

    def _can_stop_time(self) -> bool:
        if not self._has_item("Lamp of Time"):
            return False
        return any(self._can_reach_by_name(area) for area in ["RoYBottom", "IBMain", "ITLeft", "DSLMMain"])

    def _can_spin_corridor(self) -> bool:
        return self._has_item("Progressive Beherit") and self._dissonance(1)

    def _can_seal_corridor(self) -> bool:
        if not self._dissonance(6):
            return False
        if not any(self._can_reach_by_name(area) for area in ["ValhallaMain", "DSLMTop", "SotFGBlood", "ACBlood", "HoM", "EPDEntrance"]):
            return False

        if self.options.random_dissonance:
            req = self.options.required_guardians
            if hasattr(req, "value"):
                req = req.value
            return self._guardian_kills(int(req))

        return self._has_item("Anu")

    def _melee_attack(self) -> bool:
        if hasattr(self, 'starting_weapon'):
            if self.starting_weapon in [ItemID.Whip1, ItemID.Knife, ItemID.Rapier, ItemID.Axe, ItemID.Katana]:
                return True
        return any(self._has_item(weapon) for weapon in ["Leather Whip", "Knife", "Rapier", "Axe", "Katana"])

    def _horizontal_attack(self) -> bool:
        if hasattr(self, 'starting_weapon'):
            if self.starting_weapon in [ItemID.Whip1, ItemID.Knife, ItemID.Rapier, ItemID.Axe, ItemID.Katana]:
                return True
            if self.starting_weapon in [ItemID.Shuriken, ItemID.RollingShuriken, ItemID.EarthSpear, ItemID.Flare, ItemID.Caltrops, ItemID.Chakram, ItemID.Bomb, ItemID.Pistol, ItemID.ClaydollSuit]:
                return True
        return (
            self._has_item("Leather Whip") or self._has_item("Knife") or 
            self._has_item("Rapier") or self._has_item("Axe") or self._has_item("Katana") or 
            self._can_use("Shuriken") or self._can_use("Rolling Shuriken") or 
            self._can_use("Earth Spear") or self._can_use("Caltrops") or 
            self._can_use("Chakram") or self._can_use("Bomb") or 
            self._can_use("Pistol") or self._has_item("Claydoll Suit")
        )

    def _glitch(self, glitch_name: str) -> bool:
        if glitch_name == "Costume Clip":
            return bool(self.options.costume_clip)
        return False

    def _dissonance(self, count: int) -> bool:
        # C# parity: prefer explicit Dissonance items if present,
        # otherwise fall back to Progressive Beherit (>= count+1).
        if self._collected_items.get("Dissonance", 0) >= count:
            return True
        return self._collected_items.get("Progressive Beherit", 0) >= (count + 1)

    def _setting(self, setting_name: str) -> bool:
        explicit_settings = {
            "AutoScan": lambda: self.options.auto_scan,
            "Random Ladders": lambda: self.options.vertical_entrances,
            "Non Random Ladders": lambda: not self.options.vertical_entrances,
            "Random Gates": lambda: self.options.gate_entrances,
            "Non Random Gates": lambda: not self.options.gate_entrances,
            "Random Soul Gates": lambda: self.options.random_soul_gate_value,
            "Non Random Soul Gates": lambda: not self.options.random_soul_gate_value,
            "Non Random Unique": lambda: not self.options.unique_transitions,
            "Remove IT Statue": lambda: self.options.remove_icefire_treetop_statue,
            "Not Life for HoM": lambda: not self.options.life_sigil_to_awaken_hom,
            "CostumeClip": lambda: self.options.costume_clip,
        }
        
        if setting_name in explicit_settings:
            return bool(explicit_settings[setting_name]())
        
        key = self.setting_overrides.get(setting_name, re.sub(r'(?<!^)(?=[A-Z])', '_', setting_name).lower())
        
        if not hasattr(self.options, key):
            return False
        
        option_value = getattr(self.options, key)
        
        if hasattr(option_value, 'value'):
            value = option_value.value
            if key == "logic_difficulty":
                return value == 1
            return bool(value)
        
        return bool(option_value)

    def _start(self, area: str) -> bool:
        """Port of C# Start(string startName)"""
        if not self.starting_area:
            return False
        
        normalized = re.sub(r'\s+', '', area)
        
        try:
            area_id = AreaID[normalized]
            return area_id == self.starting_area
        except KeyError:
            print(f"[LM2 LOGIC WARNING] Unknown Start area: {area}")
            return False