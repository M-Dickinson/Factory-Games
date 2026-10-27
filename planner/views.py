from pathlib import Path

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from factory_planner import (
    PlanningError,
    collect_additional_output_totals,
    collect_fuel_totals,
    format_plan,
    load_bases,
    load_recipes,
    plan_production,
)

from .forms import PlanRequestForm


RECIPE_DATABASE = Path(__file__).resolve().parent.parent / "recipes.json"


def index(request: HttpRequest) -> HttpResponse:
    recipes = load_recipes(RECIPE_DATABASE)
    bases = load_bases(RECIPE_DATABASE)
    materials = sorted(
        bases.union(*(recipe.outputs.keys() for recipe in recipes))
    )
    form = PlanRequestForm(
        request.POST if request.method == "POST" else None,
        materials=materials,
    )
    results: list[dict[str, object]] = []

    if request.method == "POST" and form.is_valid():
        try:
            plans = plan_production(
                form.cleaned_data["target"],
                form.cleaned_data["rate"],
                bases,
                recipes,
            )
            for index, plan in enumerate(plans, start=1):
                fuel_totals = collect_fuel_totals(plan)
                additional_outputs = collect_additional_output_totals(plan)
                results.append(
                    {
                        "title": (
                            f"Option {index} of {len(plans)}"
                            if len(plans) > 1
                            else "Production plan"
                        ),
                        "plan": format_plan(plan),
                        "fuel_totals": [
                            f"{fuel_type}: {quantity:.6g} {unit}/s"
                            for fuel_type, (unit, quantity) in sorted(
                                fuel_totals.items()
                            )
                        ],
                        "additional_outputs": [
                            f"{material}: {quantity:.6g}/s"
                            for material, quantity in sorted(
                                additional_outputs.items()
                            )
                        ],
                    }
                )
        except PlanningError as exc:
            form.add_error(None, str(exc))

    return render(
        request,
        "planner/index.html",
        {"form": form, "materials": materials, "results": results},
    )
