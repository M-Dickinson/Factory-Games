import json
import tempfile
import unittest
from pathlib import Path

from factory_planner import PlanningError, Recipe, load_recipes, plan_production


class PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recipes = [
            Recipe("plate", "Furnace", 2, {"ore": 1}, {"plate": 1}),
            Recipe("gear", "Assembler", 3, {"plate": 2}, {"gear": 1}),
            Recipe("alloy", "Foundry", 4, {"ore": 1}, {"plate": 2, "slag": 1}),
            Recipe("alternate gear", "Assembler", 1, {"ore": 3}, {"gear": 2}),
        ]

    def test_tree_rates_scale_through_recipes_and_base_inputs(self) -> None:
        [plan] = plan_production("gear", 2, {"ore"}, self.recipes[:2])
        self.assertEqual(plan.machines, 6)
        self.assertAlmostEqual(plan.utilization, 1)
        self.assertEqual(plan.inputs[0].material, "plate")
        self.assertEqual(plan.inputs[0].rate, 4)
        self.assertEqual(plan.inputs[0].inputs[0].material, "ore")
        self.assertEqual(plan.inputs[0].inputs[0].rate, 4)

    def test_lists_alternatives_for_target_recipe(self) -> None:
        plans = plan_production(
            "gear", 2, {"ore"}, self.recipes[:2] + self.recipes[3:]
        )
        self.assertEqual([plan.recipe.name for plan in plans], ["gear", "alternate gear"])
        self.assertEqual([plan.inputs[0].rate for plan in plans], [4, 3])

    def test_can_use_any_output_of_a_multi_output_recipe(self) -> None:
        [plan] = plan_production("plate", 3, {"ore"}, [self.recipes[2]])
        self.assertEqual(plan.inputs[0].rate, 1.5)

    def test_skips_cycles_and_unavailable_branches(self) -> None:
        recipes = [
            Recipe("cycle", "Assembler", 1, {"gear": 1}, {"gear": 1}),
            *self.recipes[:2],
        ]
        [plan] = plan_production("gear", 1, {"ore"}, recipes)
        self.assertEqual(plan.recipe.name, "gear")

    def test_unreachable_target_raises(self) -> None:
        with self.assertRaises(PlanningError):
            plan_production("gear", 1, {"copper ore"}, self.recipes[:2])

    def test_rejects_non_positive_rate(self) -> None:
        with self.assertRaisesRegex(PlanningError, "target rate"):
            plan_production("gear", 0, {"ore"}, self.recipes)

    def test_loads_json_database(self) -> None:
        contents = {"recipes": [{
            "name": "Make plate",
            "machine": "Furnace",
            "seconds": 2,
            "inputs": {"ore": 1},
            "outputs": {"plate": 1},
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipes.json"
            path.write_text(json.dumps(contents), encoding="utf-8")
            self.assertEqual(load_recipes(path)[0].name, "Make plate")

    def test_accepts_machine_recipe_with_no_inputs(self) -> None:
        contents = {"recipes": [{
            "name": "Mine ore",
            "machine": "Burner drill",
            "seconds": 2.8,
            "inputs": {},
            "outputs": {"ore": 1},
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipes.json"
            path.write_text(json.dumps(contents), encoding="utf-8")
            recipes = load_recipes(path)

        plans = plan_production("ore", 1, {"ore"}, recipes)
        self.assertEqual(len(plans), 2)
        self.assertIsNone(plans[0].recipe)
        self.assertEqual(plans[1].recipe.name, "Mine ore")
        self.assertEqual(plans[1].machines, 3)
        self.assertEqual(plans[1].inputs, ())


if __name__ == "__main__":
    unittest.main()
