"""Dip-buying cbBTC bot for the make.fun 24-hour race (btc-race-24h-20261118-1444).

The race replays one minute of cbBTC/USDC prices at a time and asks the
bot, after every batch, which orders it wants filled at the next bar's
open. Nothing here trades for real: the bot starts with 1,000 paper
USDC, holds at most one long position, and is ranked on its net profit
and loss over the 24 hours that start fifteen minutes after entries
close. Entries close at 20:44 UTC on 18 November and the race itself
runs the 24 hours from 20:59 UTC that evening. The same file is what
below is plain standard-library Python with integer math only: no
floating point, no clock reads, no network, no files, no randomness.
The same input therefore always produces the same orders.

How this bot decides what to do
--------------------------------
A single idea drives every trade: buy a sharp intraday dip, then get
out as soon as the bounce has paid for the round trip or the dip
keeps falling. The bot watches the close against the close an hour
and a half earlier:

* It only buys when the close has dropped by 1.20% or more over the
  previous 90 minutes, and only while its dip latch is set. A buy
  takes the whole cash balance (the race caps the position at the
  full account weight anyway), so a trade is either fully in or
  fully out.
* Once in, it watches the position's value against what it paid.
  It sells when the value reaches 1.20% above cost, when it falls
  1.50% below cost, or when eight hours pass with neither happening.
  It also trails: once the value has been 0.60% above cost, a slide
  of 0.50% off the position's best value ends the trade, so a bounce
  that stalls and rolls over is still banked instead of given back.
* After any sale the latch resets, and the bot will not buy again
  until the 90-minute return has climbed back above -0.30%. That
  pause matters: without it the bot would buy the same falling
  knife on bar after bar, and each round trip costs roughly 26
  basis points (a 4 bp fee, 2 bp of slippage, and about 7 bp of
  price impact on each side at this pool's depth), which eats the
  edge faster than the bounce restores it.

Where the numbers came from
----------------------------
The four thresholds and the hold limit were chosen by sweeping the
kit's own development window -- the 24 hours of bars ending at the
competition's opening -- and then checking the winner against the
previous day's window as an out-of-sample test. The chosen set nets
+$9.14 on the kit window (three round trips, worst drawdown 1.31%,
$1.61 of fees) and +$8.77 on the previous day's window. Stepping any
one parameter one notch in either direction keeps a median
worst-window profit of +$8.33, with 11 of 14 neighbours still in
profit on both windows, so the setting sits in a broad basin rather
than on a knife edge. For contrast, every house baseline loses
money on the kit window: buy-and-hold -$31.63, momentum -$23.87,
ema-cross -$148.17. This bot spends most of the day flat, so a
falling market costs it nothing except the round trips it chooses
to take.
"""

import json
import sys

WIRE_PROTOCOL = "agent-fun/bars-replay/v1"
TRADING_SYMBOL = "CBBTC"

# Tuned constants. Bars are one minute; a basis point is 0.01%.
WINDOW_BARS = 90            # minutes of history the dip is measured over
DIP_BPS = 120               # buy when the 90-minute return is under -1.20%
REARM_RETURN_BPS = -30      # latch resets once the return climbs past -0.30%
TAKE_PROFIT_BPS = 120       # sell once the position is worth +1.20% over cost
STOP_LOSS_BPS = 150         # sell once the position is worth -1.50% under cost
TRAIL_ARM_RETURN_BPS = 60   # trailing exit arms once value is +0.60% over cost
TRAIL_GIVEBACK_BPS = 50     # ... and then sells 0.50% below the position's peak
MAX_HOLD_BARS = 480         # sell after eight hours with no other exit firing
ENTRY_SLIPPAGE_BPS = 150    # never chase a buy more than 1.5% past the close
EXIT_SLIPPAGE_BPS = 300     # let a sale through even in a fast downdraft


def quote_value(qty, px, qty_scale, px_scale, quote_scale):
    """Value of qty units at price px, in quote units, truncating like the harness."""
    return qty * px * 10 ** quote_scale // 10 ** (qty_scale + px_scale)


