# Chem system notes (Monkestation)

What the chemistry code actually does, as found while building the recipe engine. Everything here was read from the game source (file names in brackets) and checked in the simulator; **none of it has been tested in a live round**, and items marked *unverified* are inferences. Rules snapshot: Monkestation2.0 commit `607bcdae1a`. If something stops matching the game, run `python3 src/codecheck.py` first.

## Foam vs smoke

| | Foam | Chem smoke |
|---|---|---|
| Trigger | fluorosurfactant + water | phosphorus + potassium + sugar (smoke powder) |
| Area | **2 tiles per unit** of trigger (`create_foam(..., 2 * created_volume)`) | **3 tiles per unit** of trigger (3 smoke powder per reaction multiple) |
| Life | 8 s | 20 s |
| Payload per tile | the whole beaker copied **x3.2** into every tile, then **diluted** when the foam is larger than 25 tiles | the whole beaker copied **1:1** into every tile, **never diluted** |
| How much a mob takes in total | tile content x min(1, 25/tiles), spread over 8 s | tile content x 1, spread over 20 s |
| How it reaches a mob | `expose(mob, VAPOR)` every 0.2 s: reagents with the default `penetrates_skin = VAPOR` go into the blood, and each reagent's own `expose_mob` runs | two ways. (1) Every movable on the tile (mobs of any kind, items) gets `expose(TOUCH)` each 2 s tick at 10% of the tile content. (2) **Carbon** mobs without internals or smoke protection also get `copy_to`, a 10% share of **every** reagent straight into the blood (ignores `penetrates_skin`), plus `expose(INGEST)` |
| Floor | `expose(turf, VAPOR)` each tick | `expose(turf, TOUCH)` each 2 s tick, 10% of the tile content |
| Slippery | **yes, by itself** (`/datum/component/slippery, 100`), whatever the payload | no |
| Blocks vision | no | yes |
| Hurts the borg using it | yes, foam exposes every `/mob/living`, borgs included (*unverified* whether a borg slips) | only through the TOUCH exposure: harmless chems do nothing to you, but acid or fire stacks would still land. The blood copy only affects carbon mobs, so healing or sleep chems do not act on a borg |
| Stopped by | foam dissolves in hot air (above 475 K, chance = temperature - 475 per atmos tick) | stabilizing agent in the beaker cancels smoke powder (`smoke_powder` checks for it) |

### When to use which

**Foam is better when**
- you want the target on the floor: foam itself slips, so even a pure cleaner or healing foam knocks people down;
- the payload works by touch or vapour: acid, napalm fire stacks, lube on the floor, carpet, drying agent, metal walls;
- the area is small (25 tiles or fewer): then there is no dilution and every tile holds 3.2x the payload;
- you want it gone quickly (8 s).

**Foam is worse when**
- the area is large: past 25 tiles each tile gets only 25/tiles of its content, so a 120 tile foam is about a fifth as strong per tile as a 20 tile one;
- the payload is fire: the fire heats the air and dissolves the foam, so napalm and phlogiston get fewer exposure ticks than the 8 s suggests;
- the payload needs a lot of time in the blood (the target slips and walks off after a few seconds).

**Smoke is better when**
- you want **area**: 3 tiles per unit instead of 2, and no dilution, so a 180 tile cloud holds as much per tile as a 45 tile one;
- the payload works through the lungs: sleep chems (chloral hydrate), healing chems, poisons: everything in the tile ends up in the blood;
- the payload acts through the blood (sleep chems, healing chems, poisons) and you are a borg: the blood copy only applies to carbon mobs, so your own healing or sleeping cloud does not affect you (a contact chem like acid still would);
- the target should not notice a floor effect.

**Smoke is worse when**
- you need a knockdown or a slip on contact (lube on the floor still slips people who walk in, but nothing trips them);
- the target wears internals, a gas mask with air, or is not carbon (borgs, most simple mobs);
- you want a payload that only acts on contact **and** gets a strong dose: smoke delivers 10% of the tile per tick through TOUCH (napalm and acid do work in smoke), but foam gives 3.2x the content in a small area;
- smoke powder needs potassium and sugar in the beaker, which makes the recipe **order sensitive** (potassium + water explodes), so those two always go in last, after the water in the payload is used up.

