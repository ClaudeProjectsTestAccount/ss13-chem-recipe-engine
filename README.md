# ss13-chem-recipe-engine

**A chemistry simulator and recipe planner for Space Station 13, built for [Monkestation](https://github.com/Monkestation/Monkestation2.0) and designed to be modular for other tg-based servers.**
It reads the real chemistry rules out of the game's source code, simulates them exactly (reaction order, BYOND rounding, foam and smoke scaling), and writes step-by-step recipes you can follow in-game.

Right now it does one job: **give medical (and science) cyborgs "syringe into beaker" foam/smoke grenade recipes** - cleaner foam, lube foam, lube smoke, acid foam - and a second batch of **unusual reactions** (metal-foam walls, carpet foam, healing fog, vortex shockwaves...). The engine is written to grow well beyond that (see [Roadmap](#roadmap)).

**Already calculated recipes (tested in the simulator):**
- Original five: [cleaner foam](docs/RECIPES.md#cleaner-foam-30-tiles) · [cleaner smoke](docs/RECIPES.md#cleaner-smoke-45-tiles) · [lube foam](docs/RECIPES.md#lube-foam-30-tiles) · [lube smoke](docs/RECIPES.md#lube-smoke-45-tiles) · [hellfoam](docs/RECIPES.md#hellfoam---fluorosulfuric-acid-foam-30-tiles)
- **New reactions:** [metal foam](docs/RECIPES.md#metal-foam---instant-walls-100-tiles) · [metal foam XL](docs/RECIPES.md#metal-foam-xl---200-tiles-bluespace-beaker) · [iron foam](docs/RECIPES.md#iron-foam---reinforced-walls-100-tiles) · [smart foam](docs/RECIPES.md#smart-foam---seals-area-borders-only-100-tiles-bluespace-beaker) · [drying foam](docs/RECIPES.md#drying-foam---removes-lube-and-wet-floors-30-tiles) · [carpet foam](docs/RECIPES.md#carpet-foam---redecorates-the-floor-30-tiles) · [black carpet foam](docs/RECIPES.md#black-carpet-foam-30-tiles) · [carpet foam XL](docs/RECIPES.md#carpet-foam-xl---120-tiles-bluespace-beaker--bluespace-syringe) · [brute-mender fog](docs/RECIPES.md#brute-mender-fog-libital-smoke-45-tiles) · [burn-mender fog](docs/RECIPES.md#burn-mender-fog-aiuri-smoke-45-tiles) · [sorium shockwave](docs/RECIPES.md#sorium-shockwave---throws-everything-away-from-you-range-6) · [dark matter pull](docs/RECIPES.md#dark-matter-pull---drags-everything-toward-you-range-6) · [friendly life](docs/RECIPES.md#friendly-life-bluespace-beaker-donated-ingredients)

> **Status:** the reaction math is verified against the game code and a second, independent hand calculation. The recipes have **not yet been tested in-game**, and a few borg click-level details are unverified (listed [below](#what-is-verified-and-what-is-not)).

---

## Use the recipes as a medborg (no coding needed)

**All the ready-made recipes are in [`docs/RECIPES.md`](docs/RECIPES.md)** - open it, pick one, follow the numbered steps.

### The idea
You carry two things: a **syringe** (holds 15u) and a **beaker** (100u). You

1. make a **15u trigger** chemical and move it into the syringe,
2. build the **payload** chemical (85u or less) in the beaker,
3. **inject the whole syringe into the beaker at once.** The trigger reacts with the payload, and the beaker's contents burst out as foam or smoke that carries the payload over many tiles.

Foam trigger = fluorosurfactant (the payload rides in a foam that is slippery on its own). Smoke trigger = phosphorus (with potassium and sugar sitting in the beaker).

### What you need
- A Medical or Science cyborg with the stock **syringe** and **beaker storage apparatus** (the apparatus carries a 100u large beaker).
- A **chem dispenser** (Chemistry / Medbay). The recipes assume the basic dispenser reagent list.
- Hellfoam only: a **chem heater** (the beaker has to reach 380K+).
- Optional upgrades change the numbers (see [Gear](#gear-and-upgrades)): bluespace syringe (60u), a second beaker, bigger beakers.

### Worked example - cleaner foam (30 tiles)
Taken from [`docs/RECIPES.md`](docs/RECIPES.md):

1. Dispenser: 10u fluorine, 10u carbon, 5u sulfuric acid. The beaker now holds 25u fluorosurfactant.
2. Syringe: draw 15u from the beaker. Spill the remaining 10u.
3. Dispenser: 30u hydrogen, then 10u nitrogen (they become ammonia).
4. Dispenser: 45u water (a 30u click, then a 15u click). The beaker now holds 60u space cleaner and 15u water.
5. Set the syringe transfer amount to 15 and **inject it all into the beaker.** 30 tiles of foam, each carrying 192u of space cleaner.

Stand clear afterwards: foam is slippery and knocks people down. Smoke recipes are **order sensitive** (potassium reacts violently with water), so follow the listed order exactly - the guide tells you which recipes care.

### The likely click flow (unverified in-game)
The planner tells you *what* to put where. The exact button presses below come from reading the code, not from playing:

- **Dispenser clicks:** the dispenser UI offers 5 / 10 / 15 / 20 / 25 / 30 / 50 / 100 unit buttons. A step like "45u water (a 30u click, then a 15u click)" means exactly that.
- **Beaker in and out of the dispenser:** use the beaker apparatus on the dispenser to load it; the apparatus passes clicks through to the beaker it holds, and right-clicking the machine with it takes the beaker back out.
- **Syringe:** use the syringe in hand to cycle its transfer amount (5 / 10 / 15); right-click a container to **draw**, left-click to **inject**.
- **Spilling the leftovers:** right-click with the apparatus to spill the beaker's contents on the floor.

If any of that is different on your server, please open an issue - it is the most useful report you can send.

### Pick a recipe

| Recipe | Trigger | Result |
| --- | --- | --- |
| Cleaner foam | fluorosurfactant | 30 tiles, 4u cleaner per tile per tick |
| Cleaner smoke | phosphorus | 45 tiles, 3u per tile per tick |
| Lube foam | fluorosurfactant | 30 tiles, 4u per tile per tick |
| Lube smoke | phosphorus | 45 tiles, 4u per tile per tick |
| Hellfoam (assumed: fluorosulfuric acid foam) | fluorosurfactant | 30 tiles, 4u acid per tile per tick |

Cleaner and lube only act on a tile when at least 1u lands on it per tick; every recipe clears that.

### New reactions (second batch)

Full steps, cautions and the code each effect was read from are in [`docs/RECIPES.md`](docs/RECIPES.md#new-reactions). Several use bigger gear on purpose.

| Reaction | What it does | Gear |
| --- | --- | --- |
| Metal foam | foam that sets into 20 HP airtight walls: 100 tiles from a stock beaker | heater |
| Metal foam XL | the same, 200 tiles | bluespace beaker, heater |
| Iron foam | same walls, 50 HP | heater |
| Smart foam | walls only on area borders (breach rims, door frames) | bluespace beaker, heater |
| Drying foam | wipes lube / wet floors off 30 tiles (the antidote to lube foam) | stock |
| Carpet foam / black carpet foam | turns every floor tile it touches into (black) carpet | 1u blood as a seed |
| Carpet foam XL | 120 tiles of carpet | bluespace syringe + beaker, 1u blood |
| Brute-mender fog / burn-mender fog | chem smoke that heals everyone breathing it (libital / aiuri) | stock |
| Sorium shockwave / dark matter pull | vortex that throws things away from / pulls them toward you (range caps at 6 tiles, so a bigger beaker does not help) | stock |
| Friendly life | spawns rand(1, mult) friendly mobs; a 300u beaker allows mult 3 | bluespace beaker, donated strange reagent + synthflesh |

Reactions the dispenser alone cannot make (life, corgium, butterflium, ant slurry) are listed at the end of that document with what they are missing.

**The blood trick:** blood is not a dispenser chemical, but `unstable mutagen + a blood catalyst -> more blood` (a virology recipe) multiplies it, so 1u of real blood drawn with your syringe becomes as much as you like. The planner treats that loop as a seed, not a source.

### Gear and upgrades
Beaker, syringe and a second beaker are parameters, with sizes read from the game source:

| Item | Volume |
| --- | --- |
| Beaker / large (borg stock) / x-large / metamaterial / bluespace | 50 / **100** / 120 / 180 / 300 u |
| Cryostasis beaker (nothing reacts inside) | 50 u |
| Syringe: stock / piercing upgrade / bluespace upgrade | **15** / 10 / 60 u |
| Secondary beaker apparatus upgrade (medical borgs) | a second 100u beaker |

The beaker apparatus accepts any beaker, bottle or tube, so a better beaker found on the station can go straight in. Examples of what the planner finds for cleaner foam: a **bluespace beaker** with the stock syringe gives the same 30 tiles but 3x the cleaner per tile; **two bluespace beakers** give 150 tiles. Ask the planner for your exact gear (below).

---

## Ask the planner for a new recipe

```
python3 src/chemcli.py nade --trigger foam  --payload "space cleaner"
python3 src/chemcli.py nade --trigger smoke --payload "space lube" --mode lean
python3 src/chemcli.py nade --trigger foam  --payload "space cleaner" --beaker bluespace --syringe bluespace --trigger-units auto
python3 src/chemcli.py nade --trigger foam  --payload "space cleaner" --trigger-beaker large     # two-beaker mode
python3 src/chemcli.py reaction "space cleaner"        # look a recipe up
python3 src/chemcli.py sim "dispense water 30; dispense silicon 15; dispense oxygen 15"   # simulate any step list
python3 src/chemcli.py sim "add blood 1; dispense radium 5; dispense phosphorus 5; dispense chlorine 5"   # 'add' = an ingredient from outside the dispenser
python3 src/export_recipes.py                          # regenerate docs/RECIPES.md from src/recipes.py
```

`nade` designs a *foam or smoke carrier* for one payload chemical. The new-reaction recipes (walls, vortexes, mob spawns...) are hand-written step lists in `src/recipes.py` and checked with `sim`: the engine simulates the reagent maths and reports the effect (foam tiles, vortex range, mob-spawn cap); what the effect then does in the game is read from the code and cited in each recipe.

Python 3 only, no dependencies. Gear flags take a name or a volume: `--beaker large|xl|meta|bluespace|beaker|noreact|bottle|tube|<units>`, `--syringe standard|piercing|bluespace|<units>`, `--trigger-beaker <name|units>`, `--trigger-units N|auto`. The planner searches dispenser amounts exhaustively, simulates every candidate through the same reaction code, checks that the order of dispensing does not change the result (or flags it when it does), and prints the step list.

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

This is meant to grow into a general recipe generator: **bartender drinks**, and **non-borg chem mixes** that take advantage of everything a player controls - bigger and more containers, chem bags, bottles, the chem master. Today it is borg-only. A **service borg** may also be able to use parts of it (it carries a beaker apparatus and a drink dispenser, but no syringe) - that needs verifying. Details and open questions: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What is verified and what is not

| Verified | Not verified |
| --- | --- |
| Reaction formulas, temperatures, dispenser lists, container sizes - parsed from the game source | Any of it in a live round |
| Reaction ordering, BYOND rounding quirks, nested reactions, foam/smoke scaling - 32 source-cited engine checks | The borg click flow (dispenser / apparatus / syringe handling) |
| Six recipes re-derived by hand independently (`src/verify_independent.py`) | Borg use of a chem heater; pouring one held beaker into another |
| Reagent maths of the 13 new reactions (engine), their effects read from the code | Mob-spawn, vortex and wall effects are not simulated, only cited; that a dispenser click really stops at the free space is read from `chem_dispenser.dm`, not played |
| Rules diff against live source (`codecheck.py`) | Dispenser power-cell capacity (not modelled); "hellfoam" meaning |

## Tests

```
python3 -m unittest discover -s tests -v
```
`tests/legacy_checks.py` holds the original source-cited checks; new tests go in their own `tests/test_*.py` files (shared helpers in `tests/helpers.py`, including a tiny fake game tree for end-to-end tool tests).

## Layout
`src/dmparse.py` DM parser - `chemlib.py` reaction simulator - `planner.py` borg rig and `Gear` - `search.py` design search - `chemcli.py` CLI - `codecheck.py` / `wikicheck.py` change detection - `recipes.py` the verified recipes - `chemdata.json` rules snapshot (Monkestation2.0 commit recorded inside). See [`NOTICE.md`](NOTICE.md) for licensing (AGPL-3.0) and attribution.
