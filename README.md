# Factory production planner

A dependency-free Python command-line tool that calculates production trees for
a requested material throughput. The included [recipes.json](recipes.json)
demonstrates the recipe database format.

## Run

```text
python factory_planner.py --recipes recipes.json --target circuit --rate 2 --base "iron ore" "copper ore"
```

`--rate` is the requested output quantity per second. Each name after `--base`
is treated as an unlimited raw material and does not require a recipe.

## Recipe database

The JSON file has a top-level `recipes` array. Every recipe has a unique name,
a machine type, processing time in seconds per crafting cycle, and positive
input/output quantities per cycle:

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

If multiple recipes can produce the target or one of its required inputs, all
acyclic recipe combinations are displayed as separate options. Base materials
are always supplied directly. Machine totals are rounded up to whole machines;
utilization is shown for the requested average throughput. Additional outputs
from a recipe are reported as byproducts, but are not credited against
requirements elsewhere in the tree.

Run the unit tests with:

```text
python -m unittest
```
