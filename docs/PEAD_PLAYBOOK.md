# PEAD Deployment Playbook — trade it small, kill it fast

Philosophy: all edges decay. We do NOT need PEAD to work forever — we need to
deploy it while it works and **pull the plug the moment it breaks, by pre-defined
rule, not gut feel.** This playbook locks the spec and the failure criteria *in
advance* so the kill decision is mechanical.

Basis: `PEAD_THESIS.md` — in-sample (one ~2yr regime) the lower-liquidity 20-day
form shows Sharpe ~1.3, maxDD −4%, net +1–2%/trade. NOT cross-regime validated.
Treat every number below as a *prior to be confirmed forward*, not a promise.

---

## The locked spec (do not tweak once live — tweaking = new in-sample fit)
- **Universe:** liquid-but-not-blue-chip NSE names, median daily traded value
  ~₹100–300 cr/day (the segment where the edge concentrated). Fixed list at
  launch; no mid-flight additions.
- **Trigger:** company reports earnings → reaction day = first session after the
  announcement. Require **|reaction-day return| ≥ 2%**.
- **Entry:** at the reaction-day close. Long if reaction up, short if down
  (shorts via F&O where the name has liquid futures; else long-only).
- **Hold:** 20 trading days, exit at close. No discretionary early exit except
  the stop below.
- **Sizing:** equal risk per event; start tiny (see ladder). Max ~8–10 concurrent
  positions; cap any one name ≤ 10% of capital; gross ≤ 80%.

## Expected behaviour (the prior — what "working" looks like)
- Net ~+1–2% per trade (20-day), win rate ~52–55%, Sharpe ~1 (wide error bars).
- Sits in cash often (~30% invested) — a sparse event strategy, by design.

---

## KILL-CRITERIA (pre-registered — hit any one → halt and re-evaluate)
1. **Hard drawdown stop:** strategy equity −8% from its peak (2× in-sample maxDD).
   Immediate halt.
2. **Rolling edge dead:** after each close, compute the trailing **20-trade mean
   net return**. If it is **≤ 0** (edge no longer covers cost), halt.
3. **Hit-rate collapse:** trailing-20-trade win rate **< 45%** (below the
   break-even the payoff needs). Halt.
4. **Significance breakdown:** after ≥ 20 live trades, if realized mean net return
   is **> 2 standard errors below** the +1%/trade prior, halt (the live edge is
   statistically worse than expected).
5. **Signal inversion:** quarterly, re-run the IC test over the trailing ~30
   events. If rolling IC turns **negative**, halt.
6. **Regime/structure break:** a market-wide shock, a change in NSE
   settlement/STT, or the name leaving the liquidity band → review before next
   entry.

Any halt = stop new entries, let open positions run to their 20-day exit (or the
drawdown stop), then re-evaluate from scratch. **No overrides.** The point of
pre-registering is that you do not get to argue with the rule in the moment.

---

## Deployment ladder (escalate only on evidence)
1. **Paper, ~2–3 months / ≥ 15 events.** Run `scripts/pead_signals.py` daily,
   log fills, track the kill-metrics. Forward = true out-of-sample by construction.
2. **Small real, 10–20% of intended size** — only if paper metrics match the
   prior (positive trailing mean, win rate ~50%+) and no kill-criterion fired.
3. **Scale toward full** only after ≥ 3 months live consistent with the prior.
4. **At any tier, a kill-criterion fires → drop immediately.** Re-entry requires
   a fresh forward paper-validation, not a tweak.

## Position sizing for a decaying edge
- Risk a small fixed fraction per trade (e.g., 0.5–1% of capital), NOT Kelly.
- Assume the edge is temporary: size so a full kill-criterion drawdown (−8%) is
  an acceptable, pre-agreed loss. If −8% of your PEAD capital is not acceptable,
  your PEAD capital is too large.

## What success looks like (and that's OK)
A clean run of a few profitable months, exited the moment the kill-switch trips,
is a *win* — not a failure to find permanence. The edge will decay; the
discipline is to be out before it costs more than the pre-agreed drawdown.

---

## Deployment — single NautilusTrader strategy (backtest = live)
The strategy is **`backtest/pead_strategy.py::PEADStrategy`** — the *one* class,
with all params from `config.PEAD_*` and signal/risk logic in `pead_core.py`.
The same class drives the NT `BacktestEngine` (`scripts/pead_nt_backtest.py`) and
(next) a live **sandbox `TradingNode`**. There is no separate cron reimplementation —
that was removed precisely to avoid backtest/live drift.

Risk guards live in the strategy (`PEADStrategy.on_bar`): disaster stop
(`PEAD_STOP_PCT`), corporate-action gap guard (`PEAD_CORP_GAP`), 20-session hold,
plus a portfolio gross cap. The kill-switch (`pead_core.kill_check`) is evaluated
on realized trades — for live, by a portfolio risk actor; meanwhile inspect any
realized-trades CSV with `pead_signals monitor`.

**Remaining for live:** a Fyers live data adapter + `SandboxExecutionClient`
TradingNode (poll-based daily bars). Untestable offline — build + iterate on EC2
in market hours.

**Hard dependency: unattended auth.** The Fyers token expires daily, so any
unattended run MUST refresh it headlessly — build TOTP auto-login in `auth.py`
first, or every morning's run hits the interactive auth wall and does nothing.
