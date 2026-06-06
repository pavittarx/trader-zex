# <strategy name> — STATUS

**Stage:** hypothesis (mirror of `manifest.py:MANIFEST.stage` — keep in sync)
**Broker:** fyers

## Hypothesis

One paragraph: what inefficiency, who is on the other side, why it persists.

## Stage history

| Date | Stage | Evidence / decision |
|------|-------|---------------------|
| YYYY-MM-DD | hypothesis | Initial write-up |

## Findings log

Chronological, including negative results — they're the point.

- YYYY-MM-DD: …

## Kill / drop log

If dropped: which gate failed (triage IC, cost, OOS, sandbox kill-criteria),
the numbers, and the decision. A dropped strategy keeps its folder.

## Pre-registered kill criteria (before sandbox)

Locked BEFORE the first sandbox trade; no discretion afterwards.
Declared in `manifest.py:kill_criteria` (enforced by core.live.risk).