### Rules of thumb
- Dose per tile: foam = beaker content x 3.2 x min(1, 25/tiles); smoke = beaker content x 1.
- More tiles from a bigger syringe always costs payload: with a foam, 2 units of beaker per tile-pair go to surfactant and water; with smoke, 3 units go to smoke powder (all of it consumed).
- Foam of 25 tiles or fewer (trigger of 12u or less) is the strongest per tile; a 15u trigger is 30 tiles, already 17% diluted.
- Cleaner and lube only act on a tile when at least **1u** lands per exposure call (`reac_volume >= 1`). Foam: tile content x 0.025 x dilution per call. Smoke: tile content x 0.1 per call. Check this before making a big, thin cloud.

## Edge cases and oddities

**Reactions and the dispenser**
- Reactions are **instant** and happen the moment the last ingredient lands. How many times a reaction fires is `min(round(have / amount_needed))` (BYOND `round`), so leftover fractions and "almost enough" amounts matter. pH, purity and timed equilibrium reactions are off on this server and are not modelled; on tg proper they are on.
- `created_volume` handed to a reaction's `on_reaction` is the **number of times it fired**, not the volume of product. That is why foam is `2 x`, metal foam `5 x`, smoke `3 x`, sorium range `sqrt(4 x)`.
- The chem dispenser clicks 5, 10, 15, 20, 25, 30, 50 or 100u, and a click is **clamped to the free space** in the beaker (`min(amount, max_volume - volume)`). So the last click can be an exact fill. Amounts have to be multiples of 5, which makes most chems come in blocks: lube 20u, acid 20u, napalm 15u oil, phlogiston 15u, stabilizer 15u.
- Reactions that share an ingredient compete for it (sulfuric acid goes to fluorosurfactant, fluorosulfuric acid and phlogiston). Build each chem as a block, completely, before starting the next one. The planner flags recipes where the order of clicks changes the result.
- **Heating** is a separate machine step. The chem heater (`chem_heater.dm`) moves the beaker toward its target every 2 s by `(target - T) * 0.1 * tier * 2`, in both directions, so it only approaches the target and never reaches it (a stock part is tier 1: about 34 s from 300 K to within 5 K of 500 K). The recipe says to wait until the display reads 5 K under the target; that is the temperature simulated. A beaker keeps its temperature when taken out, and every chemical added afterwards mixes in at 300 K (equal heat capacities), so it **cools the beaker** (45u at 495 K plus 50u cold = about 392 K). Hence the planner rules: heat last when it can, otherwise add a `cool <K>` step (heater target low, wait until the display reads that or less) so a hot beaker cannot react with what comes next. Every recipe is re-simulated with the beaker 5 K hotter and 30 K colder than expected and is refused if the result changes (`temp_ok`). Whether a borg can use a chem heater is unverified.

- **Click order inside a dispenser step is biggest click first** (the page lists clicks that way and the engine now runs them that way). The planner checks recipes against the opposite order too, and a recipe whose result changes is flagged or rejected. One BYOND rounding quirk: 17 reaction multiples from 50u chlorine at a 3:1 ratio asks for 51u and leaves 1u when the amount is split across clicks.
- **A reaction fires on the first click that completes it.** The reaction runs after every dispenser click, not after the last one you planned. With metal foam the metal is needed 3:1, so a 180u metal order in clicks of 100 + 50 + 30 fires at the first 100u click (about 33 reaction multiples) and the rest of the metal sits in an empty beaker. Put the ingredient that triggers the reaction last, and make that last amount a single click (`metal-foam-xl-300` ends on the 100u lithium click, which the free space clamps to exactly 40u).
- **Leftover reagents ride into the foam.** `create_foam` copies whatever is still in the beaker into every tile before clearing it. Foam tiles hold an instant-react holder, so a leftover reagent multiplied by 3.2 can fire a reaction again inside the foam (1u leftover aluminium made 5 extra tiles carrying acid); the simulator warns about it. A 60u block of fluorosulfuric acid with a reaction that only uses 47u would leave 13u of acid in a "wall" foam, so structure foams are sized so that the acid is used up exactly (acid comes in blocks of 20u).
- **A single click is at most 100u,** so no reaction that needs more than 100u of one reagent at its trigger moment can fire bigger than that click allows. A 300u beaker does not make metal foam bigger than about 200 tiles; run the recipe twice instead.
- **Healing smoke is dose-limited, not volume-limited.** The blood copy over the full 20 s is the whole tile content, and libital / aiuri have no overdose threshold, only their damage (liver about 0.15/s, eyes about 0.125/s) for as long as they stay in the blood. Both burn off at **0.1 u/s** (a 0.5 factor on `REAGENTS_METABOLISM`, parsed from the reagent code), so 30u of libital is about 300 s: about 450 brute healed and about 45 liver damage if all of it stays. The 300u med recipes therefore add a second medicine and more area instead of more dose per tile (30 to 60u per tile).
- **Convermol is an ordinary instant reaction in this engine** (heated, 370 K). An earlier version of these notes called it a timed equilibrium reaction; that was wrong. It only looked slow because a chem heater approaches its target temperature asymptotically and never reaches a setpoint equal to the requirement: set the heater 10 to 20 K above what the reaction needs. The planner now models that and warns when a reaction is too cold.

