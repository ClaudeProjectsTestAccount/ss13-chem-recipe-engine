"""recipes.py - the recipe book as seen by the tools that re-run every recipe (codecheck.py).

The recipes themselves live in data/recipe_book.json (see book.py); add one with `chemcli.py publish`.
"""
import book

def all_recipes():
    """every recipe as (id, title, ops, gear kwargs for planner.Gear)"""
    out = []
    for r in book.load_book():
        g = book.gear_of(r)
        out.append((r['id'], r['title'], [tuple(o) for o in r['ops']], dict(beaker=g.bname, syringe=g.sname)))
    return out
