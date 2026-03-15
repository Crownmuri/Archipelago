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
    Check if the player can complete the game.

    "Ninth Child" is a code=None event item placed at the Ninth Child location.
    AP's sweep_for_advancements only auto-collects it when the location is
    reachable via the AP region graph (which already encodes ER connections and
    all location access rules including mantras, dissonances, items, and area
    reachability via soul gates). Therefore state.has("Ninth Child") is
    sufficient — it is True if and only if the player can reach and beat the
    final boss.
    """
    return state.has("Ninth Child", player)


def set_location_access_rule(world, location_name: str, rule_func):
    """
    Helper to set a custom access rule for a specific location.
    
    Args:
        world: The LM2 world
        location_name: Name of the location
        rule_func: Lambda function taking (state) and returning bool
    """
    location = world.multiworld.get_location(location_name, world.player)
    location.access_rule = rule_func


def set_entrance_access_rule(world, entrance_name: str, rule_func):
    """
    Helper to set a custom access rule for a specific entrance.
    
    Args:
        world: The LM2 world  
        entrance_name: Name of the entrance
        rule_func: Lambda function taking (state) and returning bool
    """
    entrance = world.multiworld.get_entrance(entrance_name, world.player)
    entrance.access_rule = rule_func