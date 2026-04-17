from .bases import LM2TestBase


class TestHorizontalEntrances(LM2TestBase):
    options = {
        "horizontal_entrances": True,
    }


class TestVerticalEntrances(LM2TestBase):
    options = {
        "vertical_entrances": True,
    }


class TestGateEntrances(LM2TestBase):
    options = {
        "gate_entrances": True,
    }


class TestAllEntranceTypes(LM2TestBase):
    options = {
        "horizontal_entrances": True,
        "vertical_entrances": True,
        "gate_entrances": True,
        "unique_transitions": True,
        "soul_gate_entrances": True,
    }


class TestFullRandomEntrances(LM2TestBase):
    options = {
        "full_random_entrances": True,
    }


class TestFullRandomWithLoopPrevention(LM2TestBase):
    options = {
        "full_random_entrances": True,
        "prevent_area_loops": True,
    }


class TestERWithNonDefaultOptions(LM2TestBase):
    """Test ER combined with options that might interact with entrance logic."""
    options = {
        "horizontal_entrances": True,
        "vertical_entrances": True,
        "gate_entrances": True,
        "random_grail": "shuffled",
        "random_fdc": "shuffled",
        "random_scanner": "shuffled",
        "guardian_specific_ankhs": True,
    }
