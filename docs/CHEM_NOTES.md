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
- Heating is a separate machine step (about 30 s to 400 K). The beaker keeps that temperature, and so do the foam tiles. Whether a borg can use a chem heater is unverified.

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
- Metabolism is 0.2 u/s (`REAGENTS_METABOLISM`) times the reagent's own factor.

**Where the source and the wiki disagree**
- Monkestation recipes are not tg's. Examples: fluorosulfuric acid is sulfuric acid + fluorine + hydrogen + potassium (4 units out, heated to 380 K); space lube makes 4 units from 3. The sandbox cannot reach the wiki, so the **game source on GitHub is the reference**, and `codecheck.py` diffs it against the snapshot.

## Not yet verified in game
- The clicks (dispenser, beaker apparatus, syringe), whether a borg can use a chem heater, and whether a borg slips on foam.
- Every effect that is only cited (walls, vortexes, mob spawns, fire and slip behaviour of the hell recipes). The simulator checks reagent amounts, tiles and per-tile doses, not what the effect does to a person.
- How far foam actually spreads: tile counts are a **maximum**. Foam only fills open turf, so in a small room the real group size is smaller (less dilution, stronger foam) and in a corridor it runs long.
