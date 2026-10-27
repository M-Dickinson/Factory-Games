import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factory_planner_web.settings")

import django

django.setup()

from django.test import TestCase
from django.urls import reverse


class PlannerPageTests(TestCase):
    def test_page_lists_materials_in_searchable_input(self) -> None:
        response = self.client.get(reverse("planner:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'list="target-materials"')
        self.assertContains(response, '<option value="advanced circuit">')
        self.assertContains(response, '<option value="iron ore">')

    def test_upgrades_default_to_zero_percent(self) -> None:
        response = self.client.get(reverse("planner:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="0" selected>0% increase</option>')
        self.assertContains(
            response, '<option value="0" selected>0% reduction</option>'
        )

    def test_post_displays_production_plan(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {
                "target": "circuit",
                "rate": "2",
                "item_rate_upgrade": "1",
                "fuel_consumption_upgrade": "1",
                "active_tab": "standard",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Make circuit")
        self.assertContains(response, "Fuel requirements per second")
        self.assertContains(response, "Unreinvested additional outputs per second")

    def test_upgrades_preserve_target_rate_and_reduce_machines_and_fuel(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {
                "target": "iron plate",
                "rate": "2",
                "item_rate_upgrade": "0.25",
                "fuel_consumption_upgrade": "2",
                "active_tab": "upgrades",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "- iron plate: 2/s")
        self.assertContains(response, "6 x Stone furnace")
        self.assertContains(response, "combustables: 12 J/s")
        self.assertContains(
            response,
            "Fuel: combustables 2 J/s per machine (total: combustables 12 J/s)",
        )
        self.assertContains(response, 'aria-selected="true">')
        self.assertContains(response, "0% increase")
        self.assertContains(response, "200% reduction")

    def test_rejects_target_not_in_recipe_database(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {
                "target": "unknown material",
                "rate": "2",
                "item_rate_upgrade": "1",
                "fuel_consumption_upgrade": "1",
                "active_tab": "standard",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a material from the suggestions.")

    def test_rejects_non_positive_rate(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {
                "target": "circuit",
                "rate": "0",
                "item_rate_upgrade": "1",
                "fuel_consumption_upgrade": "1",
                "active_tab": "standard",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a finite rate greater than zero.")
