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


class TestRequireFDCWithER(LM2TestBase):
    """
    Oannesanity + shuffled DLC/unique transitions + RequireFDC.

    Exercises fix_fdc_logic_post_er: both RequireFDC gates describe the area you
    ARRIVE in, so they have to land on the exits that actually reach a backside
    area / a Tower of Oannes checkpoint room once ER has moved the doors, not on
    whatever led there in an unshuffled seed.
    """
    options = {
        "oannesanity": True,
        "include_dlc_entrances": True,
        "unique_transitions": True,
        "gate_entrances": True,
        "require_fdc": True,
    }

    def _live_exits(self):
        for exit_ in self.multiworld.get_entrances(self.player):
            logic = getattr(exit_, "_original_logic", None)
            dest = exit_.connected_region
            if logic is None or dest is None:
                continue
            yield exit_, logic, dest, exit_.destination_area

    def test_checkpoint_gate_follows_live_destination(self):
        from ..randomizer import LM2RandomizerCore

        checkpoints = LM2RandomizerCore.OANNES_CHECKPOINT_AREAS
        gate = "Totem Pole"

        for exit_, logic, dest, dest_area in self._live_exits():
            expected = dest_area in checkpoints
            with self.subTest(exit=exit_.name):
                self.assertEqual(
                    expected, gate in logic,
                    f"{exit_.name} -> {dest.name}: gate present={gate in logic}, "
                    f"expected={expected}",
                )

    def test_backside_gate_follows_live_destination(self):
        """C# FixFDCLogic: non-internal exits into a backside area need FDC."""
        from ..regions import AREA_DEFS, ExitType
        from ..randomizer import LM2RandomizerCore

        checkpoints = LM2RandomizerCore.OANNES_CHECKPOINT_AREAS
        gate = "Future Development Company"

        # A couple of World.json exits name FDC in their own logic (the EPG
        # internal exit routes through a backside warp). Those are not stamps,
        # so exempt them rather than counting them as one. Exit names are
        # globally unique, so the name alone identifies the definition.
        native = {
            ed.name
            for area_def in AREA_DEFS.values()
            for ed in area_def.exits
            if any(gate in (s or "")
                   for s in (ed.logic, ed.tricky_logic, ed.minimal_logic))
        }

        for exit_, logic, dest, dest_area in self._live_exits():
            if exit_.name in native:
                continue
            area_def = AREA_DEFS.get(dest_area)
            expected = (
                exit_.exit_type != ExitType.Internal
                and area_def is not None
                and area_def.is_backside
            ) or dest_area in checkpoints
            with self.subTest(exit=exit_.name):
                self.assertEqual(
                    expected, gate in logic,
                    f"{exit_.name} -> {dest.name}: gate present={gate in logic}, "
                    f"expected={expected}",
                )
