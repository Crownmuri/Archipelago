from .ids import AreaID, DLC_AREA_IDS
from .regions import ExitType, LM2Entrance

# Areas that allow Holy Grail usage during escape, generally outside the ruins.
# Base list from the original randomizer (PlayerState.cs).
# The DLC areas except for Eden are also free-warp areas.
# (Spring in the Sky, Tower of Oannes, Bailey)
_ESCAPE_AREAS = (
    {AreaID.Cliff, AreaID.GateofGuidance, AreaID.MausoleumofGiants,
     AreaID.VoD, AreaID.VoDLadder, AreaID.GateofIllusion, AreaID.Nibiru}
    | (DLC_AREA_IDS - {AreaID.Eden})
)


def set_rules(world):
    """
    Set access rules for all locations and define completion condition.
    
    This is the KEY function that makes Archipelago understand LM2's logic.
    Each location's access_rule is a lambda that:
    1. Creates a PlayerStateAdapter from the AP state
    2. Evaluates the location's logic tree
    3. Checks area reachability
    """
    
    # Set access rules for all locations
    for location in world.multiworld.get_locations(world.player):
        if not hasattr(location, 'can_access'):
            # Skip non-LM2 locations (shouldn't happen, but defensive)
            continue
        
        # Use the location's existing can_access method as the access rule
        # The lambda captures 'location' to avoid late binding issues
        location.access_rule = lambda state, loc=location: loc.can_access(state)
    
    # Set the completion condition
    # Beat the Game: Ninth Child + Cliff reachable
    world.multiworld.completion_condition[world.player] = lambda state: (
        can_complete_game(state, world.player, world)
    )


def can_complete_game(state, player: int, world) -> bool:
    """
    Check if the player can complete the game, based on the resolved goal.

    - beat_the_game (default): reach and defeat the Ninth Child.
    - beat_the_dlc: reach and defeat Fish-Gear mk-2 turboR (Tower of Oannes).
    - glossary_hunt: collect `world.glossary_hunt_count` Glossary entries.

    "Ninth Child" and "Fish-Gear mk-2 turboR" are code=None event items placed
    at their boss locations. AP's sweep_for_advancements only auto-collects them
    when the location is reachable via the AP region graph (which already
    encodes ER connections and all location access rules including mantras,
    dissonances, items, and area reachability via soul gates). So state.has(...)
    is True if and only if the player can reach and beat that boss.

    For glossary_hunt, the enabled Glossary ROM items are made progression (see
    items.build_item_pool) and grouped as "Glossary", so has_group counts them.
    """
    from .options import Goal
    goal = getattr(world, "goal", Goal.option_beat_the_game)

    if goal == Goal.option_beat_the_dlc:
        return state.has("Fish-Gear mk-2 turboR", player)

    if goal == Goal.option_glossary_hunt:
        required = getattr(world, "glossary_hunt_count", 0)
        return state.has_group("Glossary", player, required)

    return (state.has("Ninth Child", player)
            and can_escape(state, player, world))


def can_escape(state, player: int, world) -> bool:
    """
    Port of the original randomizer's CanBeatGame + escape check
    (PlayerState.cs). Cliff must be reachable at all, and after the Ninth
    Child the player must get from Immortal Battlefield to one of the
    escape areas without using the Eternal Prison exits/gates. The Holy
    Grail is disabled until an escape area is reached, so CanWarp is False
    along the way.

    Approximation: CanReach(X) tokens inside exit rules still use normal
    reachability, where the original re-evaluated them from IBMain.
    """
    regions = getattr(world, "regions_by_area_id", None)
    if not regions:
        return True

    cliff = regions.get(AreaID.Cliff)
    if cliff is not None and not state.can_reach(cliff, "Region", player):
        return False

    escape_targets = {regions[a] for a in _ESCAPE_AREAS if a in regions}
    start = regions.get(AreaID.IBMain)
    if start is None or not escape_targets:
        return True

    adapter = None

    def escape_adapter():
        # Interpreted state with CanWarp switched off. Only built when an
        # exit on the route actually mentions CanWarp.
        nonlocal adapter
        if adapter is None:
            from .logic.player_state import PlayerStateAdapter
            adapter = PlayerStateAdapter(state, player, world.multiworld, world.options)
            adapter.starting_area = getattr(world, "starting_area", None)
            adapter.escape_check = True
        return adapter

    seen = {start}
    stack = [start]
    while stack:
        region = stack.pop()
        if region in escape_targets:
            return True
        for exit_ in region.exits:
            dest = exit_.connected_region
            if dest is None or dest in seen:
                continue
            if isinstance(exit_, LM2Entrance):
                if exit_.exit_type in (ExitType.PrisonExit, ExitType.PrisonGate):
                    continue
                # Skip the "parent reachable" precheck in can_access: during
                # the escape the player is physically in this region.
                if "CanWarp" in (exit_._original_logic or ""):
                    ok = exit_._logic_tree.evaluate(escape_adapter())
                else:
                    rule = exit_._compiled_rule
                    ok = rule(state) if rule is not None else exit_.access_rule(state)
            else:
                ok = exit_.access_rule(state)
            if ok:
                seen.add(dest)
                stack.append(dest)
    return False
