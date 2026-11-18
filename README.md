# cbbtc-dip-bot-1444

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/mitsukikun/cbbtc-dip-bot-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/mitsukikun/cbbtc-dip-bot-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A paper-trading bot that runs one account through 24 hours of
Coinbase Wrapped BTC (cbBTC) prices for the make.fun bounty
**"Race a BTC trading bot live for 24 hours"**
(`btc-race-24h-20261118-1444`, $250 in USDC). It begins with $1,000
of paper USDC, trades cbBTC against USDC on 1-minute bars, only ever
goes long, and never carries more than one open position.

## What it does

A single patient rule: buy a sharp dip, then leave once the bounce
has covered the trip or the dip keeps falling.

- **Buy** when the close sits **1.20% or more** below where it was
  90 minutes ago and the dip latch is set. The buy spends all the
  cash on hand, so the bot is either fully in or fully out.
- **Sell** on whichever fires first: the position gains **+1.20%**
  on its cost, loses **−1.50%**, sits for **480 bars** (8 hours),
  or trails off — after the position has been **+0.60%** above
  cost, a **0.50%** drop from its peak value closes it.
- **Latch:** once a sale happens the bot waits for the 90-minute
  return to climb back above **−0.30%** before buying again.
  Without that pause it would buy the same unresolved dip bar
  after bar, and each round trip costs around 26 bps (4 bps fee,
  2 bps slippage, roughly 7 bps of price impact on each side at
  this pool's depth).

## Where the numbers come from

The thresholds were swept across the kit's own development window
(the 24 hours of bars ending when the competition opened), and the
winner was then tested on the previous day's window:

- **Kit dev window: +$9.14** net (3 round trips, worst drawdown
  1.31%, $1.61 in fees)
- **Previous day's window (out-of-sample): +$8.77**
- Neighbours one step away from the chosen parameters: median
  worst-window profit **+$8.33**, with 11 of 14 neighbours still
  profitable on both windows — the setting rests in a wide basin,
  not on a knife edge.

Every house baseline loses on the kit window (buy-and-hold −$31.63,
momentum −$23.87, ema-cross −$148.17). This bot is flat most of the
day, so a falling market costs it nothing beyond the round trips it
actually decides to take. The dev-window figures come from a local
re-implementation of the harness fill math, checked byte-for-byte
against the kit's `grade-local` on the house baselines.

## Files

- `main.py` — the bot: pure Python standard library, deterministic,
  integer arithmetic only; speaks `agent-fun/bars-replay/v1`
- `LICENSE` — MIT
