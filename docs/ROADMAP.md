# Roadmap and open questions

## Where this is going
The engine is a general "what does this pile of reagents become, and what do I click to get it" model, not a grenade tool.
Grenades were the first target because they have a clear goal (cover tiles with X). The same machinery should extend to:

- **Bartender drinks and other food/drink recipes.** Same reaction database, different planner goal ("N units of drink X").
- **Non-borg chem mixes.** Players have far more control over containers: chem bags, big beakers, bottles, the chem master,
  plumbing. A planner that is told what containers and how much space exist (the `Gear` object) can plan around them.
- **Medicine and utility chems** with a purity/pH model for codebases that still use them (see "Other servers" in the README).
- **Other borg models.** The service borg carries a beaker apparatus (it holds a drinking glass by default), a beverage
  dispenser module and a dropper, but no syringe. Pour-style recipes (the two-beaker mode) and drink recipes *might* work
  for it. **Unverified** - nobody has checked what a service borg can actually move between containers.

## Open questions (need an in-game check)
1. Exact click flow for a borg: loading the apparatus beaker into the chem dispenser, getting it back, drawing into the
   syringe from a beaker, setting transfer amounts.
2. Can a borg operate a chem heater (hellfoam needs 380K+)?
3. How does a borg aim one held beaker at another for the two-beaker pour (probably by setting one down)?
4. Chem dispenser energy cell capacity (not modelled; a very long recipe may need a recharge).
5. "Hellfoam" is not a defined term in the Monkestation code or wiki; the repo treats it as fluorosulfuric acid foam.

## Engine gaps
- Timed (equilibrium) reactions, pH and purity are not modelled. Monkestation has them disabled; tg proper does not.
- Reactions with explosions, spawned mobs, atmos or EMP effects are refused rather than guessed.
- Foam/smoke exposure numbers assume the effect-tick values read from the source (foam 0.2s / 8s life, smoke 2s / 20s life).
