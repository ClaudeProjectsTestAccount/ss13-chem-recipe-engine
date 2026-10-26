"""recipes.py - the verified borg grenade recipes (default gear: standard syringe 15u + large beaker 100u)."""
SYR = [('dispense', 'fluorine', 10), ('dispense', 'carbon', 10), ('dispense', 'sulfuric acid', 5), ('draw', 15), ('spill',)]
PH = [('dispense', 'phosphorus', 15), ('draw', 15), ('spill',)]
RECIPES = [
 ('cleaner-smoke', 'Cleaner smoke (45 tiles)', 'space cleaner', PH + [('dispense', 'hydrogen', 15), ('dispense', 'nitrogen', 5), ('dispense', 'water', 15), ('dispense', 'potassium', 15), ('dispense', 'sugar', 15), ('inject',)]),
 ('cleaner-foam', 'Cleaner foam (30 tiles)', 'space cleaner', SYR + [('dispense', 'hydrogen', 30), ('dispense', 'nitrogen', 10), ('dispense', 'water', 45), ('inject',)]),
 ('lube-smoke', 'Lube smoke (45 tiles)', 'space lube', PH + [('dispense', 'water', 10), ('dispense', 'silicon', 10), ('dispense', 'oxygen', 10), ('dispense', 'potassium', 15), ('dispense', 'sugar', 15), ('inject',)]),
 ('lube-foam', 'Lube foam (30 tiles)', 'space lube', SYR + [('dispense', 'water', 30), ('dispense', 'silicon', 15), ('dispense', 'oxygen', 15), ('inject',)]),
 ('hellfoam', 'Hellfoam - fluorosulfuric acid foam (30 tiles)', 'fluorosulfuric acid', SYR + [('dispense', 'sulfuric acid', 15), ('dispense', 'fluorine', 15), ('dispense', 'hydrogen', 15), ('dispense', 'potassium', 15), ('heat', 400), ('dispense', 'water', 15), ('inject',)]),
]

# ----------------------------------------------------------------------------------------------------------------
#  NEW REACTIONS (second batch).  Each entry is a dict; ops use the same mini-language as above plus
#      ('add', reagent, units, where)   an ingredient that does NOT come from the chem dispenser
#  `gear` is the Gear(...) the recipe was verified with.  `what` / `how` / `caution` are written from the game code
#  (file names in `src`), the numbers in the result line are produced by the engine at export time.
# ----------------------------------------------------------------------------------------------------------------
FACID20 = [('dispense', 'sulfuric acid', 5), ('dispense', 'fluorine', 5), ('dispense', 'hydrogen', 25), ('dispense', 'potassium', 5),
           ('heat', 400), ('dispense', 'lithium', 20)]
SYR60 = [('dispense', 'fluorine', 30), ('dispense', 'carbon', 30), ('dispense', 'sulfuric acid', 15), ('draw', 60), ('spill',)]
BLOOD_SEED = ('add', 'blood', 1, '1u of blood drawn with the syringe from a healthy crewmember; it is only a seed, the mutagen loop multiplies it')
CARPET15 = [BLOOD_SEED,
            ('dispense', 'radium', 5), ('dispense', 'phosphorus', 5), ('dispense', 'chlorine', 5),     # -> 15u mutagen -> 15u blood
            ('dispense', 'mercury', 5), ('dispense', 'sugar', 5), ('dispense', 'lithium', 5)]            # -> 15u space drugs -> 30u carpet

