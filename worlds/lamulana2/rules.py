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
    # Player must have Ninth Child and be able to reach the Cliff area
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

    return state.has("Ninth Child", player)
