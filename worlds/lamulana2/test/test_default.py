from .bases import LM2TestBase


class TestDefaultOptions(LM2TestBase):
    """Runs the built-in WorldTestBase tests with default options.

    Covers:
    - test_all_state_can_reach_everything: all items collected -> all locations reachable
    - test_empty_state_can_reach_something: no items -> at least something reachable
    - test_fill: a valid multiworld can be generated and filled
    """
    pass
