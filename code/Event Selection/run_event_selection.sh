#!/bin/bash
# Event selection (Strategy v3.0, Step 2), in order. Stops at the first failure.
# Usage: bash run_event_selection.sh            (from anywhere)
#        bash run_event_selection.sh --query    (also re-query the official US discovery times, needs internet)
set -e
ES="$(cd "$(dirname "$0")" && pwd)"                    # code/Event Selection
PY="$ES/../../../master-thesis/bin/python"             # the master-thesis venv, next to the Latex folder
run() { echo ">>> $*"; "$PY" "$@"; }

# 1. global FIRMS cleaning and 1 km clusters (same method as the Spanish events), about 2 min
cd "$ES/../Input Data FIRMS"
run scripts/common/02_clean.py --region world > /dev/null

# 2. official US discovery times (optional; the result is kept in processed/)
cd "$ES"
[ "$1" = "--query" ] && run scripts/00_wfigs_query.py

# 3. screen, criteria, overpasses, figures
run scripts/01_screen_firms.py > /dev/null
run scripts/02_criteria.py > /dev/null
run scripts/03_overpasses.py > /dev/null
run scripts/04_figures.py > /dev/null
echo "done: processed/ and figures/ updated"