**Syringe and beaker**
- Syringe transfer settings: stock **5 / 10 / 15**; bluespace upgrade **10 / 20 / 30 / 40 / 50 / 60** (from the item definitions). A recipe that draws 15u does **not** work on a bluespace syringe; one that draws 10u works on both.
- To inject, the transfer setting must be at least what the syringe holds, or only that amount goes in.
- `create_foam` and the smoke effect **empty the beaker**. Anything left over is gone, and a second click does nothing.
- Spilling to get rid of surplus trigger chem is part of most recipes.

**Dangerous or surprising reactions**
- **Phlogiston** forms a 1000 K plasma fireball on the borg and **wipes the whole beaker** unless stabilizing agent (iron + oxygen + hydrogen, 15u minimum) is already in it. The same check protects rdx and some other volatile recipes.
- **Chlorine trifluoride** (chlorine + 3 fluorine at 424 K) spawns a 3x3 hotspot and sets the beaker to 1000 K when it forms, with no stabilizer check. Do not make it in a borg beaker.
- **Potassium + water** explodes; sugar and potassium go in last in every smoke recipe.
- Reactions with hidden effects (`on_reaction`) are not all modelled. The engine marks any it cannot model and refuses to publish a recipe that depends on one.
- Foam tiles hold an **instant-reacting** reagent holder: reagents copied into a tile can react there. Almost never matters, but a reaction that only becomes possible at x3.2 amounts would fire in every tile.

**Doses and effects (from the reagent code)**
- Napalm: `penetrates_skin = NONE`, so in foam it never reaches the blood; its effect is `min(volume / 4, 20)` fire stacks per exposure call (foam: VAPOR, smoke: TOUCH). In smoke a carbon mob also gets napalm copied into the blood, which adds 1 fire stack per metabolism tick. Welding fuel is `volume / 10`.
- Phlogiston ignites on **any** exposure (+1 fire stack and `ignite_mob`), so it works in foam (VAPOR) and smoke (TOUCH and INGEST).
- Chloral hydrate: confusion and drowsiness for the first 10 metabolism cycles, then sleep until cycle 50, then toxin damage. It is the cheap sleeper, but it costs 5u of raw chems per 1u of product (ethanol 1 + chlorine 3 + water 1 makes 1).
- Space lube: floor slippery for `min(volume x 2 s, 120 s)` after each exposure of at least 1u, and the wet state starts at 15 s.
- Fluorosulfuric acid: acid power 42, plus fire damage in the blood that grows each metabolism cycle.
- Libital costs about 0.15 liver damage per second while it heals about 1.5 brute per second; aiuri costs about 0.125 eye damage per second for about 1 burn per second.
- Metabolism is 0.2 u/s (`REAGENTS_METABOLISM`) times the reagent's own factor (libital and aiuri 0.5, so 0.1 u/s). The engine reads each reagent's description, overdose threshold and metabolism rate from source; the page's *Dosing* line quotes them.

**Where the source and the wiki disagree**
- Monkestation recipes are not tg's. Examples: fluorosulfuric acid is sulfuric acid + fluorine + hydrogen + potassium (4 units out, heated to 380 K); space lube makes 4 units from 3. The sandbox cannot reach the wiki, so the **game source on GitHub is the reference**, and `codecheck.py` diffs it against the snapshot.

## Not yet verified in game
- The clicks (dispenser, beaker apparatus, syringe), whether a borg can use a chem heater, and whether a borg slips on foam.
- Every effect that is only cited (walls, vortexes, mob spawns, fire and slip behaviour of the hell recipes). The simulator checks reagent amounts, tiles and per-tile doses, not what the effect does to a person.
- How far foam actually spreads: tile counts are a **maximum**. Foam only fills open turf, so in a small room the real group size is smaller (less dilution, stronger foam) and in a corridor it runs long.

