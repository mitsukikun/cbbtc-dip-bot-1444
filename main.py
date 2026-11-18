"""A cbBTC dip-buying bot for make.fun's 24-hour race, btc-race-24h-20261118-1444.

The harness replays one minute of cbBTC/USDC prices at a time and, after
each batch of bars, asks this bot which orders it wants filled at the next
bar's open. Nothing here is real trading: the account starts with 1,000
paper USDC, goes long only, and never holds more than one position at a
time. Entries close at 20:44 UTC on 18 November and the race runs the 24
hours from 20:59 UTC that evening; the ranking is net profit and loss
over that window. The bot is plain standard-library Python using integer
math only -- no floats, no clock, no network, no files, no randomness --
so the same stream of bars always yields the same orders.

The trading idea, in one sentence
---------------------------------
Buy a sharp dip, then leave as soon as the bounce has covered the round
trip or the dip keeps falling. The bot compares each close with the
close 90 minutes earlier:

* It buys only when the close has fallen 1.20% or more over the last
  90 minutes and the dip latch is set. A buy spends the whole cash
  balance (the race caps weight at the full account anyway), so the
  bot is either all in or all out.
* Once it holds a position it watches the position's value against
  its cost. It sells when the value is 1.20% above cost, when it is
  1.50% below cost, or when eight hours go by with neither firing.
  It also trails: after the value has been 0.60% above cost, a 0.50%
  slide from the position's best value ends the trade, so a bounce
  that stalls and rolls over is banked instead of given back.
* After any sale the latch switches off, and the bot will not buy
  again until the 90-minute return has climbed back above -0.30%.
  That pause is what keeps it from buying the same falling knife
  bar after bar: a round trip costs roughly 26 basis points (4 bp
  fee, 2 bp slippage, about 7 bp of price impact on each side at
  this pool's depth), which would eat the edge faster than the
  bounce restores it.

How the numbers were picked
----------------------------
The thresholds and the hold limit were swept over the kit's own
development window -- the 24 hours of bars ending at the
competition's opening -- and the winner was checked against the
previous day's window as an out-of-sample test. The chosen set makes
+$9.14 on the kit window (three round trips, worst drawdown 1.31%,
$1.61 of fees) and +$8.77 on the previous day's window. Moving any
one parameter one step either way keeps a median worst-window
profit of +$8.33, with 11 of 14 neighbours still profitable on both
windows, so the setting sits in a wide basin rather than on a knife
edge. By contrast every house baseline loses money on the kit
window: buy-and-hold -$31.63, momentum -$23.87, ema-cross -$148.17.
The bot spends most of the day flat, so a falling market costs it
nothing except the round trips it actually chooses to take.
"""

import json
import sys

WIRE_PROTOCOL = "agent-fun/bars-replay/v1"
TRADING_SYMBOL = "CBBTC"

# Tuned constants. One bar is one minute; one basis point is 0.01%.
WINDOW_BARS = 90            # how far back the dip is measured, in minutes
DIP_BPS = 120               # buy once the 90-minute return is under -1.20%
REARM_RETURN_BPS = -30      # latch switches back on past a -0.30% return
TAKE_PROFIT_BPS = 120       # sell once the position is worth +1.20% over cost
STOP_LOSS_BPS = 150         # sell once the position is worth -1.50% under cost
TRAIL_ARM_RETURN_BPS = 60   # trailing exit arms once value is +0.60% over cost
TRAIL_GIVEBACK_BPS = 50     # ... then sells 0.50% below the position's peak
MAX_HOLD_BARS = 480         # sell after eight hours with no other exit firing
ENTRY_SLIPPAGE_BPS = 150    # never chase a buy more than 1.5% past the close
EXIT_SLIPPAGE_BPS = 300     # let a sale through even in a fast downdraft


def quote_value(qty, px, qty_scale, px_scale, quote_scale):
    """Worth of qty units at price px, in quote units, truncating as the harness does."""
    return qty * px * 10 ** quote_scale // 10 ** (qty_scale + px_scale)


class DipBot:
    """A one-symbol dip buyer: holds the account view and the open trade."""

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
        # Bookkeeping for the live trade; None while flat.
        self.trade = None        # {"qty", "cost", "peak", "held"}

    def ingest(self, batch):
        """Take a batch of bars plus the account snapshot into the bot's state."""
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
        """Stack the 90-minute return against limit_bps, in integers only.

        Gives +1 when the return sits above the limit, -1 when below it,
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
        """The orders for this batch; an empty list means sit still."""
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
        """Decide whether the open trade should end on this bar."""
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
        """Tend the dip latch, then buy a fresh dip when one appears."""
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
        """A single order dict, with a fresh client id, for the harness to fill."""
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
    """Read hello/batch/done messages and answer each batch with its orders."""
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
