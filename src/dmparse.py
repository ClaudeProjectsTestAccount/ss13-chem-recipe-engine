"""
dmparse.py - minimal DreamMaker (DM) source reader for SS13 chemistry data.

It does NOT run DM. It reads the *declarative* parts of Monkestation's
chemistry files (reagent definitions + chemical_reaction definitions) and the
*text* of their on_reaction() procs so an engine can classify side effects.

Source of truth: the tgstation.dme include order (compile order decides
BYOND's subtypesof() order, which decides reaction priority in holder.dm).
"""
import re, os, ast

T0C, T20C = 273.15, 293.15

def strip_comments(src: str) -> str:
    out, i, n = [], 0, len(src)
    in_str = None
    while i < n:
        c = src[i]
        if in_str:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == in_str: in_str = None
            i += 1; continue
        if c == '"':
            in_str = '"'; out.append(c); i += 1; continue
        if src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            if j < 0: break
            out.append('\n' * src.count('\n', i, j))
            i = j + 2; continue
        out.append(c); i += 1
    return ''.join(out)

def logical_lines(src: str):
    """join backslash continuations and unbalanced-paren continuations"""
    raw = src.replace('\r', '').split('\n')
    lines, cur, depth = [], '', 0
    for ln in raw:
        s = ln.rstrip()
        if cur == '':
            indent = len(s) - len(s.lstrip('\t'))
            cur_indent = indent
        if s.endswith('\\'):
            cur += s[:-1] + ' '
            continue
        cur += s.strip() if cur else s
        depth += s.count('(') - s.count(')')
        if depth > 0:
            cur += ' '
            continue
        depth = 0
        lines.append((cur_indent, cur.strip()))
        cur = ''
    if cur: lines.append((cur_indent, cur.strip()))
    return lines

PAIR = re.compile(r'(/datum/reagent[\w/]*)\s*=\s*([-+0-9.*/() ]+?)\s*(?=,|\)|$)')

def parse_pairs(val: str):
    res = {}
    for m in PAIR.finditer(val):
        expr = m.group(2).strip()
        try:
            res[m.group(1)] = float(eval(expr, {'__builtins__': {}}, {}))
        except Exception:
            res[m.group(1)] = float('nan')
    return res

MACROS = {}
def load_macros(root):
    """simple numeric #defines from code/__DEFINES (resolved iteratively)"""
    import glob
    raw = {}
    for f in glob.glob(os.path.join(root, 'code', '__DEFINES', '**', '*.dm'), recursive=True):
        for ln in open(f, encoding='utf-8', errors='replace'):
            m = re.match(r'#define\s+(\w+)\s+(.+?)\s*(?://.*)?$', ln.rstrip())
            if m and '(' not in m.group(1):
                raw[m.group(1)] = m.group(2)
    raw.update({'T0C': str(T0C), 'T20C': str(T20C)})
    MACROS.update({})
    for _ in range(8):
        for k, v in raw.items():
            if k in MACROS: continue
            e = v
            for name in sorted(re.findall(r'[A-Za-z_]\w*', e), key=len, reverse=True):
                if name in MACROS: e = re.sub(r'\b%s\b' % name, '(%s)' % MACROS[name], e)
            try:
                MACROS[k] = float(eval(e, {'__builtins__': {}}, {}))
            except Exception:
                pass
    return MACROS

def parse_num(val: str):
    v = val.strip()
    for name in sorted(set(re.findall(r'[A-Za-z_]\w*', v)), key=len, reverse=True):
        if name in MACROS: v = re.sub(r'\b%s\b' % name, '(%r)' % MACROS[name], v)
    try:
        return float(eval(v, {'__builtins__': {}}, {}))
    except Exception:
        return None

class Def:
    def __init__(self, path, order, file):
        self.path, self.order, self.file = path, order, file
        self.vars = {}          # name -> raw string
        self.procs = {}         # procname -> body text
        self.pind = {}          # procname -> [(indent, text)] (same lines, indentation kept: lets effects.py see if/else nesting)
        self.parent_path = None

def _split_assign(text):
    """split 'name = value' at the first top-level '=' (not ==, <=, >=, !=)"""
    depth = 0
    for i, c in enumerate(text):
        if c in '([{': depth += 1
        elif c in ')]}': depth -= 1
        elif c == '=' and depth == 0:
            prev = text[i-1] if i else ''
            nxt = text[i+1] if i+1 < len(text) else ''
            if prev in '<>!=' or nxt == '=':
                continue
            return text[:i].strip(), text[i+1:].strip()
    return None

def parse_file(path, rootkey, defs, order_counter, root=None):
    """collect /datum/<rootkey>... definitions: var assignments + proc bodies"""
    src = strip_comments(open(path, encoding='utf-8', errors='replace').read())
    root = root or ('/datum/' + rootkey)
    cur = None
    body = None            # list collecting a proc body
    pbody = None
    for indent, text in logical_lines(src):
        if not text or text.startswith('#'):
            continue
        if body is not None:
            if indent >= 1:
                body.append(text); pbody.append((indent, text)); continue
            body = None
        if indent == 0 and text.startswith('/'):
            mproc = re.match(r'(/(?:datum|obj|mob)/[\w/]*?)/(?:proc/)?(\w+)\s*\(.*\)\s*$', text)
            asg = _split_assign(text)
            if asg and asg[0].startswith(root):
                lhs, rhs = asg
                tp, _, name = lhs.rpartition('/')
                name = name if not name.startswith('var') else name
                d = defs.get(tp) or defs.setdefault(tp, Def(tp, next(order_counter), path))
                d.vars[name] = rhs
                cur = d
            elif mproc and mproc.group(1).startswith(root):
                tp, name = mproc.group(1), mproc.group(2)
                d = defs.get(tp) or defs.setdefault(tp, Def(tp, next(order_counter), path))
                body = d.procs.setdefault(name, []); pbody = d.pind.setdefault(name, [])
                cur = d
            elif re.match(r'/(?:datum|obj|mob)/[\w/]+$', text) and text.startswith(root):
                d = defs.get(text) or defs.setdefault(text, Def(text, next(order_counter), path))
                cur = d
            else:
                cur = None
            continue
        if cur is not None and indent == 1:
            asg = _split_assign(text)
            if asg and not re.match(r'(if|for|while|return|else|switch|var/[\w/]+\s+\w+\s*$)', text):
                name = asg[0].split('/')[-1].strip()
                cur.vars[name] = asg[1]
                continue
            mp2 = re.match(r'(?:proc/)?(\w+)\s*\(.*\)\s*$', text)
            if mp2:
                body = cur.procs.setdefault(mp2.group(1), []); pbody = cur.pind.setdefault(mp2.group(1), [])
    return defs

def resolve_chain(defs, path, key):
    """Walk DM inheritance by path prefix: value from nearest ancestor that sets it."""
    p = path
    while True:
        d = defs.get(p)
        if d is not None and key in d.vars:
            return d.vars[key], p
        if p.count('/') <= 2: return None, None
        p = p.rsplit('/', 1)[0]

def dme_order(dme_path, root):
    files = []
    for ln in open(dme_path, encoding='utf-8', errors='replace'):
        m = re.match(r'#include "([^"]+)"', ln.strip())
        if m:
            files.append(m.group(1).replace('\\', '/'))
    return files
