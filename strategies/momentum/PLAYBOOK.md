# Momentum Deployment Playbook

Philosophy: test before deployment, then trust the mechanics. Pre-register all kill-switch rules so the halt decision is mechanical, not discretionary.

---

## The Locked Spec

**Do NOT tweak once live** — tweaking = new in-sample fit, nullifies edge.

- **Universe:** Nifty 500 constituents, point-in-time (use NSE constituent history, not current list)
- **Ranking:** 12-month total return, excluding past 1 month
- **Quintile:** Top 20% (approx. 100 stocks)
- **Rebalance:** Every Friday EOD (3:30 PM IST)
- **Position sizing:** Vol-weighted within quintile (optional; try equal-weight first)
- **Turnover gate:** Only trade if portfolio weight drift > 1.5%
- **Execution:** Next-day open or VWAP (backtest assumes next-day open at 09:15 IST)
- **Holding:** N/A (portfolio is always held to next rebalance)

---

## Expected Behavior (The Prior)

> **In-sample:** Sharpe ~0.6–0.8, maxDD −10–15%, win rate ~55–60%, net +1–3% annually post-costs.  
> **Forward (OOS):** Assume 1 SE haircut; Sharpe ~0.3–0.5. If below, kill.

---

## KILL-CRITERIA (Pre-Registered)

Hit **any one** → immediate halt. No overrides.

### 1. Hard Drawdown Stop
- **Rule:** Strategy equity −15% from its peak (1.5× in-sample expected maxDD)
- **Action:** Halt immediately. Close all positions at market close EOD.
- **Rationale:** Edge decay; market regime break; costs exceed model → time to re-evaluate

### 2. Rolling Win Rate Collapse
- **Rule:** Compute trailing-20 *rebalance-week* win rate (fraction of weeks with positive P&L)
- **Trigger:** Win rate < 45% (below the win rate needed to cover costs)
- **Action:** Halt; switch to cash
- **Rationale:** Edge no longer pays for execution + slippage

### 3. Realized Slippage Exceeds Model
- **Rule:** Track actual fill prices vs VWAP model each rebalance
- **Trigger:** Average realized slippage > 2× model expectation over 8-week window
- **Action:** Halt; investigate execution quality
- **Rationale:** Illiquidity or market condition change; assumptions broken

### 4. Mean Return Below Prior (Significance)
- **Rule:** After ≥ 10 weeks live, compute realized mean weekly return
- **Trigger:** Realized mean < (prior_weekly_mean − 2 SE)
- **Action:** Halt; re-run IC test
- **Rationale:** Edge weaker than expected; time decay or crowding

### 5. Rolling IC Negative
- **Rule:** Quarterly, re-compute Spearman IC (12-1 rank vs realized next-month return) over ~13-week window
- **Trigger:** Rolling IC < 0
- **Action:** Halt immediately; fundamental regime break
- **Rationale:** Signal has flipped

---

## Deployment Ladder (Escalate Only on Evidence)

### Stage 1: Backtest + Walk-Forward (3–4 weeks)
- Backtest 2005–present
- Walk-forward: train 2005–2015 → validate 2015–2020 → test 2020–present
- **Gate:** OOS Sharpe ≥ 0.3, maxDD ≤ 20%, no kill-criterion fires
- **Output:** Baseline stats, parameter sensitivity plots

### Stage 2: Paper Trade (2–3 months, ≥ 10 rebalances)
- Live Fyers EOD feed → weekly 12-1 compute
- Generate target portfolio (top quintile)
- Simulate fills at next-day open (VWAP forecast)
- **Gate:** Realized metrics match backtest ±1 SE
  - Win rate 50–60%
  - Mean weekly return ≥ +0.1% (post-costs)
  - No kill-criterion fires
- **Output:** TCA report, realized cost breakdown

### Stage 3: Shadow Live (1–3 months, ≥ 8 rebalances)
- Place 10% position sizing in live market
- Real fills from Fyers
- Track TCA (actual vs model), slippage, execution quality
- **Gate:**
  - Realized fills within 2× model std dev
  - Win rate ≥ 48% (allows small margin below backtest)
  - Drawdown ≤ 12% (less than hard stop)
  - No kill-criterion fires
- **Output:** Live TCA reconciliation, slippage breakdown

### Stage 4: Full Live
- **Gate:** All shadow metrics within thresholds; confidence ≥ 80%
- Position sizing: scale from 10% → 50% over 2 weeks, then 50% → 100% over 2 more weeks
- **Kill-switch active:** Any criterion fires → halt, close positions
- **Monitoring:** Daily P&L, trailing 20-week win rate, monthly IC re-check

---

## Position Sizing for a Transient Edge

- Assume edge decays; assume we'll pull the plug at some point (that's OK)
- Use fixed fractional sizing (NOT Kelly), e.g., 5–10% per position
- Size so the hard-drawdown kill-stop (−15%) is an acceptable loss
- Example: $100k portfolio, −15% kill-stop = −$15k acceptable loss; invest up to $100k across all positions

---

## OOS Interpretation

**Good signs (edge is real):**
- Sharpe ≥ 0.3 OOS (confident; in-sample Sharpe ~0.6–0.8 → 1SE haircut)
- No parameter sensitivity cliff (12-1 window works across 10-2 to 14-0)
- Win rate stable across regimes

**Red flags (edge is overfitted):**
- Sharpe < 0.1 OOS → kill
- Sharp peak in param sensitivity (e.g., only 12-1 works, 11-1 and 13-1 fail) → rethink
- Win rate collapses in a specific regime → edge regime-dependent, risky

---

## What Success Looks Like

A clean run of **3+ months live with win rate > 50%** and no kill-switch fires is a win.
Even if the edge eventually decays (month 6), the discipline is to exit before it costs more than the pre-agreed −15%.

Permanent alpha is rare; temporary alpha deployed systematically is the game.

---

## Files

| File | Purpose |
|------|---------|
| `manifest.py` | Params, kill_criteria, stage, broker (the contract) |
| `config.py` | Runtime universe, rebalance schedule, cost model, sizing logic |
| `signal.py` | 12-1 momentum compute (expanding window) |
| `strategy.py` | NautilusTrader Strategy (backtest + live codepath) |
| `backtest.py` | Runner entry: `uv run python -m strategies.momentum.backtest` |

---

## Related

- [PIPELINE.md](../../docs/PIPELINE.md) — Full lifecycle
- [PEAD_PLAYBOOK.md](../../docs/PEAD_PLAYBOOK.md) — Template (similar kill-criteria discipline)
- [core.live.risk.py](../../core/live/risk.py) — Criterion registry (auto-enforced)
