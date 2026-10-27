"""
gear.py - what worn gear does against foam and chem smoke, read from the clothing source.
  foam  : reagents.expose(mob, VAPOR, fraction) -> the absorbed amount is reduced by `getarmor(null, BIO)/100`, the mean over the six body parts of
          100 * (1 - prod(1 - bio_armor_of_each_garment_covering_that_part)).
  smoke : a carbon mob breathes the cloud in unless an internals tank is open, it has TRAIT_NOBREATH, or its mask / glasses / head item has
          BLOCK_GAS_SMOKE_EFFECT.  Armour does nothing against the breathed part.
Writes data/gear_protection.json (items with bio armour, the smoke flag, or an internals flag).   python3 src/gear.py
"""
import os, re, json, glob
import dmparse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'data', 'gear_protection.json')
# bodypart.body_part is HEAD / CHEST / ARM_LEFT / ARM_RIGHT / LEG_LEFT / LEG_RIGHT only, so GROIN, HANDS and FEET flags never match a body part in check_armor()
PARTS = {'HEAD': {'head'}, 'CHEST': {'chest'}, 'GROIN': set(), 'ARMS': {'l_arm', 'r_arm'}, 'HANDS': set(), 'LEGS': {'l_leg', 'r_leg'}, 'FEET': set(),
         'FULL_BODY': {'head', 'chest', 'l_arm', 'r_arm', 'l_leg', 'r_leg'}, }
BODY_PARTS = ('head', 'chest', 'l_arm', 'r_arm', 'l_leg', 'r_leg')

def covered(expr, default):
    if not expr: return set(default)
    out = set()
    for w in re.findall(r'[A-Z_]+', expr):
        out |= PARTS.get(w, set())
    return out

def slot_of(path):
    for k in ('suit', 'head', 'mask', 'glasses', 'under', 'gloves', 'shoes', 'neck'):
        if path.startswith('/obj/item/clothing/' + k): return k
    return None

DEFAULT_COVER = {'suit': 'CHEST|GROIN|LEGS|ARMS', 'head': 'HEAD', 'under': 'CHEST|GROIN|LEGS|ARMS', 'gloves': 'HANDS', 'shoes': 'FEET', 'mask': 'HEAD', 'glasses': 'HEAD', 'neck': ''}

def extract(root):
    items, armor = {}, {}
    counter = iter(range(10 ** 7))
    files = glob.glob(os.path.join(root, 'code', 'modules', 'clothing', '**', '*.dm'), recursive=True) + glob.glob(os.path.join(root, 'monkestation', 'code', 'modules', 'clothing', '**', '*.dm'), recursive=True)
    for f in files:
        try:
            dmparse.parse_file(f, 'armor', armor, counter, root='/datum/armor')
            dmparse.parse_file(f, 'clothing', items, counter, root='/obj/item/clothing')
        except Exception as e:
            print('skip', f, e)
    out = {}
    for p, d in items.items():
        sl = slot_of(p)
        if not sl: continue
        at, _ = dmparse.resolve_chain(items, p, 'armor_type')
        bio = 0.0; fire = 0.0
        if at:
            at = at.strip()
            b, _ = dmparse.resolve_chain(armor, at, 'bio'); bio = dmparse.parse_num(b) or 0.0 if b else 0.0
            fr, _ = dmparse.resolve_chain(armor, at, 'fire'); fire = dmparse.parse_num(fr) or 0.0 if fr else 0.0
        flags, _ = dmparse.resolve_chain(items, p, 'clothing_flags'); flags = flags or ''
        bp, _ = dmparse.resolve_chain(items, p, 'body_parts_covered')
        nm, _ = dmparse.resolve_chain(items, p, 'name')
        smoke = 'BLOCK_GAS_SMOKE_EFFECT' in flags
        intern = 'MASKINTERNALS' in flags or 'HEADINTERNALS' in flags
        if bio <= 0 and not smoke and not intern: continue
        if d.vars.get('name') is None and nm is None: continue
        out[p] = dict(name=(nm or p.rsplit('/', 1)[-1]).strip('"'), slot=sl, bio=bio, fire=fire, smoke_block=smoke, internals=intern,
                      covers=sorted(covered(bp, covered(DEFAULT_COVER[sl], set()))))
    return out

def protection(worn, key='bio'):
    """worn: list of gear dicts -> blocked fraction (mean over 6 body parts of 1-prod(1-armour/100)); key 'bio' = foam absorption, 'fire' = burning damage"""
    tot = 0.0
    for part in BODY_PARTS:
        keep = 1.0
        for g in worn:
            if part in g['covers']: keep *= (100 - min(g[key], 100)) / 100.0
        tot += 1 - keep
    return tot / len(BODY_PARTS)

def main():
    import chemlib
    root = chemlib.SRC
    out = extract(root)
    with open(OUT, 'w') as fh: json.dump(out, fh, indent=0, sort_keys=True)
    print('wrote %s: %d garments (bio armour / smoke flag / internals flag)' % (OUT, len(out)))

if __name__ == '__main__': main()
