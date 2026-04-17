"""
Multi-seed stress tests for La-Mulana 2 world generation.

These tests are SKIPPED by default to avoid slowing down CI.
Run them explicitly with:
    LM2_STRESS=1 python -m pytest worlds/lamulana2/test/test_stress.py -v

Or run a specific seed count:
    LM2_STRESS=50 python -m pytest worlds/lamulana2/test/test_stress.py -v
"""
import os
import unittest

from .bases import LM2TestBase

STRESS = os.environ.get("LM2_STRESS", "")
SEED_COUNT = int(STRESS) if STRESS.isdigit() else 20
SKIP_REASON = "Set LM2_STRESS=1 (or =N for N seeds) to run stress tests"


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestDefault(LM2TestBase):
    """Stress-test default options across many seeds."""
    run_default_tests = False

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestHorizontalER(LM2TestBase):
    run_default_tests = False
    options = {
        "horizontal_entrances": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestVerticalER(LM2TestBase):
    run_default_tests = False
    options = {
        "vertical_entrances": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestGateER(LM2TestBase):
    run_default_tests = False
    options = {
        "gate_entrances": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestAllER(LM2TestBase):
    """All entrance types enabled — most likely to fail."""
    run_default_tests = False
    options = {
        "horizontal_entrances": True,
        "vertical_entrances": True,
        "gate_entrances": True,
        "unique_transitions": True,
        "soul_gate_entrances": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestFullRandomER(LM2TestBase):
    run_default_tests = False
    options = {
        "full_random_entrances": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestFullRandomLoopPrevention(LM2TestBase):
    run_default_tests = False
    options = {
        "full_random_entrances": True,
        "prevent_area_loops": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")


@unittest.skipUnless(STRESS, SKIP_REASON)
class StressTestERKitchenSink(LM2TestBase):
    """ER + most randomization options — maximum chaos."""
    run_default_tests = False
    options = {
        "horizontal_entrances": True,
        "vertical_entrances": True,
        "gate_entrances": True,
        "unique_transitions": True,
        "soul_gate_entrances": True,
        "full_random_entrances": True,
        "prevent_area_loops": True,
        "random_grail": "shuffled",
        "random_fdc": "shuffled",
        "random_scanner": "shuffled",
        "random_codices": "shuffled",
        "random_ring": "shuffled",
        "random_shell_horn": "shuffled",
        "guardian_specific_ankhs": True,
        "mantra_placement": "shuffled",
        "random_dissonance": True,
        "random_cursed_chests": True,
    }

    def test_multi_seed_fill(self) -> None:
        failures = []
        for seed in range(SEED_COUNT):
            with self.subTest(seed=seed):
                try:
                    self.world_setup(seed)
                except Exception as e:
                    failures.append((seed, str(e)))
        if failures:
            msg = "\n".join(f"  seed {s}: {err}" for s, err in failures)
            self.fail(f"{len(failures)}/{SEED_COUNT} seeds failed generation:\n{msg}")
