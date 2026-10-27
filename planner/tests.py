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

    def test_post_displays_production_plan(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {"target": "circuit", "rate": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Make circuit")
        self.assertContains(response, "Fuel requirements per second")
        self.assertContains(response, "Unreinvested additional outputs per second")

    def test_rejects_target_not_in_recipe_database(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {"target": "unknown material", "rate": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a material from the suggestions.")

    def test_rejects_non_positive_rate(self) -> None:
        response = self.client.post(
            reverse("planner:index"),
            {"target": "circuit", "rate": "0"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a finite rate greater than zero.")
