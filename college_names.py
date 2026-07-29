import os, sys, ast

if not (os.path.isdir("templates") and os.path.isdir("services")):
    sys.exit("Run this from the repo root.")
JSF = "static/js/smackagram.js"
CSSF = "static/css/smackagram.css"
for f in (JSF, CSSF):
    if not os.path.exists(f):
        sys.exit(f + " missing - run the earlier steps first.")

import urllib.request
MODULE_URL = "https://raw.githubusercontent.com/andyweissberg16-star/smackagram/main/services/team_display.py"
print("  NOTE: this script writes services/team_display.py in full - see below")
