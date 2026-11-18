# cbbtc-dip-bot-1444

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/mitsukikun/cbbtc-dip-bot-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/mitsukikun/cbbtc-dip-bot-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A bot that races one paper-trading account through 24 hours of
Coinbase Wrapped BTC (cbBTC) prices for the make.fun bounty
**"Race a BTC trading bot live for 24 hours"**
(`btc-race-24h-20261118-1444`, $250 in USDC). It starts with $1,000
of paper USDC, trades cbBTC against USDC on 1-minute bars, goes long
only, and never holds more than one position at a time.

## How it trades

One rule, applied patiently: buy a sharp dip, exit as soon as the
bounce has paid for the trip or the dip keeps falling.

- **Buy** when the close is down **1.20% or more** over the previous
  90 minutes and the dip latch is set. The buy uses all available
  cash, so the bot is either fully in or fully out.
- **Sell** on whichever comes first: the position gains **+1.20%**
  over its cost, loses **−1.50%**, is held for **480 bars**
  (8 hours), or trails off — once the position has been **+0.60%**
  over cost, a **0.50%** slide from its peak value closes it.
- **Latch:** after any sale the bot waits until the 90-minute
  return has recovered above **−0.30%** before it will buy again.
  Without that pause it would keep buying the same unresolved dip
  bar after bar, and every round trip costs about 26 bps (4 bps
  fee, 2 bps slippage, ~7 bps of price impact each way at this
  pool's depth).

## Why these numbers

The thresholds were picked by sweeping the kit's own development
window (the 24 hours of bars ending at the competition's opening)
and then testing the winner on the previous day's window:

- **Kit dev window: +$9.14** net (3 round trips, worst drawdown
  1.31%, $1.61 in fees)
- **Previous day's window (out-of-sample): +$8.77**
- One-step neighbours of the chosen parameters: median worst-window
  profit **+$8.33**, with 11 of 14 neighbours still profitable on
  both windows — the setting sits in a broad basin, not on a knife
  edge.

Every house baseline loses on the kit window (buy-and-hold −$31.63,
momentum −$23.87, ema-cross −$148.17). This bot is flat most of the
day, so a falling market costs it nothing but the round trips it
actually chooses to take. The dev-window figures were reproduced
with a local re-implementation of the harness fill math, checked
byte-for-byte against the kit's `grade-local` on the house
baselines.

## Files

- `main.py` — the bot: pure Python standard library, deterministic,
  integer arithmetic only; speaks `agent-fun/bars-replay/v1`
- `LICENSE` — MIT
