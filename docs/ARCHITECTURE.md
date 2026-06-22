# Trader Zex — Architecture & Data Flow

## 1. High-level pipeline

```mermaid
flowchart TD
    subgraph AUTH["Auth & Universe"]
        A[core/brokers/fyers/auth.py<br/>Fyers OAuth] -->|token| TOK[(~/.fyers_token.json)]
        U[core/operators/universe.py<br/>Nifty 500 bulk fetch] -->|daily cache| UCACHE[(~/.trader_zex_universe.json)]
    end

    subgraph DATA["Data layer"]
        FC[core/brokers/fyers/client.py<br/>get_history / get_history_multi]
        TOK --> FC
        FC -->|1-min OHLCV| RS[resample_ohlcv<br/>RESAMPLE_RULES]
        RS --> TF5[5-min]
        RS --> TF15[15-min]
        RS --> TF60[60-min]
        RS --> TFD[Daily]
    end

    subgraph SIGNAL["Signal stack (per symbol × timeframe)"]
        HMM[core/signals/hmm_model.py<br/>3-state Gaussian HMM<br/>features: log-ret + range-ratio]
        STR[core/signals/structure.py<br/>ATR Keltner bands / pivots<br/>support / resistance / location]
        CONF[core/signals/confluence.py<br/>3×3 regime × location → signal]
        HMM -->|regime| CONF
        STR -->|location| CONF
    end

    TF15 --> HMM
    TF15 --> STR
    TF60 --> HMM

    CONF --> SCR[core/operators/screener.py<br/>orchestrate across symbols/TFs]
    U --> SCR

    subgraph OUTPUTS["Consumers"]
        SCR --> MAIN[core/operators/main.py CLI<br/>regime + signal table]
        SCR --> DASH[trader_zex/<br/>Reflex web UI]
        SCR --> RANK[core/operators/ranker.py<br/>multi-factor composite]
    end
```

## 2. The ranker (daily candidate selection)

```mermaid
flowchart LR
    UNIV[Nifty 500 universe] --> FS[_fetch_signals<br/>15m + 60m regime, S/R]
    UNIV --> FM[_fetch_momentum<br/>daily bars: 5d return, vol surge]

    FS --> SCORE{composite score}
    FM --> SCORE

    SCORE -->|"40%"| W1[signal strength]
    SCORE -->|"30%"| W2[structure proximity]
    SCORE -->|"20%"| W3[momentum 5d]
    SCORE -->|"10%"| W4[volume surge]

    SCORE --> DIR{60-min regime}
    DIR -->|Bullish| LONG[LONG candidates]
    DIR -->|Bearish| SHORT[SHORT candidates]
    DIR -->|Sideways| LONG

    LONG --> TOPN[top-N each side]
    SHORT --> TOPN
    TOPN --> RCACHE[(~/.trader_zex_rankings.json<br/>keyed by date)]
```

## 3. The backtest (NautilusTrader 1.226)

```mermaid
flowchart TD
    CLI["python -m backtest<br/>--all-symbols / --symbols / --allow-shorts"] --> ENG

    subgraph PREP["Per symbol prep"]
        DL[data_loader.py<br/>Fyers DF → NT Bars<br/>IST→UTC: −5h30m]
        SP[signal_precompute.py<br/>rolling per-bar HMM+confluence<br/>NO look-ahead, disk-cached]
        INST[instruments.py<br/>NT Equity + commission fee]
    end

    ENG[engine.py<br/>run_backtest_portfolio<br/>one engine, shared ₹10L capital]
    DL --> ENG
    SP --> ENG
    INST --> ENG

    ENG --> STRAT

    subgraph STRAT["strategy.py — HMMConfluenceStrategy (per bar)"]
        direction TB
        E1{has position?}
        E1 -->|yes| EXIT[exit checks:<br/>TAKE PROFIT / regime flip /<br/>stop hit / EOD 15:15 IST]
        E1 -->|no| ENT{entry checks}
        ENT -->|"Bullish + STRONG/WEAK BUY<br/>+ regime stable"| BUY[BUY<br/>size = risk% / stop-dist]
        ENT -->|"Bearish + STRONG SELL/AVOID<br/>+ stable + allow_shorts"| SELL[SELL]
    end

    STRAT --> POS[generate_positions_report]
    POS --> MET[metrics.py<br/>parse '2910.00 INR'<br/>win rate / P&L / drawdown / PF]
    MET --> OUT[summary table]
```

## 4. Key design invariants

| Concern | How it's handled |
|---------|-----------------|
| Look-ahead bias | Signals use expanding window `bars[:i+1]` only (`signal_precompute.py`) |
| Survivorship guard | `--use-ranker` prints & **exits**; never picks symbols for historical backtest |
| Position state | Derived from `portfolio.is_net_long/short`, not a manual field |
| Timezone | IST-naive − 5h30m → UTC ns; EOD bars open 09:15 IST → 03:45 UTC |
| Cache invalidation | Signal cache key includes a hash of HMM/structure config |
| Short selling | Requires `AccountType.MARGIN`; off by default (`allow_shorts=False`) |
