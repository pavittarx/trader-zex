#!/bin/zsh
# Phase 1/2/4 file moves for the multi-strategy restructure (one-shot, then delete me).
# Run from repo root. Each phase: moves + import rewrite + test gate.
set -e

echo "=== Commit Phase 0 + new pipeline machinery ==="
git add -A
git commit -m "feat: PEAD merge + multi-strategy pipeline machinery

Phase 0: PEAD branch import-rebased onto core/ (pead_core, NT strategy,
TOTP headless auth, ENVIRONMENTS/PLAYBOOK docs, PEAD_* config, pyotp).
Phase 3: core/research harness (data+parquet cache, cost, stats,
event_study, report, events_nse); scripts deduped onto it.
Phase 5: runners/ (list, backtest, sandbox, live) with stage gates.
Phase 6: core/live (KillSwitch registry, persisted halt state, monitor).
Plus: core/manifest.py, core/brokers (DataAdapter + Fyers impl),
strategies/ (pead@sandbox, hmm_confluence@backtest, 4 dropped w/
post-mortems, _template), docs/PIPELINE.md, tests (90 passing).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

echo "=== Phase 1: backtest/ -> core/backtest/, signals -> core/signals/, fyers -> core/brokers/fyers/client.py ==="
git mv backtest core/backtest
mkdir -p core/signals
git mv core/hmm_model.py core/structure.py core/confluence.py core/signals/
git mv core/fyers_client.py core/brokers/fyers/client.py
git mv core/auth.py core/brokers/fyers/auth.py
touch core/signals/__init__.py && git add core/signals/__init__.py

# import rewrites
grep -rl --include='*.py' -e 'from backtest' -e 'import backtest' -e 'core.fyers_client' -e 'core import auth' -e 'core.hmm_model' -e 'core.structure' -e 'core.confluence' -e 'core import fyers_client' . \
  | grep -v '.venv' | grep -v '.git/' | while read f; do
  sed -i '' \
    -e 's/from backtest\./from core.backtest./g' \
    -e 's/^import backtest$/import core.backtest as backtest/' \
    -e 's/from backtest import/from core.backtest import/g' \
    -e 's/from core\.fyers_client import/from core.brokers.fyers.client import/g' \
    -e 's/from core import auth/from core.brokers.fyers import auth/g' \
    -e 's/from core\.hmm_model import/from core.signals.hmm_model import/g' \
    -e 's/from core\.structure import/from core.signals.structure import/g' \
    -e 's/from core\.confluence import/from core.signals.confluence import/g' \
    "$f"
done
# auth's internal "from core import config" stays valid; fyers client imports auth:
sed -i '' 's/^from core import auth$/from core.brokers.fyers import auth/' core/brokers/fyers/client.py || true
# pead_strategy etc reference backtest.* via strategies shims:
sed -i '' 's/from backtest\.pead_strategy/from core.backtest.pead_strategy/' strategies/pead/strategy.py
sed -i '' 's/from backtest\.strategy/from core.backtest.strategy/' strategies/hmm_confluence/strategy.py
sed -i '' 's/from backtest\.__main__/from core.backtest.__main__/' strategies/hmm_confluence/backtest.py
# poe task
sed -i '' 's|backtest  = "python -m backtest"|backtest  = "python -m core.backtest"|' pyproject.toml

uv run pytest -q -x
uv run python -c "import core.backtest.engine, core.signals.hmm_model, core.brokers.fyers.client, apps if False else 0"
git add -A
git commit -m "refactor: core/ platform sub-packages (backtest, signals, brokers/fyers)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

echo "=== Phase 2: apps/ ==="
mkdir -p apps
git mv core/screener.py core/ranker.py core/universe.py core/main.py apps/
touch apps/__init__.py && git add apps/__init__.py
grep -rl --include='*.py' -e 'core.screener' -e 'core.ranker' -e 'core.universe' -e 'core.main' . \
  | grep -v '.venv' | grep -v '.git/' | while read f; do
  sed -i '' \
    -e 's/from core\.screener import/from apps.screener import/g' \
    -e 's/from core\.ranker import/from apps.ranker import/g' \
    -e 's/from core\.universe import/from apps.universe import/g' \
    "$f"
done
sed -i '' \
  -e 's|screen    = "python -m core.main"|screen    = "python -m apps.main"|' \
  -e 's|universe  = "python -m core.main --universe"|universe  = "python -m apps.main --universe"|' \
  -e 's|rank      = "python -m core.ranker"|rank      = "python -m apps.ranker"|' \
  -e 's|auth      = "python -m core.auth"|auth      = "python -m core.brokers.fyers.auth"|' \
  pyproject.toml
uv run pytest -q -x
git add -A
git commit -m "refactor: operator apps (screener, ranker, universe, main CLI) -> apps/

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

echo "=== Phase 4: strategy implementations into their folders ==="
git rm -f strategies/pead/strategy.py strategies/hmm_confluence/strategy.py  # the shims
git mv core/backtest/pead_strategy.py strategies/pead/strategy.py
git mv core/backtest/strategy.py strategies/hmm_confluence/strategy.py
git mv core/pead_core.py strategies/pead/core.py
mkdir -p strategies/pead/research strategies/gap_fade/research strategies/reversal/research strategies/breakout/research strategies/continuation/research strategies/hmm_confluence/research
git mv scripts/pead_event_ic.py scripts/pead_backtest.py scripts/pead_liquidity.py scripts/pead_signals.py scripts/pead_fundamental.py scripts/pead_surprise.py scripts/pead_nt_backtest.py strategies/pead/research/
git mv scripts/gap_fade_test.py scripts/gap_fade_intraday.py strategies/gap_fade/research/
git mv scripts/reversal_test.py strategies/reversal/research/
git mv scripts/breakout_test.py strategies/breakout/research/
git mv scripts/continuation_limit.py strategies/continuation/research/
git mv scripts/validate_confluence.py scripts/check_label_stability.py strategies/hmm_confluence/research/
git mv tests/test_pead_core.py strategies/pead/tests/test_pead_core.py 2>/dev/null || { mkdir -p strategies/pead/tests && git mv tests/test_pead_core.py strategies/pead/tests/; }
for d in pead gap_fade reversal breakout continuation hmm_confluence; do
  touch strategies/$d/research/__init__.py; git add strategies/$d/research/__init__.py
done
touch strategies/pead/tests/__init__.py && git add strategies/pead/tests/__init__.py
# fix cross-references to moved scripts
grep -rl --include='*.py' 'scripts.pead_event_ic' . | grep -v '.venv' | while read f; do
  sed -i '' 's/from scripts\.pead_event_ic import/from strategies.pead.research.pead_event_ic import/g' "$f"
done
grep -rl --include='*.py' 'core.pead_core\|core import pead_core' . | grep -v '.venv' | while read f; do
  sed -i '' \
    -e 's/from core\.pead_core import/from strategies.pead.core import/g' \
    -e 's/from core import pead_core/from strategies.pead import core as pead_core/g' \
    "$f"
done
sed -i '' 's/from backtest\.pead_strategy import/from strategies.pead.strategy import/g; s/from core\.backtest\.pead_strategy import/from strategies.pead.strategy import/g' strategies/pead/research/pead_nt_backtest.py strategies/pead/backtest.py 2>/dev/null || true
uv run pytest -q -x
git add -A
git commit -m "refactor: strategy implementations + research scripts into strategies/<name>/

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

echo "=== DONE — run full verification ==="
uv run pytest -q
uv run python -m runners.list
echo "All phases complete. Delete this script: git rm scripts/_restructure_moves.sh"
