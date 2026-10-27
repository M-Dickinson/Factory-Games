import json
import tempfile
import unittest
from pathlib import Path

from factory_planner import (
    FuelRequirement,
    PlanningError,
    Recipe,
    collect_additional_output_totals,
    collect_fuel_totals,
    format_plan,
    load_recipes,
    plan_production,
)


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

    def test_fuel_totals_sum_machine_rates_across_tree(self) -> None:
        recipes = [
            Recipe(
                "plate",
                "Furnace",
                2,
                {"ore": 1},
                {"plate": 1},
                {"electricity": FuelRequirement("kW", 5)},
            ),
            Recipe(
                "gear",
                "Assembler",
                3,
                {"plate": 2},
                {"gear": 1},
                {"steam": FuelRequirement("kg", 0.5)},
            ),
        ]
        [plan] = plan_production("gear", 2, {"ore"}, recipes)

        self.assertEqual(
            collect_fuel_totals(plan),
            {"electricity": ("kW", 40), "steam": ("kg", 3)},
        )

    def test_plan_shows_fuel_rate_under_each_machine_step(self) -> None:
        recipe = Recipe(
            "plate",
            "Furnace",
            2,
            {"ore": 1},
            {"plate": 1},
            {
                "electricity": FuelRequirement("kW", 5),
                "steam": FuelRequirement("kg", 0.25),
            },
        )
        [plan] = plan_production("plate", 3, {"ore"}, [recipe])

        rendered = format_plan(plan)

        self.assertIn("Fuel: electricity 5 kW/s per machine, steam 0.25 kg/s per machine", rendered)
        self.assertIn("(total: electricity 30 kW/s, steam 1.5 kg/s)", rendered)

    def test_rejects_inconsistent_fuel_units(self) -> None:
        recipes = [
            Recipe(
                "plate",
                "Furnace",
                2,
                {"ore": 1},
                {"plate": 1},
                {"electricity": FuelRequirement("kW", 1)},
            ),
            Recipe(
                "gear",
                "Assembler",
                3,
                {"plate": 2},
                {"gear": 1},
                {"electricity": FuelRequirement("MW", 1)},
            ),
        ]
        [plan] = plan_production("gear", 1, {"ore"}, recipes)
        with self.assertRaisesRegex(PlanningError, "inconsistent units"):
            collect_fuel_totals(plan)

    def test_lists_alternatives_for_target_recipe(self) -> None:
        plans = plan_production(
            "gear", 2, {"ore"}, self.recipes[:2] + self.recipes[3:]
        )
        self.assertEqual([plan.recipe.name for plan in plans], ["gear", "alternate gear"])
        self.assertEqual([plan.inputs[0].rate for plan in plans], [4, 3])

    def test_can_use_any_output_of_a_multi_output_recipe(self) -> None:
        [plan] = plan_production("plate", 3, {"ore"}, [self.recipes[2]])
        self.assertEqual(plan.inputs[0].rate, 1.5)

    def test_reinvests_byproducts_into_matching_base_material_demands(self) -> None:
        recipes = [
            Recipe(
                "assemble gear",
                "Assembler",
                1,
                {"widget": 1, "ore": 3},
                {"gear": 1},
            ),
            Recipe(
                "make widget",
                "Assembler",
                1,
                {"coal": 1},
                {"widget": 1, "ore": 5},
            ),
        ]
        plans = plan_production("gear", 1, {"coal", "ore"}, recipes)
        plan = next(plan for plan in plans if plan.inputs[1].recipe is None)

        ore = plan.inputs[1]
        self.assertEqual(ore.sourced_elsewhere, 3)
        self.assertEqual(collect_additional_output_totals(plan), {"ore": 2})
        self.assertIn("sourced from elsewhere in the tree", format_plan(plan))

    def test_reinvests_into_largest_matching_demand_first(self) -> None:
        recipes = [
            Recipe(
                "make product",
                "Assembler",
                1,
                {"large part": 1, "small part": 1, "surplus": 1},
                {"product": 1},
            ),
            Recipe("make large part", "Assembler", 1, {"ore": 4}, {"large part": 1}),
            Recipe("make small part", "Assembler", 1, {"ore": 2}, {"small part": 1}),
            Recipe(
                "make surplus",
                "Assembler",
                1,
                {},
                {"surplus": 1, "ore": 4},
            ),
        ]
        plans = plan_production("product", 1, {"ore"}, recipes)
        plan = next(
            plan
            for plan in plans
            if plan.inputs[0].inputs[0].recipe is None
            and plan.inputs[1].inputs[0].recipe is None
        )

        large_ore = plan.inputs[0].inputs[0]
        small_ore = plan.inputs[1].inputs[0]
        self.assertEqual(large_ore.sourced_elsewhere, 4)
        self.assertEqual(small_ore.sourced_elsewhere, 0)

    def test_prioritizes_largest_demand_across_breadth_levels(self) -> None:
        recipes = [
            Recipe(
                "make product",
                "Assembler",
                1,
                {"deep part": 1, "ore": 1, "surplus": 1},
                {"product": 1},
            ),
            Recipe("make deep part", "Assembler", 1, {"component": 1}, {"deep part": 1}),
            Recipe("make component", "Assembler", 1, {"ore": 4}, {"component": 1}),
            Recipe(
                "make surplus",
                "Assembler",
                1,
                {},
                {"surplus": 1, "ore": 4},
            ),
        ]
        plans = plan_production("product", 1, {"ore"}, recipes)
        plan = next(
            plan
            for plan in plans
            if plan.inputs[1].recipe is None
            and plan.inputs[0].inputs[0].inputs[0].recipe is None
        )

        deep_ore = plan.inputs[0].inputs[0].inputs[0]
        shallow_ore = plan.inputs[1]
        self.assertEqual(deep_ore.sourced_elsewhere, 4)
        self.assertEqual(shallow_ore.sourced_elsewhere, 0)

    def test_reinvestment_trims_the_sourced_step_and_its_inputs(self) -> None:
        recipes = [
            Recipe(
                "make product",
                "Assembler",
                1,
                {"part": 1, "intermediate": 2},
                {"product": 1},
            ),
            Recipe(
                "make part",
                "Assembler",
                1,
                {"stone": 2},
                {"part": 1, "intermediate": 1.5},
            ),
            Recipe(
                "make intermediate",
                "Assembler",
                1,
                {"ore": 4},
                {"intermediate": 1},
            ),
        ]
        plans = plan_production("product", 1, {"stone", "ore"}, recipes)
        plan = next(
            plan for plan in plans if plan.inputs[1].recipe.name == "make intermediate"
        )

        intermediate = plan.inputs[1]
        self.assertEqual(intermediate.sourced_elsewhere, 1.5)
        self.assertEqual(intermediate.inputs[0].rate, 2)

    def test_excess_byproduct_removes_fully_sourced_step_and_leaves_surplus(self) -> None:
        recipes = [
            Recipe(
                "make product",
                "Assembler",
                1,
                {"part": 1, "intermediate": 2},
                {"product": 1},
            ),
            Recipe(
                "make part",
                "Assembler",
                1,
                {"stone": 2},
                {"part": 1, "intermediate": 3},
            ),
            Recipe(
                "make intermediate",
                "Assembler",
                1,
                {"ore": 4},
                {"intermediate": 1},
                {"electricity": FuelRequirement("kW", 5)},
            ),
        ]
        plans = plan_production("product", 1, {"stone", "ore"}, recipes)
        plan = next(
            plan for plan in plans if plan.inputs[1].recipe.name == "make intermediate"
        )

        intermediate = plan.inputs[1]
        self.assertEqual(intermediate.sourced_elsewhere, 2)
        self.assertEqual(intermediate.machines, 0)
        self.assertEqual(intermediate.inputs, ())
        self.assertEqual(collect_fuel_totals(plan), {})
        self.assertEqual(collect_additional_output_totals(plan), {"intermediate": 1})

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
            "fuel": {
                "electricity": {"unit": "kW", "per_second": 4}
            },
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipes.json"
            path.write_text(json.dumps(contents), encoding="utf-8")
            recipe = load_recipes(path)[0]
            self.assertEqual(recipe.name, "Make plate")
            self.assertEqual(
                recipe.fuel,
                {"electricity": FuelRequirement("kW", 4)},
            )

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
