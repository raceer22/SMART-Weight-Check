#!/usr/bin/env bash
# Full reproducible build of the official packages (organisers): generate -> validate -> test -> baselines ->
# business-case example -> docs -> START_HERE.html -> package. Needs organizer/seeds.json (organiser-held seeds).
# Participants: generate your own world with any seed, e.g.
#   python -m europress_data.generate --profile quickstart --seed 12345 --out my_world
set -euo pipefail
cd "$(dirname "$0")/.."
SEEDS=${SEEDS:-organizer/seeds.json}
python3 scripts/run_with_stats.py europress_data.generate --profile quickstart --seed-file "$SEEDS" | tee reports/gen_quickstart.log
python3 -m europress_data.validate --profile quickstart
python3 scripts/run_with_stats.py europress_data.generate --profile competition --seed-file "$SEEDS" --workers 2 | tee reports/gen_competition.log
python3 -m europress_data.validate --profile competition
python3 -m pytest -p no:cacheprovider | tee reports/pytest.txt
python3 baselines/run_all.py quickstart > reports/baselines_quickstart.log
python3 baselines/run_all.py competition > reports/baselines_competition.log
python3 baselines/business_case.py competition --params configs/business_case_example_params.yaml --out reports/organizer_only/business_case_example > reports/business_case.log
python3 examples/run_queries.py data/competition/public > reports/example_queries_competition.log
python3 examples/weighing_accuracy_value.py data/competition/public > reports/weighing_accuracy_competition.log
python3 -m europress_data.docs_build
python3 scripts/make_start_here_html.py
python3 scripts/package_releases.py
