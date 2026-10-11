# Factory production planner

A dependency-free Python command-line tool that calculates production trees for
a requested material throughput. The included [recipes.json](recipes.json)
demonstrates the recipe database format.

## Run

```text
python factory_planner.py --target circuit --rate 2 --base "iron ore" "copper ore"
```

`--recipes` is an optional argument that can specify a separate JSON recipe
library (defaults to recipes.json)

`--target` is the requested output material. `--rate` is the requested output
quantity per second.

## Recipe database

The JSON file has a `recipes` array. Every recipe has a machine type,
processing time in seconds per crafting cycle, and positive input/output
quantities per cycle:

```json
{
  "recipes": [
    {
      "name": "Make gear",
      "machine": "Assembler",
      "seconds": 0.5,
      "inputs": { "iron plate": 2 },
      "outputs": { "gear": 1 }
    }
  ]
}
```

The JSON file can also have a `bases` array containing materials available
without requiring production. For a material that is both a base and a recipe
output, the planner shows the direct base option alongside every valid
machine-produced option.

```json
{
  "bases": [
    "copper ore",
    "iron ore",
    "coal",
    "stone"
  ]
}
```

If multiple recipes can produce the target or one of its required inputs, all
acyclic recipe combinations are displayed as separate options. Base materials
can be supplied directly, and matching recipes are also considered, including
recipes with no inputs (such as mining). Machine totals are rounded up to
whole machines; utilization is shown for the requested average throughput.
Additional outputs from a recipe are reported as byproducts, but are not
credited against requirements elsewhere in the tree.

Run the unit tests with:

```text
python -m unittest
```
