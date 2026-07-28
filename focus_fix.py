import os, re, sys

if not (os.path.isdir("templates") and os.path.isdir("static")):
    sys.exit("Run this from the repo root.")
CSSF = "static/css/smackagram.css"
if not os.path.exists(CSSF):
    sys.exit("static/css/smackagram.css missing - run the earlier steps first.")

css = open(CSSF).read()

BLOCK = """
/* ---------------------------------------------------------------------------
   KEYBOARD FOCUS
   16 templates carried `input:focus{outline:none; border-color:var(--flare);}`.
   A 1px border tint is a weak indicator, and on a checkbox it is invisible -
   tabbing through the site, 12 of 40 elements showed no focus state at all.

   `html body` is here on purpose: it lifts specificity to (0,1,2) so this beats
   those `input:focus` rules at (0,1,1), which would otherwise win on source
   order since the page's inline <style> loads after this file. That avoids
   having to touch 16 templates, and avoids !important.

   :focus-visible (not :focus) means mouse users don't get a ring on every
   click - only keyboard users, and text fields, which browsers always treat
   as focus-visible.
--------------------------------------------------------------------------- */
html body :focus-visible{
  outline:2px solid var(--chalk);
  outline-offset:2px;
}
/* smack_chat and smack_lab suppress the ring with class-level selectors like
   `.search-input:focus` (0,2,0) and `input[type=text]:focus` (0,2,1), which
   outrank the rule above at (0,1,2). :is() takes the specificity of its
   heaviest argument, lifting this to (0,2,2) so it wins - still no !important. */
html body :is(a,button,input,select,textarea,[tabindex]):focus-visible{
  outline:2px solid var(--chalk);
  outline-offset:2px;
}
/* Checkboxes are small and sit inside dark rows; give them a little more. */
html body input[type=checkbox]:focus-visible,
html body input[type=radio]:focus-visible{
  outline:2px solid var(--gold);
  outline-offset:3px;
}
"""

if "KEYBOARD FOCUS" not in css:
    css += BLOCK
    print("  added focus-visible rules to smackagram.css")
else:
    print("  focus rules already present")

old = ".nav-drawer a:hover,.nav-drawer a:focus-visible{color:var(--flare); outline:none;}"
new = ".nav-drawer a:hover,.nav-drawer a:focus-visible{color:var(--flare);}"
if old in css:
    css = css.replace(old, new)
    print("  removed outline:none from the drawer link rule")

open(CSSF, "w").write(css)

css = open(CSSF).read()
checks = {
    "focus-visible block present": "html body :focus-visible" in css,
    "checkbox/radio focus styled": "input[type=checkbox]:focus-visible" in css,
    "drawer no longer suppresses its ring":
        ".nav-drawer a:hover,.nav-drawer a:focus-visible{color:var(--flare);}" in css,
    "high-specificity :is() rule present": ":is(a,button,input,select,textarea,[tabindex]):focus-visible" in css,
}
print()
for k, v in checks.items():
    print("  %-48s %s" % (k, "ok" if v else "FAIL"))
print("\nRESULT:", "ALL GOOD - safe to commit" if all(checks.values())
      else "PROBLEM - send this output to Claude")
