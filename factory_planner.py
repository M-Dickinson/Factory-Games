"""Plan machine and material requirements for a target production rate."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from collections.abc import Iterator, Mapping, Sequence


class PlanningError(ValueError):
    """Raised when recipes cannot be loaded or a target cannot be planned."""


@dataclass(frozen=True)
class FuelRequirement:
    unit: str
    per_second: float


@dataclass(frozen=True)
class Recipe:
    name: str
    machine: str
    seconds: float
    inputs: Mapping[str, float]
    outputs: Mapping[str, float]
    fuel: Mapping[str, FuelRequirement] | None = None


@dataclass(frozen=True)
class PlanNode:
    material: str
    rate: float
    recipe: Recipe | None = None
    cycles_per_second: float = 0.0
    machines: int = 0
    utilization: float = 0.0
    inputs: tuple[PlanNode, ...] = ()
    sourced_elsewhere: float = 0.0


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
    for index, item in enumerate(data["recipes"], start=1):
        label = f"recipe #{index}"
        if not isinstance(item, dict):
            raise PlanningError(f"{label} must be an object")
        name = item.get("name")
        machine = item.get("machine")
        if not isinstance(name, str) or not name.strip():
            raise PlanningError(f"{label} needs a non-empty name")
        if not isinstance(machine, str) or not machine.strip():
            raise PlanningError(f"{label} needs a non-empty machine name")
        seconds = _positive_number(item.get("seconds"), f"{label} seconds")

        parsed_flows: list[dict[str, float]] = []

        for field in ("inputs", "outputs"):
            flows = item.get(field)
            parsed: dict[str, float] = {}
            for material, quantity in flows.items():
                if not isinstance(material, str) or not material.strip():
                    raise PlanningError(f"{label} has an invalid material in '{field}'")
                parsed[material] = _positive_number(
                    quantity, f"{label} {field} quantity for {material}"
                )
            parsed_flows.append(parsed)

        fuel_data = item.get("fuel", {})
        if not isinstance(fuel_data, dict):
            raise PlanningError(f"{label} 'fuel' must be an object")
        fuel: dict[str, FuelRequirement] = {}
        for fuel_type, requirement in fuel_data.items():
            if not isinstance(fuel_type, str) or not fuel_type.strip():
                raise PlanningError(f"{label} has an invalid fuel type")
            if not isinstance(requirement, dict):
                raise PlanningError(
                    f"{label} fuel requirement for {fuel_type} must be an object"
                )
            unit = requirement.get("unit")
            if not isinstance(unit, str) or not unit.strip():
                raise PlanningError(
                    f"{label} fuel requirement for {fuel_type} needs a unit"
                )
            per_second = _positive_number(
                requirement.get("per_second"),
                f"{label} fuel rate for {fuel_type}",
            )
            fuel[fuel_type] = FuelRequirement(unit, per_second)

        recipes.append(
            Recipe(name, machine, seconds, parsed_flows[0], parsed_flows[1], fuel)
        )
    return recipes

def load_bases(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("bases"), list):
            raise PlanningError("recipe database must contain a 'bases' array")
    return set(data["bases"])

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
        if material in ancestors:
            return

        if material in base_materials:
            yield PlanNode(material=material, rate=required_rate)

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

    plans = [_reinvest_byproducts(plan) for plan in expand(target, rate, frozenset())]
    if not plans:
        raise PlanningError(
            f"no production tree can make '{target}' at {rate:g}/s "
            "from the selected base materials"
        )
    return plans


def _reinvest_byproducts(root: PlanNode) -> PlanNode:
    """Use stable recipe byproducts to reduce matching input production."""
    nodes: list[tuple[PlanNode, tuple[int, ...], int]] = []
    pending = deque([(root, (), 0)])
    while pending:
        node, path, depth = pending.popleft()
        nodes.append((node, path, depth))
        pending.extend(
            (child, path + (index,), depth + 1)
            for index, child in enumerate(node.inputs)
        )

    producers: list[tuple[tuple[int, ...], str, float]] = []
    available_materials: set[str] = set()
    for node, path, _ in nodes:
        if node.recipe is None:
            continue
        for material, quantity in node.recipe.outputs.items():
            if material != node.material:
                amount = quantity * node.cycles_per_second
                producers.append((path, material, amount))
                available_materials.add(material)

    if not producers:
        return root

    potential_sinks = [
        path
        for node, path, _ in nodes
        if path and node.material in available_materials
    ]

    def is_within_sink(path: tuple[int, ...]) -> bool:
        return any(path[: len(sink)] == sink for sink in potential_sinks)

    stock: dict[str, float] = {}
    for path, material, amount in producers:
        if not is_within_sink(path):
            stock[material] = stock.get(material, 0.0) + amount

    if not stock:
        return root

    nodes_by_path = {path: node for node, path, _ in nodes}
    sink_paths = set(potential_sinks)
    sink_frontiers = {
        path: sum(path[:index] in sink_paths for index in range(1, len(path)))
        for path in sink_paths
        if nodes_by_path[path].material in stock
    }

    allocations: dict[tuple[int, ...], float] = {}
    factors: dict[tuple[int, ...], float] = {
        path: 1.0 for _, path, _ in nodes
    }
    for frontier in range(max(sink_frontiers.values(), default=-1) + 1):
        by_material: dict[str, list[tuple[PlanNode, tuple[int, ...]]]] = {}
        for path, path_frontier in sink_frontiers.items():
            if path_frontier == frontier:
                node = nodes_by_path[path]
                by_material.setdefault(node.material, []).append((node, path))

        for material, sinks in by_material.items():
            sinks.sort(
                key=lambda entry: (
                    -(entry[0].rate * factors[entry[1]]),
                    entry[1],
                )
            )
            for node, path in sinks:
                required = node.rate * factors[path]
                amount = min(required, stock[material])
                if amount <= 0:
                    continue
                allocations[path] = amount
                stock[material] -= amount

        factors = {(): 1.0}
        for node, path, _ in nodes:
            factor = factors[path]
            required = node.rate * factor
            sourced = allocations.get(path, 0.0)
            remaining_factor = (required - sourced) / required if required else 0.0
            for index, _ in enumerate(node.inputs):
                factors[path + (index,)] = factor * remaining_factor

    if not allocations:
        return root

    def rebuild(
        node: PlanNode, path: tuple[int, ...], inherited_factor: float
    ) -> PlanNode:
        required = node.rate * inherited_factor
        sourced = allocations.get(path, 0.0)
        produced = max(0.0, required - sourced)
        if node.recipe is None:
            return PlanNode(
                material=node.material,
                rate=required,
                sourced_elsewhere=sourced,
            )

        cycles = produced / node.recipe.outputs[node.material]
        equivalents = cycles * node.recipe.seconds
        machines = max(1, math.ceil(equivalents - 1e-12)) if produced else 0
        utilization = equivalents / machines if machines else 0.0
        child_factor = inherited_factor * (produced / required) if required else 0.0
        children = (
            tuple(
                rebuild(child, path + (index,), child_factor)
                for index, child in enumerate(node.inputs)
            )
            if produced
            else ()
        )
        return PlanNode(
            material=node.material,
            rate=required,
            recipe=node.recipe,
            cycles_per_second=cycles,
            machines=machines,
            utilization=utilization,
            inputs=children,
            sourced_elsewhere=sourced,
        )

    return rebuild(root, (), 1.0)


def _format_rate(rate: float) -> str:
    return f"{rate:.6g}"


def collect_additional_output_totals(node: PlanNode) -> dict[str, float]:
    """Return additional recipe outputs left after reinvestment."""
    totals: dict[str, float] = {}
    sourced: dict[str, float] = {}

    def visit(current: PlanNode) -> None:
        if current.recipe is not None:
            for material, quantity in current.recipe.outputs.items():
                if material != current.material:
                    totals[material] = totals.get(material, 0.0) + (
                        quantity * current.cycles_per_second
                    )
        if current.sourced_elsewhere:
            sourced[current.material] = (
                sourced.get(current.material, 0.0) + current.sourced_elsewhere
            )
        for child in current.inputs:
            visit(child)

    visit(node)
    return {
        material: amount - sourced.get(material, 0.0)
        for material, amount in totals.items()
        if amount - sourced.get(material, 0.0) > 1e-12
    }


def collect_fuel_totals(node: PlanNode) -> dict[str, tuple[str, float]]:
    """Sum machine fuel-consumption rates across a production tree."""
    totals: dict[str, tuple[str, float]] = {}

    def add_node(current: PlanNode) -> None:
        if current.recipe is not None and current.machines and current.recipe.fuel:
            for fuel_type, requirement in current.recipe.fuel.items():
                existing = totals.get(fuel_type)
                if existing is not None and existing[0] != requirement.unit:
                    raise PlanningError(
                        f"fuel type '{fuel_type}' uses inconsistent units "
                        f"('{existing[0]}' and '{requirement.unit}')"
                    )
                totals[fuel_type] = (
                    requirement.unit,
                    (existing[1] if existing is not None else 0.0)
                    + current.machines * requirement.per_second,
                )
        for child in current.inputs:
            add_node(child)

    add_node(node)
    return totals


def format_plan(node: PlanNode, indent: int = 0) -> str:
    """Format a plan tree as readable indented text."""
    prefix = " " * indent
    if node.recipe is None:
        if node.sourced_elsewhere >= node.rate:
            return (
                f"{prefix}- {node.material}: {_format_rate(node.rate)}/s "
                "(sourced from elsewhere in the tree)"
            )
        label = "base material"
        if node.sourced_elsewhere:
            label += (
                f"; {_format_rate(node.sourced_elsewhere)}/s sourced "
                "from elsewhere in the tree"
            )
        return f"{prefix}- {node.material}: {_format_rate(node.rate)}/s ({label})"

    recipe = node.recipe
    lines = [
        f"{prefix}- {node.material}: {_format_rate(node.rate)}/s",
    ]
    if node.sourced_elsewhere:
        lines.append(
            f"{prefix}  {_format_rate(node.sourced_elsewhere)}/s sourced "
            "from elsewhere in the tree"
        )
    if node.machines:
        lines.append(
            f"{prefix}  {node.machines} x {recipe.machine} "
            f"({recipe.name}; {_format_rate(node.utilization * 100)}% utilization)"
        )
    if node.machines and recipe.fuel:
        fuel_rates = ", ".join(
            f"{fuel_type} {_format_rate(requirement.per_second)} "
            f"{requirement.unit}/s per machine"
            for fuel_type, requirement in sorted(recipe.fuel.items())
        )
        total_rates = ", ".join(
            f"{fuel_type} "
            f"{_format_rate(requirement.per_second * node.machines)} "
            f"{requirement.unit}/s"
            for fuel_type, requirement in sorted(recipe.fuel.items())
        )
        lines.append(f"{prefix}  Fuel: {fuel_rates} (total: {total_rates})")
    if node.machines and len(recipe.outputs) > 1:
        byproducts = [
            f"{material} {_format_rate(quantity * node.cycles_per_second)}/s"
            for material, quantity in recipe.outputs.items()
            if material != node.material
        ]
        if byproducts:
            lines.append(f"{prefix}  Additional outputs: {', '.join(byproducts)}")
    if node.machines:
        if node.inputs:
            lines.append(f"{prefix}  Inputs:")
            lines.extend(format_plan(child, indent + 4) for child in node.inputs)
        else:
            lines.append(f"{prefix}  Inputs: none")
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
    parser.add_argument(
        "--target", 
        required=True, 
        help="target material name"
    )
    parser.add_argument(
        "--rate",
        required=True,
        type=float,
        help="target production rate in units per second",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        recipes = load_recipes(args.recipes)
        bases = load_bases(args.recipes)
        plans = plan_production(args.target, args.rate, bases, recipes)
        fuel_totals = [collect_fuel_totals(plan) for plan in plans]
    except PlanningError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    for index, (plan, totals) in enumerate(zip(plans, fuel_totals), start=1):
        if len(plans) > 1:
            print(f"Option {index} of {len(plans)}:")
        print(format_plan(plan))
        print("Fuel requirements per second:")
        if totals:
            for fuel_type, (unit, quantity) in sorted(totals.items()):
                print(f"  {fuel_type}: {_format_rate(quantity)} {unit}")
        else:
            print("  none")
        additional_outputs = collect_additional_output_totals(plan)
        print("Unreinvested additional outputs per second:")
        if additional_outputs:
            for material, quantity in sorted(additional_outputs.items()):
                print(f"  {material}: {_format_rate(quantity)}")
        else:
            print("  none")
        if index < len(plans):
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
