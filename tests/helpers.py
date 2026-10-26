import os, sys, json, tempfile, shutil, contextlib, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path: sys.path.insert(0, SRC)
import chemlib, planner

SNAPSHOT = os.path.join(SRC, 'chemdata.json')

def load_db():
    return chemlib.DB(json_path=SNAPSHOT)

def mutated_snapshot(tmpdir, mutate):
    """copy chemdata.json to tmpdir after calling mutate(dict); returns the new path"""
    with open(SNAPSHOT) as fh: d = json.load(fh)
    mutate(d)
    p = os.path.join(tmpdir, 'snap.json')
    with open(p, 'w') as fh: json.dump(d, fh)
    return p

def make_mini_source(tmpdir, ammonia=(3, 1), extra=''):
    """a tiny fake game tree: one dme, one recipe file (enough for chemlib.DB(src=...) to parse)"""
    rdir = os.path.join(tmpdir, 'code/modules/reagents/chemistry/recipes'); os.makedirs(rdir)
    with open(os.path.join(tmpdir, 'tgstation.dme'), 'w') as fh: fh.write('#include "code\\modules\\reagents\\chemistry\\recipes\\mini.dm"\n')
    with open(os.path.join(rdir, 'mini.dm'), 'w') as fh: fh.write(
        '/datum/reagent/hydrogen\n\tname = "Hydrogen"\n/datum/reagent/nitrogen\n\tname = "Nitrogen"\n/datum/reagent/ammonia\n\tname = "Ammonia"\n'
        '/datum/chemical_reaction/ammonia\n\tresults = list(/datum/reagent/ammonia = 3)\n'
        '\trequired_reagents = list(/datum/reagent/hydrogen = %d, /datum/reagent/nitrogen = %d)\n' % ammonia + extra)
    return tmpdir

@contextlib.contextmanager
def tmp():
    d = tempfile.mkdtemp()
    try: yield d
    finally: shutil.rmtree(d, ignore_errors=True)

def capture(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rv = fn(*a, **k)
    return rv, buf.getvalue()
