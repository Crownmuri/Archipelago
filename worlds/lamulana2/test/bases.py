from test.bases import WorldTestBase
from BaseClasses import CollectionState


class LM2TestBase(WorldTestBase):
    game = "La-Mulana 2"

    def test_all_state_can_reach_everything(self):
        """
        Override: use sphere-sweep instead of get_all_state(False).

        AP's default get_all_state collects pool items without sweeping,
        then runs one sweep.  This fails for LM2 ER because region access
        rules depend on event items (boss kills, shortcuts) that are only
        collected as their locations become reachable.  get_all_state's
        BFS can't bootstrap these events because it runs with no events
        in the state.

        A sphere-sweep (collect pool items via state.collect, which
        triggers progressive event collection) mirrors the actual fill
        behavior and correctly resolves event-region dependencies.
        """
        if not (self.run_default_tests and self.constructed):
            return
        with self.subTest("Game", game=self.game, seed=self.multiworld.seed):
            state = CollectionState(self.multiworld)
            player = self.player

            # Collect all pool items (triggers sweeps that collect events)
            for item in self.multiworld.itempool:
                if item.player == player:
                    state.collect(item)

            # Verify all locations reachable
            for location in self.multiworld.get_locations():
                if location.player != player:
                    continue
                with self.subTest("Location should be reached", location=location.name):
                    self.assertTrue(location.can_reach(state),
                                    f"{location.name} unreachable")
            with self.subTest("Beatable"):
                self.multiworld.state = state
                self.assertBeatable(True)
