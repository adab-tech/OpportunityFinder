"""Preview-only launcher: runs the backend with cwd set to backend/ so the
`app` package resolves, without needing a shell script or execution-policy
changes. Not part of the deployed app (Dockerfile has its own CMD).
"""

import os
import runpy
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
# Respect whatever port the preview harness assigns via PORT (Settings.API_PORT
# already aliases to PORT) — never hardcode a port here, so autoPort can work.
os.environ.setdefault("API_PORT", os.environ.get("PORT", "8010"))
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)
runpy.run_path(os.path.join(BACKEND_DIR, "run.py"), run_name="__main__")