## Effects, overdoses and foam / smoke exposure (stats system)

Source of truth is the game code, parsed by script (no wiki needed): `src/effects.py` -> `data/chem_stats.json` (per-chemical life / overdose effects, metabolism, hooks), `src/gear.py` -> `data/gear_protection.json` (bio / fire armour per garment). Re-run both with `MONKE_SRC=<game checkout>` when the game snapshot changes. `data/chem_curated.json` is the hand-written layer (named special effects such as Slick / Ignite / Clean with tooltips, crit-only buffs, overdose-severity overrides).

* Units: one Life tick = 2 s. Damage / healing numbers are per tick, NEGATIVE = healing. A chemical's per-tick effect does not depend on how much of it is in the blood, only on it being there; amount sets how long it lasts (1u lasts 1 / (2 x metabolization rate) ticks) and when the overdose starts.
* Overdose of a mix: a chemical at share f of the mix overdoses after (its threshold / f) units of the whole mix are in the blood. Severity is about "HP per tick while overdosed" (2 brute per tick = 2.0; optional organs low), computed from the code with overrides in the curated file.
* `src/chemstats.py` (profiles, mix analysis), `src/exposure.py` (foam / smoke model, protection scenarios), `src/statspanel.py` (the block the page draws; text output for the CLI).
* CLI: `chemcli.py mix "libital 30, salicylic acid 15"`, `chemcli.py mix --recipe <id>`, `chemcli.py stats <chem>`.
* Foam / smoke recipe cards get an Effects block: tile contents, per-chemical totals, the exposure rules, and a table of what a person takes by protection. A plain chemical recipe can show one too: give it a `mix` (name -> units) in the book.
* Foam: 0.2 s ticks, 8 s life; each tick exposes every chemical in the tile by VAPOR; skin only absorbs an exposure of 0.5u or more after (1 - bio protection). Smoke: 2 s ticks, 20 s life; 10% of the tile per tick is breathed in unless internals are open, the target does not breathe, or a mask / glasses / hat blocks gas smoke. Contact effects (fire, acid, lube, cleaner) ignore armour.
* Not modelled: liver efficiency, burning over time beyond fire stacks, chemical reactions inside the blood, extra exposures from foam spreading onto a person. Nothing here has been checked in-game yet.

## Amount applied per tile (src/tileapply.py, data/turf_effects.json)

