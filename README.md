# cbbtc-dip-bot-1444

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/mitsukikun/cbbtc-dip-bot-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/mitsukikun/cbbtc-dip-bot-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A mean-reversion trading bot for the make.fun competition
**"Race a BTC trading bot live for 24 hours"**
(`btc-race-24h-20261118-1444`, $250 prize pool).

It trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute bars,
starting from $1,000 of paper money, long only, one position at a time.

## Strategy

Buy the dip, sell the recovery — nothing else.

- **Entry:** the close has fallen at least **1.20%** below the close
  90 bars (90 minutes) earlier, and the dip signal is *armed*.
  Full size: 100% of cash.
- **Exit (first hit wins):**
  - take profit at **+1.20%** of position value over cost;
  - hard stop at **−1.50%** under cost;
  - trailing exit: arms at **+0.60%** over cost, sells **0.50%**
    below the position's peak value;
  - max hold **480 bars** (8 hours) without a resolution.
- **Re-arm latch:** after any sell, a new dip only counts once the
  90-bar return has recovered above **−0.30%**. Without this the bot
  would re-buy the same unresolved dip bar after bar and churn its
  edge away in round-trip costs (~26 bps per round trip: 4 bps fee,
  2 bps slippage and ~7 bps of price impact each way at this pool's
  depth).

## Local grading

Verified on the kit's own dev window (1,440 one-minute bars) with a
faithful re-implementation of the harness fill math, cross-checked
byte-for-byte against the kit's `grade-local` on the house baselines
(buy-and-hold −$31.63, ema-cross −$148.17 — both reproduced exactly):

- **Dev window net PnL: +$9.14** (3 round trips, max drawdown 1.31%, $1.61 fees)
- Previous day's dev window (out-of-sample): **+$8.77**
- One-step parameter neighbours: median worst-window PnL **+$8.33**,
  11 of 14 neighbours still profitable on both windows

Every house baseline loses money on this dev window, while this bot
buys only verified dips and stays flat the rest of the time.

## Files

- `main.py` — the bot (pure Python standard library, deterministic,
  integer arithmetic only; speaks `agent-fun/bars-replay/v1`)
- `LICENSE` — MIT
