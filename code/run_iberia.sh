#!/bin/bash
# Full pipeline for the Spanish events (region iberia), in dependency order: FIRMS, LSA SAF, EFFIS, Comparison.
# Usage: bash run_iberia.sh   (stops at the first failure; script output is discarded, outputs are written in place)
# Used as the regression check of Strategy v3.0 Steps 0 and 1.
set -e
C="$(cd "$(dirname "$0")" && pwd)"   # the code/ folder
PY="$C/../../master-thesis/bin/python"   # the master-thesis venv, next to the Latex folder
run() { echo ">>> [$(basename "$PWD")] $*"; "$PY" "$@" > /dev/null; }

cd "$C/Input Data FIRMS"
run scripts/common/00_inventory.py --region iberia; run scripts/common/01_merge.py
for s in 02_clean 03_overpasses 04_export 05_compare_v1; do run scripts/common/$s.py --region iberia; done
for e in larouco molezuelas; do
  for s in 01_select 02_products 03_figures 04_merge_check; do run scripts/event/$s.py --event $e; done
done
run scripts/event/05_gap_split.py --event larouco
run scripts/event/05_gap_split.py --event molezuelas --until 2025-08-12T14:57:00Z

cd "$C/Input Data LSA SAF"
run scripts/common/01_region_export.py --region iberia
run scripts/common/02_inventory.py --region iberia
for e in larouco molezuelas; do run scripts/event/01_event_seviri.py --event $e; run scripts/event/02_event_figures.py --event $e; done

cd "$C/Input Data EFFIS"
run scripts/common/01_inspect.py; run scripts/common/02_standardize.py
run scripts/common/03_overpass_coincidence.py --region iberia
run scripts/event/01_effis_reference.py --event larouco
run scripts/event/01_effis_reference.py --event molezuelas --records 277940 --neighbour-provinces Zamora León \
  --reported-end 2025-08-22T00:00:00Z --area-refs "Junta provisional, both provinces (registry comment)=31500" \
  "media / Copernicus estimate low (registry comment)=37000" "media / Copernicus estimate high (registry comment)=38000"
run scripts/event/02_firms_context_figure.py --event larouco
run scripts/event/02_firms_context_figure.py --event molezuelas --records 277940
run scripts/event/03_regression_check.py --event larouco
run scripts/event/04_find_records.py --event molezuelas --provinces Zamora Leon --start-from 2025-08-10T00:00:00Z \
  --start-to 2025-08-13T23:59:00Z --communes "Molezuelas de la Carballeda" "Una de Quintana" "Castrocalbon" \
  --name-parts Valderia Valduerna Jamuz

cd "$C/Input Comparison"
for e in larouco molezuelas; do
  for s in 01_check_inputs 02_observation_instants 03_t0_and_gaps 04_plots; do run scripts/event/$s.py --event $e; done
done
run scripts/cross/01_cross_event.py
run scripts/cross/02_figures.py
echo ALL OK
