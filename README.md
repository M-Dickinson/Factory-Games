# Factory production planner

A minimal Django application that calculates production trees for a requested
material throughput. The app uses the included [recipes.json](recipes.json)
recipe database.

## Run the application

```text
python -m pip install -r requirements.txt
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Choose a target by typing into the searchable
material field, enter the desired rate in units per second, and select **Plan
production**. The page shows each valid production option, reinvested and
unreinvested additional outputs, and fuel requirements. The recipe database is
fixed to `recipes.json`; it cannot be switched from the page.

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
      "outputs": { "gear": 1 },
      "fuel": {
        "electricity": { "unit": "kW", "per_second": 90 }
      }
    }
  ]
}
```

The optional `fuel` object lists each abstract fuel or power type consumed by
the machine, with its unit and per-machine consumption rate. For example,
`"electricity": { "unit": "kW", "per_second": 90 }` means each machine
requires 90 kW. Omit `fuel` for machines with no fuel requirement. The plan
shows the per-machine fuel rate under each machine step and ends with the
combined per-second requirement for all machines in that tree. Totals use the
rounded-up machine counts displayed in the tree; a fuel type must use the same
unit wherever it appears in a plan.

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
Additional outputs from recipes are reinvested into matching material
requirements elsewhere in the same tree. Larger requirements are covered
first within each breadth-first frontier; a step is considered only after its
ancestors can no longer trim it. When a requirement is partly or fully supplied
by another step, its production and upstream input requirements are reduced
accordingly. Byproducts that cannot be reinvested are listed with the final
fuel requirements.

Run the Django and planner unit tests with:

```text
python manage.py test
python -m unittest
```
