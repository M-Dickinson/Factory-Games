"""Plan machine and material requirements for a target production rate."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterator, Mapping, Sequence


class PlanningError(ValueError):
    """Raised when recipes cannot be loaded or a target cannot be planned."""


@dataclass(frozen=True)
class Recipe:
    name: str
    machine: str
    seconds: float
    inputs: Mapping[str, float]
    outputs: Mapping[str, float]


@dataclass(frozen=True)
class PlanNode:
    material: str
    rate: float
    recipe: Recipe | None = None
    cycles_per_second: float = 0.0
    machines: int = 0
    utilization: float = 0.0
    inputs: tuple[PlanNode, ...] = ()


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanningError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise PlanningError(f"{label} must be a finite number greater than zero")
    return number


def load_recipes(path: Path) -> list[Recipe]:
    """Load and validate a JSON recipe file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanningError(f"cannot read recipe database {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanningError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("recipes"), list):
        raise PlanningError("recipe database must contain a 'recipes' array")

    recipes: list[Recipe] = []
    names: set[str] = set()
    for index, item in enumerate(data["recipes"], start=1):
        label = f"recipe #{index}"
        if not isinstance(item, dict):
            raise PlanningError(f"{label} must be an object")
        name = item.get("name")
        machine = item.get("machine")
        if not isinstance(name, str) or not name.strip():
            raise PlanningError(f"{label} needs a non-empty name")
        if name in names:
            raise PlanningError(f"duplicate recipe name: {name}")
        names.add(name)
        if not isinstance(machine, str) or not machine.strip():
            raise PlanningError(f"{label} needs a non-empty machine name")
        seconds = _positive_number(item.get("seconds"), f"{label} seconds")

        parsed_flows: list[dict[str, float]] = []
        for field in ("inputs", "outputs"):
            flows = item.get(field)
            if not isinstance(flows, dict) or not flows:
                raise PlanningError(f"{label} '{field}' must be a non-empty object")
            parsed: dict[str, float] = {}
            for material, quantity in flows.items():
                if not isinstance(material, str) or not material.strip():
                    raise PlanningError(f"{label} has an invalid material in '{field}'")
                parsed[material] = _positive_number(
                    quantity, f"{label} {field} quantity for {material}"
                )
            parsed_flows.append(parsed)

        recipes.append(
            Recipe(name, machine, seconds, parsed_flows[0], parsed_flows[1])
        )
    return recipes


def plan_production(
    target: str,
    rate: float,
    base_materials: set[str],
    recipes: Sequence[Recipe],
) -> list[PlanNode]:
    """Return every acyclic recipe tree that can produce the requested rate."""
    if not target:
        raise PlanningError("target material must not be empty")
    rate = _positive_number(rate, "target rate")
    by_output: dict[str, list[Recipe]] = {}
    for recipe in recipes:
        for material in recipe.outputs:
            by_output.setdefault(material, []).append(recipe)

    def expand(material: str, required_rate: float, ancestors: frozenset[str]) -> Iterator[PlanNode]:
        if material in base_materials:
            yield PlanNode(material=material, rate=required_rate)
            return
        if material in ancestors:
            return

        candidates = by_output.get(material, [])
        if not candidates:
            return

        next_ancestors = ancestors | {material}
        for recipe in candidates:
            cycles_per_second = required_rate / recipe.outputs[material]
            child_options: list[list[PlanNode]] = []
            for input_material, quantity in recipe.inputs.items():
                options = list(
                    expand(
                        input_material,
                        quantity * cycles_per_second,
                        next_ancestors,
                    )
                )
                if not options:
                    break
                child_options.append(options)
            else:
                equivalents = cycles_per_second * recipe.seconds
                machine_count = max(1, math.ceil(equivalents - 1e-12))
                utilization = equivalents / machine_count
                for children in product(*child_options):
                    yield PlanNode(
                        material=material,
                        rate=required_rate,
                        recipe=recipe,
                        cycles_per_second=cycles_per_second,
                        machines=machine_count,
                        utilization=utilization,
                        inputs=tuple(children),
                    )

    plans = list(expand(target, rate, frozenset()))
    if not plans:
        raise PlanningError(
            f"no production tree can make '{target}' at {rate:g}/s "
            "from the selected base materials"
        )
    return plans


def _format_rate(rate: float) -> str:
    return f"{rate:.6g}"


def format_plan(node: PlanNode, indent: int = 0) -> str:
    """Format a plan tree as readable indented text."""
    prefix = " " * indent
    if node.recipe is None:
        return f"{prefix}- {node.material}: {_format_rate(node.rate)}/s (base material)"

    recipe = node.recipe
    lines = [
        f"{prefix}- {node.material}: {_format_rate(node.rate)}/s",
        f"{prefix}  {node.machines} x {recipe.machine} "
        f"({recipe.name}; {_format_rate(node.utilization * 100)}% utilization)",
    ]
    if len(recipe.outputs) > 1:
        byproducts = [
            f"{material} {_format_rate(quantity * node.cycles_per_second)}/s"
            for material, quantity in recipe.outputs.items()
            if material != node.material
        ]
        if byproducts:
            lines.append(f"{prefix}  Other outputs: {', '.join(byproducts)}")
    lines.append(f"{prefix}  Inputs:")
    lines.extend(format_plan(child, indent + 4) for child in node.inputs)
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate machine and input requirements for a target material."
    )
    parser.add_argument(
        "--recipes",
        type=Path,
        default=Path("recipes.json"),
        help="JSON recipe database (default: recipes.json)",
    )
    parser.add_argument("--target", required=True, help="target material name")
    parser.add_argument(
        "--rate",
        required=True,
        type=float,
        help="target production rate in units per second",
    )
    parser.add_argument(
        "--base",
        nargs="+",
        required=True,
        metavar="MATERIAL",
        help="materials available without production",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        recipes = load_recipes(args.recipes)
        plans = plan_production(args.target, args.rate, set(args.base), recipes)
    except PlanningError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    for index, plan in enumerate(plans, start=1):
        if len(plans) > 1:
            print(f"Option {index} of {len(plans)}:")
        print(format_plan(plan))
        if index < len(plans):
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