* One module owns the foam / smoke numbers: `plan(kind, tiles)` (exposure share, number of exposures, timing), `per_tile`, `units_needed`, `turf_effects`, `evaluate`, `tile_report`. `search.foam_metrics`, `search.smoke_metrics` and `exposure.py` call it, so the recipe finder, the result text and the Effects block cannot disagree.
* The game exposes a tile every tick with (units in the tile) x fraction. Foam: fraction = 0.2 x 25 / (8 x max(25, area)), 40 exposures. Smoke: 10% of the tile, 9 exposures that touch the floor. Floor effects test the amount in ONE exposure, not the tile total: lube 1u, water / peroxide 5u (wet), thermite 1u (then the coat ADDS UP, 30u melts a floor or wall, 50u a reinforced wall), uranium / radium glow 3u, fuel pool 5u, salt 1u, blood splatter 3u, cleaner 1u, frost oil 1u. The list lives in `data/turf_effects.json` (parents' effects are inherited, e.g. radium from uranium).
* Wet floors: the first exposure sets the minimum time (lube 15 s), each later one adds 2 s per unit but only 12 s per exposure counts (the code caps at 120 DECIseconds), and the timer drains at (T - 273.15) / 2 / 15 s per s (0.67 s per s at 293 K). Earlier text said "max 120 s": that was wrong.
* A chemical in a foam / smoke tile that has no floor effect (threshold not met), no contact effect on a person and nothing it does once absorbed is "wasted space"; the recipe is flagged BROKEN, shown on the card, listed by `book rebuild`, and `publish` refuses it unless the spec sets `allow_waste`. Metal / iron / smart foams are skipped (the foam itself is the effect).
* CLI: `chemcli.py tile foam 20 "lube 64, thermite 40"` (also `smoke`, `--air <K>`).

## Slick floor duration and the lube flag (tileapply.slick_sim / slick_report, data/tile_policy.json)

* `slick_sim` plays the game's wet-floor component through every exposure, with the tile's chemicals in tile order: a wet chemical sets the timer to its minimum (lube 15 s) the first time and later to clamp(timer + added, minimum, 5 min), where lube adds 2 s per unit but at most 12 s per exposure; a drying agent takes 10 s per unit off every wet type; between exposures the timer drains at (T - 273.15) / 2 / 15 s per s (0.67 at 293 K). It returns how long the floor is slick counted from the first exposure.
* Per slippery chemical the report gives units per tile now, units per tile at its threshold, the **extra over the threshold**, wet time added per exposure, the slick time alone and at the threshold, and the largest amount that still meets the target. Whole mix: total slick time, the shortest possible in that size of effect, and a drying-agent amount that would fix it.
* **Finding:** lube cannot be short. At just over 1u per exposure a 20 tile foam (40 exposures) still stacks to about 140 s of slick floor, and a smoke (9 exposures) about 47 s, because every exposure adds 2 s and the minimum is 15 s. Under 1u per exposure lube does nothing at all. Only a drying agent after the lube in the tile (about 41u per tile for a 20 tile foam), or hot air (above 373 K the floor dries at once, not modelled), shortens it.
* Policy: `slick_max_s` = 15 in `data/tile_policy.json`. A recipe over it is FLAGGED (red chip and banner on the card, listed by `book rebuild`, printed by `publish`), never refused. Lube bombs where a long lube is the point carry `lube_ok: true` (`publish --lube-ok`).

## Bigger-beaker versions (src/scale.py, `chemcli.py scale <ids> --beaker 300 [--publish]`)

Keeps the trigger part of a nade recipe (so the same area), multiplies each payload dispense by a factor (rounded to 5u, a click is at most 100u, longer amounts split), and keeps the factor with the most payload per tile whose result the engine accepts (no warning or overflow, same foam / smoke and area, click-order and temperature checks pass). The scaled recipe inherits the source recipe's flags.

## Exact stoichiometry and the hellfoam designer (src/stoich.py, payload.py, hellfoam.py, fixes.py)
- `stoich.plan/quantum/ops`: works a reaction chain out in exact fractions. A product's *quantum* is the smallest amount whose every raw ingredient is a multiple of 5u (the dispenser click), so nothing is left over to ride into the cloud. Libital is a 135u quantum, aiuri 60u, chloral hydrate needs 5u of raw per 1u made.
- `payload.build`: builds a foam/smoke recipe from exact amounts (trigger, payload blocks in order, closer), batching big products (chloral first, in rounds) so the beaker never overflows mid-build, and heating after each hot block.
- `chemcli.py fixbroken [--apply]`: rebuilds the BROKEN recipes from exact amounts (`fixes.REBUILD`) and drops the ones with no exact version that fits the gear (`fixes.REMOVE`, each with a reason). Removed: libital fog/foam at 100u (135u batch cannot fit), aiuri fog at 100/60, the 120-tile all-round fog (replaced by the 90-tile one).
- `chemcli.py hellfoam [--beaker B] [--syringe S] [--publish]`: designs hellfoam variants for every beaker/syringe pair (archetypes: acid, fire, toxic, all, lite, acid+fire, each with/without sleep and with/without a lube-and-drying-agent slip package) and keeps the best by score. Old hand-built hellfoams are replaced (`hellfoam.OLD_IDS`).
- Supporting chems (stabilizing agent for phlogiston, the carpet blood seed) take space but are not counted as wasted (`data/tile_policy.json` `support`).
- Floor safety: a recipe is floor-destroying if the thermite coat melts the floor, it has clf3, or acid power >= 200. Fluorosulfuric (42) and sulfuric (10) acid only leave an acid layer that eats floor items. The page shows a floor-safe chip.
- Slick window: lube is wanted for ~9-14 s. Only some tile counts can hit it, because drying agent removes 10 s per unit and lube sets a 15 s minimum: 10/20 tiles lube 20 + drying 15; 80 tiles 60+45; 100 tiles 60+60; 120 tiles 80+75. None at 30/40/60 tiles. Drying agent has to come after lube in the tile (order is tracked in `chemcli.signature` so tidy cannot swap them).
- Unverified in game: reagent order within a tile follows the engine's dict order here; libital 13.5u/tick is a heavy dose (liver damage); fentanyl, nitracid, sulfonal and nitrous oxide were considered as extra payloads and not added.
