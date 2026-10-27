# Project rules (ss13-chem-recipe-engine)

## Visual consistency comes first (standing rule from the owner)
A unified look matters more than any single widget. Whenever code defines a **visual style or UI behaviour** (buttons, search bars, tooltips, menus/collapsibles, chips, cards, banners...):
1. **Use one modular implementation** (a small function plus one CSS block) and call it everywhere that kind of element appears. Never write a second copy of a style or behaviour inline.
2. **Look for an existing module first.** If one exists, extend it; if a new element needs the same look, route it through the module. If none exists, create the module before using it, then convert the existing one-off uses to it.
3. When you change how a kind of element looks or reacts, change the module, not its callers. Check that every instance still looks right (light and dark, phone width).
4. Every expandable/clickable element needs visible mouse-over feedback and its own consistent look per class of element, so different kinds of control are distinguishable at a glance.

### UI module registry (src/page_template.html; keep this list current)
- **Tooltips**: `tip(element, text)` + the `#tip` CSS block ("UI MODULE: tooltips"). The ONLY way to make a tooltip. Never use the `title` attribute or `.title=` for tooltips. Style: big bold italic serif text, solid gold bevelled border, dark fill; one delegated listener draws it (mouse, keyboard focus, touch). Change the look in the `--tip-*` variables / `#tip` rules only.
- **Menu ladder** (collapsibles): section `details.group` (big hover-reactive button) > gear tier `details.tier` (indigo band) > recipe group `details.type` (amber tab) > recipe `details.recipe` (blue card); guides `details.guide` (green dashed). Add a new menu level by giving it its own class in this ladder.
- **One-open-menu rule**: `menus` module + `MENU_KINDS` list. Sibling menus of the same kind are exclusive: clicking one open closes the others (and the menus inside them); programmatic opens (Expand all, search, deep links) are exempt. A new kind of menu only needs adding to `MENU_KINDS`; never write per-menu open/close logic.
- **Overdose / organ warnings**: `statspanel.od_block` / `organ_warn` + `odPanel()`; the box renders only when something is reached.
- **Chips**: `chip(text, cls)`; chip rows `chipRow(list)`.

Tests: `tests/test_ui_modules.py` fails if a tooltip is made with the title attribute or if the tooltip module is missing.

## Other standing rules
- Recipe planning and formatting logic lives in the tool (`src/`), not hand-done per recipe.
- Rebuild the page with `python3 src/chemcli.py book rebuild`; never hand-edit `docs/index.html`. `export MONKE_SRC=<path to Monkestation2.0 checkout>` first.
- When a recipe is reported broken, run `src/codecheck.py` first. Never schedule it.
- Don't treat a borg running out of power as a concern.
- Keep the "SS13 Cyborg Notes" doc and `docs/CHEM_NOTES.md` updated on major changes.
