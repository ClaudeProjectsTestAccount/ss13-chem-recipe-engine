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
