# ss13-chem-recipe-engine

**A chemistry simulator and recipe planner for Space Station 13, built for [Monkestation](https://github.com/Monkestation/Monkestation2.0) and designed to be modular for other tg-based servers.**
It reads the real chemistry rules out of the game's source code, simulates them (reaction order, BYOND rounding, foam and smoke scaling), and writes step-by-step recipes you can follow in-game.

## 📖 The recipe book

**[Open the recipe book](https://htmlpreview.github.io/?https://github.com/ClaudeProjectsTestAccount/ss13-chem-recipe-engine/blob/main/docs/index.html)** (one self-contained page, [`docs/index.html`](docs/index.html); you can also just download and open it). Everything starts collapsed:
pick a section (medborg chem nades, or plain chemistry recipes), a gear tier (nades: 100u / 300u beaker x 15u / 60u syringe; chemistry: 50u / 100u beaker), a recipe type and follow the numbered steps. The page includes the how-to-use guide.

Notes on how the chemistry behaves (foam vs smoke, edge cases, oddities): [`docs/CHEM_NOTES.md`](docs/CHEM_NOTES.md).

> **Status:** the reaction math is verified against the game code and a second, independent hand calculation. The recipes have **not yet been tested in-game**; the borg click-level details and what each effect does to a person are unverified (see [below](#what-is-verified-and-what-is-not)).

## Adding a recipe

Recipes live in [`data/recipe_book.json`](data/recipe_book.json); the page is generated from it and re-simulated every time, so it only ever shows numbers the engine produced. One command files a new recipe in the right tier and type and rewrites the page:

```
python3 src/chemcli.py publish --id lube-foam-300-60 --type slip --beaker 300 --syringe 60 --payload "space lube" --harm caution \
    --title "Lube foam" --what "..." --ops "dispense fluorine 30; dispense carbon 30; ...; inject"
python3 src/chemcli.py book list            # what is in the book
python3 src/chemcli.py book rm <id>
python3 src/chemcli.py book rebuild         # regenerate docs/index.html
```

`publish` refuses a recipe the engine cannot model, one that overflows the beaker, or one that makes a hazard for the borg (for example phlogiston without stabilizing agent). Types: `cleaning`, `slip`, `hell`, `med`, `walls`, `other`. A recipe is listed under every syringe it works with (a 10u draw works on both, a 15u draw only on the stock one).

## Plain chemicals (no nade): `chems` and `make`

The second section of the page is ordinary chemistry from the dispenser alone (libital, mutadone, oculine, ...). One command plans a chemical, runs the plan through the engine and files it:

```
python3 src/chemcli.py chems [--labelled]                         # every chemical the basic dispenser can make alone (95), with raw cost and heat
python3 src/chemcli.py make mutadone oculine --beaker 50,100      # plan only: prints the dispenser steps and yield
python3 src/chemcli.py make --beaker 50,100 --publish             # no names = every entry of data/chem_meta.json; files them and rewrites the page once
```

`src/chemplan.py` finds the cheapest instant-reaction route down to dispensable raws, tries every reaction size, rounds raws up to the dispenser's 5u clicks, simulates each candidate, nudges each raw by 5u, drops heater steps the simulation shows are unnecessary, and keeps the plan that yields the most product without overflow and whose result does not depend on click order. Labels (type, one-line tag, harm, caution) live in `data/chem_meta.json`; the description, overdose threshold and metabolism rate come from the game source. Chemicals that need a plasma catalyst, a cold recipe or another department are not buildable and say so.

## Ask the planner for a new recipe

```
python3 src/chemcli.py nade --trigger foam  --payload "space cleaner"
python3 src/chemcli.py nade --trigger smoke --payload "space lube" --mode lean
python3 src/chemcli.py nade --trigger foam  --payload "space cleaner" --beaker bluespace --syringe bluespace --trigger-units auto
python3 src/chemcli.py reaction "space cleaner"        # look a recipe up
python3 src/chemcli.py sim "dispense water 30; dispense silicon 15; dispense oxygen 15"   # simulate any step list
python3 src/chemcli.py sim "add blood 1; dispense radium 5; dispense phosphorus 5; dispense chlorine 5"   # 'add' = an ingredient from outside the dispenser
```

Python 3 only, no dependencies. Gear flags take a name or a volume: `--beaker large|xl|meta|bluespace|beaker|noreact|bottle|tube|<units>`, `--syringe standard|piercing|bluespace|<units>`, `--trigger-beaker <name|units>`, `--trigger-units N|auto`. The planner searches dispenser amounts exhaustively, simulates every candidate through the same reaction code, checks that the order of dispensing does not change the result (or flags it when it does), and prints the step list.

### Gear and upgrades
| Item | Volume |
| --- | --- |
| Beaker / large (borg stock) / x-large / metamaterial / bluespace | 50 / **100** / 120 / 180 / **300** u |
| Cryostasis beaker (nothing reacts inside) | 50 u |
| Syringe: stock / piercing upgrade / bluespace upgrade | **15** / 10 / **60** u |

The medborg beaker apparatus starts with a 100u beaker, and the beaker upgrade gives another 100u one; like the starting tool it takes any beaker, bottle or tube, so a 300u bluespace beaker can be swapped in. The book assumes a borg that has a size tier has **two beakers of that size** (no mixing sizes).

## Is a recipe broken? Check the rules first

If a recipe stops working, the most likely cause is a small recipe change in the game. **Run this before debugging anything else:**

```
python3 src/codecheck.py                  # compares the live source on GitHub with this repo's snapshot
python3 src/codecheck.py --ref <branch>   # the branch/tag your server really runs
python3 src/codecheck.py --update-snapshot   # accept the new rules after reviewing the diff
```

It does a shallow, sparse download of only the chemistry files (a few seconds, ~30 MB), re-parses every reaction, and prints each difference with the file, line number and a GitHub link. Changes that touch one of the verified recipes are marked, every recipe is re-run on the new rules, and the beaker/syringe sizes in the gear table are re-checked. If nothing changed, it says so and points you at the next suspects. `src/wikicheck.py` does the same against the wiki's tables where the wiki is reachable (optional; its table parser is still unconfirmed against live pages).

## Other servers

The chemistry rules are parsed from source, so pointing the tools at another tg-based codebase is mostly configuration:

```
python3 src/codecheck.py --repo https://github.com/tgstation/tgstation.git --update-snapshot
```

What is Monkestation-specific, and what to check on another server:
- **pH, purity and timed (equilibrium) reactions are not modelled.** Monkestation disables them; tg proper uses them, so recipes there will be wrong until that is added.
- Foam/smoke constants (`FOAM_SCALE`, minimum dilution, effect tick rates) live at the top of `src/chemlib.py` and `src/search.py`.
- The gear table (`BEAKER_TYPES`, `SYRINGE_TYPES` in `src/planner.py`) carries source references; `codecheck.py` re-checks it against whichever source you point it at.
- Dispenser lists are parsed from `chem_dispenser.dm`; forks that move that file get empty lists and need a path tweak.

## Roadmap

This is meant to grow into a general recipe generator: **bartender drinks**, and **non-borg chem mixes** that take advantage of everything a player controls - bigger and more containers, chem bags, bottles, the chem master. Today the book has the medborg nades and a plain-chemistry section (no upgrades). A **service borg** may also be able to use parts of it (it carries a beaker apparatus and a drink dispenser, but no syringe) - that needs verifying. Details and open questions: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What is verified and what is not

| Verified | Not verified |
| --- | --- |
| Reaction formulas, temperatures, dispenser lists, container sizes - parsed from the game source | Any of it in a live round |
| Reaction ordering, BYOND rounding quirks, nested reactions, foam/smoke scaling - 32 source-cited engine checks | The borg click flow (dispenser / apparatus / syringe handling) |
| Six recipes re-derived by hand independently (`src/verify_independent.py`) | Borg use of a chem heater; pouring one held beaker into another |
| Reagent maths of every recipe in the book (engine), their effects read from the code | Mob-spawn, vortex and wall effects are not simulated, only cited; that a dispenser click really stops at the free space is read from `chem_dispenser.dm`, not played |
| Rules diff against live source (`codecheck.py`) | Dispenser power-cell capacity (not modelled); "hellfoam" meaning |

## Tests

```
python3 -m unittest discover -s tests -v
```
`tests/legacy_checks.py` holds the original source-cited checks; new tests go in their own `tests/test_*.py` files (shared helpers in `tests/helpers.py`, including a tiny fake game tree for end-to-end tool tests).

## Layout
`src/dmparse.py` DM parser - `chemlib.py` reaction simulator - `planner.py` borg rig and `Gear` - `chemplan.py` plain-chemical planner (`data/chem_meta.json` holds its labels) - `search.py` design search - `chemcli.py` CLI - `book.py` recipe book and page builder (`page_template.html` is the page, `data/recipe_book.json` the recipes) - `codecheck.py` / `wikicheck.py` change detection - `recipes.py` hands the book to `codecheck.py` - `chemdata.json` rules snapshot (Monkestation2.0 commit recorded inside). See [`NOTICE.md`](NOTICE.md) for licensing (AGPL-3.0) and attribution.
