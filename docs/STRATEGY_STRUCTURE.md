# Strategy Structure & Configuration Pattern

Each strategy in `strategies/<name>/` is **self-contained**: it has all the docs, configs, and tests needed to deploy it independently to sandbox/live without touching other strategies.

---

## Folder Structure

```
strategies/<name>/
├── manifest.py              # The contract: stage, broker, universe, params, kill_criteria
├── config.py                # Runtime config: reads env vars, provides defaults
├── .env.example             # Template for secrets + strategy-specific env vars
├── README.md                # Quick hypothesis + key params explained
├── PLAYBOOK.md              # Detailed kill-switch rules, deployment ladder
├── STATUS.md                # Stage history, findings, kill log (human narrative)
├── strategy.py              # NautilusTrader Strategy class (backtest + live)
├── backtest.py              # Runner entry point: uv run python -m strategies.<name>.backtest
├── core.py                  # [optional] Signal + risk logic (e.g. PEAD)
├── research/                # [optional] Domain-specific research scripts
└── tests/                   # Unit tests for signal, strategy, risk logic
```

---

## The Four Essential Files

### 1. `manifest.py` — The Contract

```python
from core.manifest import Manifest, Stage, KillCriterion

MANIFEST = Manifest(
    name="strategy_name",
    stage=Stage.hypothesis,    # hypothesis → triage → vectorized → backtest → sandbox → live
    broker="fyers",
    strategy_path="strategies.strategy_name.strategy:StrategyClass",  # once stage >= backtest
    universe=["NSE:RELIANCE-EQ", ...],
    params={
        "param1": value1,
        "param2": value2,
        # ... all strategy params (shared between backtest, paper, live)
    },
    kill_criteria=[
        KillCriterion("drawdown", {"dd_limit": 0.15}),
        KillCriterion("trailing_winrate", {"window": 20, "floor": 0.45}),
    ],
    notes="One-liner description",
)
```

**Immutable.** Never tweak once live (tweaking = new in-sample fit).

### 2. `config.py` — Runtime Configuration

```python
import os
from pathlib import Path
from core import config as core_config
from strategies.<name>.manifest import MANIFEST

class StrategyConfig:
    def __init__(self):
        # Load from manifest (immutable params)
        for key, val in MANIFEST.params.items():
            setattr(self, key, val)
        
        # Load from environment (secrets + overrides)
        self.paper_trade_size_pct = float(os.getenv("STRATEGY_PAPER_TRADE_SIZE_PCT", "100"))
        self.log_dir = Path(os.getenv("STRATEGY_LOG_DIR", "~/.trader_zex/logs/strategy/")).expanduser()
        
        # Inherited from core
        self.broker = MANIFEST.broker
        self.initial_capital = core_config.BACKTEST_INITIAL_CAPITAL
```

**Self-contained.** Backtest, paper, sandbox, live all use the same config; only env vars differ (secrets, sizing).

### 3. `.env.example` — Secrets Template

```bash
# Fyers auth (shared by all strategies)
FYERS_FY_ID=...
FYERS_PIN=...
FYERS_TOTP_SECRET=...

# Strategy-specific
STRATEGY_PAPER_TRADE_SIZE_PCT=100    # or 10 for shadow live
STRATEGY_LOG_DIR=~/.trader_zex/logs/strategy/
```

**Never committed.** Users copy to `~/.env` on their host machine.

### 4. `README.md` — Human Narrative

- Hypothesis: one paragraph, edge + who's wrong + why it persists
- Configuration: key params explained, why they matter
- Failure regimes: what can go wrong
- Backtest workflow: data → signal → execute → metrics
- Deployment: paper → shadow → live gates

---

## Documentation Files (Moderate or Heavy)

### `PLAYBOOK.md` — Operational Runbook

Mirrors docs/PEAD_PLAYBOOK.md:
- The locked spec (do not tweak post-launch)
- Expected behavior (the prior, OOS haircuts)
- Pre-registered kill-criteria (mechanical, no overrides)
- Deployment ladder (paper → shadow → live gates + metrics)
- OOS interpretation (good signs vs red flags)

### `STATUS.md` — Live Journal

Updated per phase:
- Stage history (when, why, evidence)
- Findings log (negative results are important)
- Kill log (if dropped: which gate failed, numbers, decision)
- Pre-registered kill-criteria (locked before sandbox)

---

## How It Fits the Pipeline

```
hypothesis  → manifest + README
triage      → backtest results, IC/stats summary
vectorized  → signal.py validated (no look-ahead)
backtest    → strategy.py in core.backtest.engine, backtest.py runner
sandbox     → paper + shadow stages (PLAYBOOK.md ladder)
live        → kill-switch active (core.live.risk registry)
dropped     → STATUS.md post-mortem
```

---

## Deployment: Backtest to Live

### Backtest (no secrets)
```bash
uv run python -m strategies.<name>.backtest --date-from 2015-01-01 --date-to 2020-12-31
```
- config.py loads defaults from manifest
- No env vars needed

### Paper Trade (secrets + 100% sizing)
```bash
export $(cat ~/.env | xargs)
uv run python -m runners.sandbox <name>
```
- config.py loads manifest params + FYERS_* secrets + STRATEGY_PAPER_TRADE_SIZE_PCT=100
- Same strategy.py code, live data + simulated fills

### Shadow Live (secrets + 10% sizing)
```bash
STRATEGY_PAPER_TRADE_SIZE_PCT=10 uv run python -m runners.sandbox <name>
```
- 10% position sizing; real fills
- Kill-switch armed; gates in PLAYBOOK.md apply

### Full Live
```bash
STRATEGY_PAPER_TRADE_SIZE_PCT=100 uv run python -m runners.live <name> --i-am-sure
```
- 100% sizing; kill-switch active; core.live.risk evaluates manifest.kill_criteria
- core.live.monitor can inspect trades + halt state

---

## Key Conventions

1. **Manifest is single source of truth** for params, universe, kill-criteria
2. **config.py is self-contained** — reads env vars, provides runtime settings
3. **Secrets never in code** — only in ~/.env or Docker/EC2 injection
4. **Backtest = live** — same Strategy class, same params, different data/exec handlers
5. **Kill-switch is mechanical** — no discretion, pre-registered rules only
6. **README + PLAYBOOK** — humans understand the strategy, playbook locks the ops

---

## Example: Adding a New Strategy

1. Copy `strategies/_template/` → `strategies/new_strategy/`
2. Edit `manifest.py`: name, stage (start at hypothesis), params, kill-criteria
3. Edit `config.py`: add any strategy-specific env vars
4. Write `README.md`: hypothesis, edge, params, failure modes
5. Write `PLAYBOOK.md`: locked spec, kill-criteria, deployment ladder
6. Implement `signal.py` + `strategy.py` (when stage >= backtest)
7. Implement `backtest.py` runner (when stage >= backtest)
8. Update `STATUS.md` as you phase through the pipeline

Each stage has gates (runners enforce them). Move only when evidence is strong.

---

## References

- [PIPELINE.md](../docs/PIPELINE.md) — Full lifecycle + gates
- [STRATEGY_GUIDELINES.md](../docs/STRATEGY_GUIDELINES.md) — Research discipline
- [PEAD_PLAYBOOK.md](../docs/PEAD_PLAYBOOK.md) — Template playbook
- [core.manifest.py](../core/manifest.py) — Stage + KillCriterion API
- [core.live.risk.py](../core/live/risk.py) — Kill-criteria registry