EXTRA = [
 dict(key='metal-foam', short='Walls: seals breaches and corridors instantly (aluminium foam, 100 tiles)', title='Metal foam - instant walls (100 tiles)', harm='caution', gear=dict(beaker='large'),
      ops=FACID20 + [('dispense', 'aluminium', 100)],
      what='Aluminium foam. About 8 seconds after it appears, every foam tile leaves a foamed-metal wall: dense, airtight, 20 HP, and on a '
           'space tile it also lays plating first. Seals hull breaches and corridors instantly.',
      how='Needs the chem heater for the fluorosulfuric acid step. The last click is the 100u aluminium button: the dispenser stops at the free '
          'space (60u), which is exactly the 3:1 aluminium the 20u of foaming agent/acid can use. No acid is left over.',
      caution='Walls form on every foamed tile, including ones people stand on, so you can box people in. Never foam over injured crew or block '
              'medbay/escape routes. Bare hands bounce off the walls; any tool or weapon breaks them.',
      src='recipes/others.dm (metalfoam), effects_foam.dm (foamedmetal, 20 integrity, foam_floor)'),
 dict(key='metal-foam-xl', short='Same walls over 200 tiles, because the beaker is bigger', title='Metal foam XL - 200 tiles (bluespace beaker)', harm='caution', gear=dict(beaker='bluespace'),
      ops=[('dispense', 'sulfuric acid', 10), ('dispense', 'fluorine', 10), ('dispense', 'hydrogen', 50), ('dispense', 'potassium', 10), ('heat', 400),
           ('dispense', 'aluminium', 180), ('dispense', 'lithium', 100)],
      what='The same walls, twice the area, because a bigger beaker holds twice the reagents (5 tiles per unit of foam reaction, no cap in the code).',
      how='The last click is the 100u lithium button; the dispenser stops at the free space (40u). That makes exactly 40u of foaming agent, '
          'which matches the 40u of acid, so no acid is left in the foam. The spare 60u of aluminium is harmless dust.',
      caution='Same as metal foam, and a 200 tile blob can wall off a whole department.',
      src='recipes/others.dm (metalfoam), effects_foam.dm'),
 dict(key='iron-foam', short='Stronger walls (50 HP instead of 20)', title='Iron foam - reinforced walls (100 tiles)', harm='caution', gear=dict(beaker='large'),
      ops=FACID20 + [('dispense', 'iron', 100)],
      what='Same recipe with iron instead of aluminium. The wall is the iron foam variant: 50 HP instead of 20 (2.5 times sturdier).',
      how='Identical steps to metal foam; the 100u iron click stops at 60u.',
      caution='Same as metal foam. Sturdier walls are harder for trapped people to break out of.',
      src='recipes/others.dm (ironfoam), effects_foam.dm (foamedmetal/iron max_integrity 50)'),
 dict(key='smart-foam', short='Walls only on area borders / breach rims, plates over space', title='Smart foam - seals area borders only (100 tiles, bluespace beaker)', harm='caution', gear=dict(beaker='bluespace'),
      ops=[('dispense', 'sulfuric acid', 5), ('dispense', 'fluorine', 5), ('dispense', 'hydrogen', 5), ('dispense', 'potassium', 5), ('heat', 400),
           ('dispense', 'lithium', 30), ('dispense', 'hydrogen', 30),
           ('dispense', 'welding fuel', 10), ('dispense', 'carbon', 5), ('dispense', 'hydrogen', 5), ('dispense', 'oxygen', 5),
           ('dispense', 'iron', 10), ('dispense', 'aluminium', 100)],
      what='Smart foam only leaves a wall on a tile that touches a different area (door frames, hull edges, breach rims) and plates over space. '
           'You can flood a whole room and only its perimeter gets sealed.',
      how='The smart foaming agent has to be made before aluminium goes in, otherwise plain foaming agent + acid + aluminium fires ordinary metal foam. '
          'Needs a bluespace beaker for the room (the intermediates plus the 100u aluminium click do not fit a 100u beaker).',
      caution='The leftover oil and acetone in the foam is inert but oil burns.',
      src='recipes/others.dm (smart_foam, smart_foaming_agent), effects_foam.dm (metal/smart make_result)'),
 dict(key='drying-foam', short='Anti-lube: dries wet and slippery floors over 30 tiles', payload='drying agent', title='Drying foam - removes lube and wet floors (30 tiles)', harm='safe', gear=dict(),
      ops=SYR + [('dispense', 'stable plasma', 30), ('dispense', 'ethanol', 15), ('dispense', 'sodium', 15), ('dispense', 'water', 15), ('inject',)],
      what='Drying agent foam. Every foam tick the drying agent wipes the wet/slip state off the floor (MakeDry(ALL) with 10 seconds of drying per unit), '
           'so it is the antidote to lube and water. (The code comment says a single 5u spray is meant to clear a wet floor; every tile of this foam gets far more.)',
      how='Same trigger syringe as the other foams. Planner design: 144u of drying agent per tile.',
      caution='The foam itself is slippery while it lasts (about 8 s), the floor is dry afterwards. Any galoshes lying in the foam are turned into dry galoshes.',
      src='reagents/other_reagents.dm (drying_agent expose_turf/expose_obj), recipes/others.dm (drying_agent)'),
 dict(key='carpet-foam', short='Turns the floor into carpet (cosmetic, needs a 1u blood seed)', payload='carpet', title='Carpet foam - redecorates the floor (30 tiles)', harm='safe', gear=dict(),
      ops=SYR + CARPET15 + [('dispense', 'water', 15), ('inject',)],
      what='Carpet reagent in foam. Each foam tick turns every open solid floor tile it touches into carpet (no volume threshold). Pure cosmetics.',
      how='Needs 1u of real blood as a seed. The mutagen loop (unstable mutagen + a blood catalyst -> more blood) turns dispenser chemicals into 15u of blood, '
          'which is then reacted with space drugs into 30u of carpet.',
      caution='Make sure the seed blood comes from a healthy person: a disease in the blood data would be copied and evolved by the loop. The foam also '
              'carries 3.2u of blood per tile.',
      src='recipes/others.dm (carpet, mix_virus_2), reagents/other_reagents.dm (carpet expose_turf)'),
 dict(key='black-carpet-foam', short='Same but the floor becomes black carpet', payload='black carpet', title='Black carpet foam (30 tiles)', harm='safe', gear=dict(),
      ops=SYR + CARPET15 + [('dispense', 'welding fuel', 10), ('dispense', 'carbon', 10), ('dispense', 'hydrogen', 10), ('dispense', 'water', 15), ('inject',)],
      what='Same as carpet foam but the carpet is reacted with oil (carpet + oil -> black carpet), so every tile becomes black carpet. '
           'The carpet reagents only change a floor that is not already carpet, so the first reagent that touches a tile wins; here all the carpet has been converted so it is always black.',
      how='Adds 10u each of welding fuel, carbon and hydrogen (30u oil) which eats all 30u of plain carpet.',
      caution='As carpet foam.',
      src='recipes/others.dm (carpet/black)'),
 dict(key='carpet-foam-xl', short='Carpet over 120 tiles using the bluespace syringe + beaker', payload='carpet', title='Carpet foam XL - 120 tiles (bluespace beaker + bluespace syringe)', harm='safe', gear=dict(beaker='bluespace', syringe='bluespace'),
      ops=SYR60 + CARPET15 + [('dispense', 'water', 60), ('inject',)],
      what='The same carpet, but the trigger is 60u of surfactant instead of 15u, so the foam is four times as big.',
      how='Needs both upgrades: the bluespace syringe holds 60u of trigger, and 60 surfactant + 60 water + 31 payload + the injected 60 only fit a big beaker.',
      caution='As carpet foam.',
      src='recipes/others.dm (carpet, foam), planner gear tables'),
 dict(key='libital-fog', short='Smoke that heals brute damage on everyone breathing it', payload='libital', title='Brute-mender fog (libital smoke, 45 tiles)', harm='caution', gear=dict(),
      ops=PH + [('dispense', 'water', 5), ('dispense', 'chlorine', 5), ('dispense', 'welding fuel', 5), ('dispense', 'carbon', 5), ('dispense', 'hydrogen', 5),
                ('dispense', 'oxygen', 10), ('dispense', 'nitrogen', 10), ('dispense', 'potassium', 15), ('dispense', 'sugar', 15), ('inject',)],
      what='Chem smoke copies a share of its reagents straight into every breathing mob in the cloud (no internals or smoke protection). Libital in the '
           'blood heals about 1.5 brute per second and costs about 0.15 liver damage per second; it burns off at 0.2u per second. A mob that stays the whole 20 s '
           'can absorb up to a tile\'s worth (30u, around 150 s of healing).',
      how='Smoke is opaque and the payload is the same in every tile, so everyone in the cloud gets the same dose. The 10u of oil / 5u of phenol are inert (oil burns).',
      caution='The liver damage is real: do not run it repeatedly on the same patient. Dead people do not metabolise it.',
      src='effects_smoke.dm (smoke/chem smoke_mob), reagents/cat2_medicine_reagents.dm (libital)'),
 dict(key='aiuri-fog', short='Smoke that heals burn damage on everyone breathing it', payload='aiuri', title='Burn-mender fog (aiuri smoke, 45 tiles)', harm='caution', gear=dict(),
      ops=PH + [('dispense', 'nitrogen', 5), ('dispense', 'hydrogen', 25), ('dispense', 'sulfuric acid', 5), ('dispense', 'potassium', 15), ('dispense', 'sugar', 15), ('inject',)],
      what='Same idea with aiuri: heals about 1 burn per second, costs about 0.125 eye damage per second, burns off at 0.2u per second. A tile holds 20u '
           '(about 100 s of healing, up to roughly 12 eye damage for someone who stands in it for the whole cloud).',
      how='Hand-tuned from the planner design (which made 40u per tile) to halve the dose. The 10u of ammonia per tile is inert.',
      caution='Eye damage accumulates; blind or nearsighted people are the cost of a very large dose.',
      src='effects_smoke.dm (smoke/chem), reagents/cat2_medicine_reagents.dm (aiuri)'),
 dict(key='sorium', short='Throws everything within 6 tiles away from you', title='Sorium shockwave - throws everything away from you (range 6)', harm='danger', gear=dict(),
      ops=[('dispense', 'mercury', 10), ('dispense', 'oxygen', 10), ('dispense', 'nitrogen', 10), ('dispense', 'carbon', 10)],
      what='Sorium makes a vortex around the beaker: everything unanchored within the range (items and living mobs, not corpses) is thrown away from the '
           'centre. Targets closer than range-2 tiles are thrown (power range-distance), farther ones get one or two steps. You (the centre tile) are not moved.',
      how='Four clicks, the last one fires it. The range is clamp(sqrt(4 x mult), 1, 6), so mult 9 already reaches the 6 tile cap: more reagent is wasted, a '
          'bigger beaker does not help. Stabilizing agent in the beaker cancels it.',
      caution='People thrown into walls are injured. Only for scattering hostile mobs or clearing an item pile; Law 1 applies to everyone else in range.',
      src='recipes/pyrotechnics.dm (sorium), recipes.dm (goonchem_vortex)'),
 dict(key='ldm', short='Pulls everything within 6 tiles toward you', title='Dark matter pull - drags everything toward you (range 6)', harm='danger', gear=dict(),
      ops=[('dispense', 'stable plasma', 15), ('dispense', 'radium', 15), ('dispense', 'carbon', 15)],
      what='Liquid dark matter is the mirror image: the same vortex, but things are pulled toward the beaker. Good for gathering scattered items or a crowd '
           'into one spot.',
      how='Range is clamp(sqrt(3 x mult), 1, 6): mult 12 is enough for the cap, 15u of each ingredient gives mult 15. The last click fires it.',
      caution='Pulled/thrown mobs can be hurt by the landing. Do not use it on crew.',
      src='recipes/pyrotechnics.dm (liquid_dark_matter), recipes.dm (goonchem_vortex)'),
 dict(key='life-friendly', short='Spawns 1 to 3 random friendly mobs (needs donated ingredients)', title='Friendly life (bluespace beaker, donated ingredients)', harm='safe', gear=dict(beaker='bluespace'),
      ops=[('add', 'strange reagent', 90, 'donor bottle/vial'), ('add', 'synthflesh', 90, 'donor bottle/vial'), ('dispense', 'sugar', 90), ('heat', 380)],
      what='Strange reagent + synthflesh + sugar at 374 K or more spawns random friendly mobs (neutral faction): rand(1, mult) of them, with a flash for everyone '
           'who can see it. Each 30u of each ingredient is one mult, so a 300u beaker (270u of ingredients) allows mult 3 -> 1 to 3 mobs.',
      how='The donors are the catch: strange reagent (omnizine + holy water + unstable mutagen) and synthflesh (blood + carbon + libital) are not dispenser reagents '
          'in a normal round. Sugar comes from the dispenser. This entry only shows the bigger-beaker maths.',
      caution='The mobs are picked at random from the same friendly list the gold slime extract uses (every simple/basic animal flagged friendly-spawnable); they can still make a mess.',
      src='recipes/others.dm (life_friendly), recipes.dm (chemical_mob_spawn)'),
]

# reactions with interesting effects that cannot be built from dispenser reagents alone (found by the planner's decompose())
NOT_DISPENSER_ONLY = [
 ('life',        'Life (hostile)',    'strange reagent 30 + synthflesh 30 + blood 30 -> rand(1, mult) HOSTILE random mobs'),
 ('corgium',     'Corgium',           'nutriment, colorful reagent, strange reagent, blood (30u each) -> rand(1, mult) corgis'),
 ('butterflium', 'Butterflium',       'colorful reagent + omnizine + strange reagent + nutriment (1:1:1:1) -> rand(1, mult) butterflies'),
 ('ant_slurry',  'Ant slurry',        'ants 50 + synthflesh 20 + maintenance sludge 5 at 480 K -> rand(1, mult) ants'),
]


def all_recipes():
    """every recipe as (key, title, ops, gear_spec) - the original tuples plus the EXTRA dicts"""
    out = [(k, t, ops, {}) for k, t, _p, ops in RECIPES]
    out += [(r['key'], r['title'], r['ops'], r['gear']) for r in EXTRA]
    return out