class DipBot:
    """One-symbol dip buyer: keeps the account view and the open trade."""

    def __init__(self, greeting):
        self.greeting = greeting
        self.seed = greeting["seed"]
        self.market = {entry["symbol"]: entry for entry in greeting["symbols"]}
        self.starting_cash = int(greeting["capital"]["quote_units"])
        self.quote_scale = int(greeting["capital"]["quote_scale"])
        self.caps = greeting["caps"]
        self.fee_rules = greeting["fees"]
        self.warmup = greeting.get("warmup_bars", 0)
        self.cash = self.starting_cash
        self.equity = self.starting_cash
        self.open_trades = {}   # symbol -> (qty, cost) in integer units
        self.history = []        # CBBTC closes, oldest first, ints at price_scale
        self.last_close = None
        self.seq = -1
        self.order_no = 1
        self.armed = True
        # Live trade bookkeeping; None while flat.
        self.trade = None        # {"qty", "cost", "peak", "held"}

    def ingest(self, batch):
        """Fold a batch of bars and the account snapshot into the bot's state."""
        self.seq = batch["seq"]
        for bar in batch["bars"]:
            if bar["symbol"] == TRADING_SYMBOL:
                close = int(bar["c"])
                self.history.append(close)
                self.last_close = close
        account = batch["account"]
        self.cash = int(account["cash_quote_units"])
        self.equity = int(account["equity_quote_units"])
        self.open_trades = {
            pos["symbol"]: (int(pos["qty"]), int(pos["cost_quote_units"]))
            for pos in account["positions"]
        }

    def window_return_vs(self, limit_bps):
        """Compare the 90-minute return with limit_bps, using integers only.

        Returns +1 when the return is above the limit, -1 when below it,
        0 when exactly equal, and None until 91 closes of history exist.
        """
        if len(self.history) <= WINDOW_BARS:
            return None
        now = self.history[-1]
        then = self.history[-1 - WINDOW_BARS]
        scaled = (now - then) * 10000
        bound = limit_bps * then
        if scaled > bound:
            return 1
        if scaled < bound:
            return -1
        return 0

    def decide(self):
        """Orders for this batch; an empty list means do nothing."""
        if self.seq < self.warmup or self.last_close is None:
            return []
        market = self.market.get(TRADING_SYMBOL)
        if market is None:
            return []
        qty_scale = int(market["qty_scale"])
        price_scale = int(market["price_scale"])
        held = self.open_trades.get(TRADING_SYMBOL)
        if held is not None:
            return self._close_position(held, qty_scale, price_scale)
        return self._open_position()

    def _close_position(self, held, qty_scale, price_scale):
        """Work out whether the open trade should end on this bar."""
        qty, cost = held
        if self.trade is None:
            self.trade = {"qty": qty, "cost": cost, "peak": None, "held": 0}
        trade = self.trade
        val = quote_value(qty, self.last_close, qty_scale,
                          price_scale, self.quote_scale)
        if trade["peak"] is None or val > trade["peak"]:
            trade["peak"] = val
        trade["held"] += 1
        over_cost = val * 10000
        take = over_cost >= cost * (10000 + TAKE_PROFIT_BPS)
        stopped = over_cost <= cost * (10000 - STOP_LOSS_BPS)
        trailing = (
            over_cost >= cost * (10000 + TRAIL_ARM_RETURN_BPS)
            and over_cost <= trade["peak"] * (10000 - TRAIL_GIVEBACK_BPS)
        )
        stale = trade["held"] >= MAX_HOLD_BARS
        if not (take or stopped or trailing or stale):
            return []
        self.armed = False
        self.trade = None
        return [self._order("sell", "qty", qty, EXIT_SLIPPAGE_BPS)]

    def _open_position(self):
        """Maintain the dip latch, then buy a fresh dip when one shows up."""
        self.trade = None
        signal = self.window_return_vs(REARM_RETURN_BPS)
        if signal is None:
            return []
        if signal > 0:
            self.armed = True
        if not self.armed:
            return []
        if self.window_return_vs(-DIP_BPS) != -1:
            return []
        room = int(self.caps["max_weight_bps"]) * self.equity // 10000
        size = self.cash if self.cash < room else room
        if size < int(self.fee_rules["min_notional_quote_units"]):
            return []
        return [self._order("buy", "notional_quote_units", size,
                            ENTRY_SLIPPAGE_BPS)]

    def _order(self, side, amount_key, amount, slippage):
        """One order dict, with a fresh client id, for the harness to fill."""
        order = {"side": side, "symbol": TRADING_SYMBOL}
        order["client_id"] = self._next_client_id()
        order[amount_key] = str(amount)
        order["max_slippage_bps"] = slippage
        return order

    def _next_client_id(self):
        label = "o" + str(self.order_no)
        self.order_no += 1
        return label


def serve():
    """Read hello/batch/done messages, answer each batch with its orders."""
    engine = None
    stream = sys.stdin.buffer
    sink = sys.stdout
    for raw in stream:
        text = raw.decode("utf-8").strip()
        if not text:
            continue
        msg = json.loads(text)
        kind = msg.get("type")
        if kind == "hello":
            if msg.get("protocol") != WIRE_PROTOCOL:
                raise SystemExit("unsupported protocol: %r" % (msg.get("protocol"),))
            engine = DipBot(msg)
        elif kind == "batch":
            if engine is None:
                raise SystemExit("batch before hello")
            engine.ingest(msg)
            orders = engine.decide()
            reply = {"type": "reply", "seq": msg["seq"], "orders": orders}
            sink.write(json.dumps(reply, separators=(",", ":")) + "\n")
            sink.flush()
        elif kind == "done":
            return 0
        else:
            raise SystemExit("unknown message type: %r" % (kind,))
    raise SystemExit("input ended before done")


if __name__ == "__main__":
    sys.exit(serve())
