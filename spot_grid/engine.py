"""Offline spot-grid simulator. No exchange API calls."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

D = Decimal

def floor_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

@dataclass(frozen=True)
class GridConfig:
    lower: Decimal
    upper: Decimal
    intervals: int
    capital: Decimal
    initial_price: Decimal
    fee_rate: Decimal = D("0.001")
    mode: str = "arithmetic"
    tick: Decimal = D("0.01")
    qty_step: Decimal = D("0.000001")
    min_notional: Decimal = D("5")
    debug: bool = False
    fill_model: str = "touch"
    through_bps: Decimal = D("5")
    stop_loss: Decimal | None = None
    taker_fee_rate: Decimal = D("0.001")
    slippage: Decimal = D("0.0005")

class GridEngine:
    """Crossing-based paper fills, not production exchange execution."""
    def __init__(self, c: GridConfig):
        if not (D(0) < c.lower < c.upper and c.intervals >= 2 and c.capital > 0):
            raise ValueError("invalid grid parameters")
        if not (c.lower <= c.initial_price <= c.upper):
            raise ValueError("initial price outside grid range")
        if not (0 <= c.fee_rate < 1 and min(c.tick,c.qty_step,c.min_notional)>0):
            raise ValueError("invalid exchange filters")
        if c.mode == "arithmetic":
            raw = [c.lower+(c.upper-c.lower)*D(i)/D(c.intervals) for i in range(c.intervals+1)]
        elif c.mode == "geometric":
            ratio = (c.upper/c.lower)**(D(1)/D(c.intervals))
            raw = [c.lower*ratio**i for i in range(c.intervals+1)]
        else:
            raise ValueError("invalid grid mode")
        self.levels = [floor_step(p,c.tick) for p in raw]
        if len(set(self.levels)) != len(self.levels):
            raise ValueError("grid levels collapse at tick")
        # Reject grid configurations that silently create no usable orders.
        unit = c.capital / D(c.intervals)
        self.buy_qty = [
            floor_step(unit / self.levels[i + 1], c.qty_step)
            for i in range(c.intervals)
        ]
        min_order = min(
            self.buy_qty[i] * self.levels[i]
            for i in range(c.intervals)
        )
        if min_order < c.min_notional:
            raise ValueError(
                f"grid order {min_order:.2f} USDT below minimum "
                f"{c.min_notional} USDT; reduce grid intervals or add capital"
            )
        # Validate actual step-rounded proceeds, not only the percentage spread.
        for i, q in enumerate(self.buy_qty):
            sold = floor_step(q * (D(1) - c.fee_rate), c.qty_step)
            if sold * self.levels[i + 1] < c.min_notional:
                raise ValueError(
                    f"level {self.levels[i]}->{self.levels[i + 1]}: "
                    "replacement SELL below minimum notional after fees and rounding"
                )
            if sold * self.levels[i + 1] * (D(1) - c.fee_rate) < q * self.levels[i]:
                raise ValueError(
                    f"level {self.levels[i]}->{self.levels[i + 1]}: "
                    "fees and quantity rounding leave insufficient proceeds "
                    "to fund the next BUY; use fewer grids or more capital"
                )
        # Calculate complete startup funding before creating any orders.
        initial_gross = [
            ((self.buy_qty[i] / (D(1) - c.fee_rate) / c.qty_step)
             .to_integral_value(rounding="ROUND_UP") * c.qty_step)
            for i, p in enumerate(self.levels[:-1])
            if p >= c.initial_price
        ]
        inventory_cost = sum((q * c.initial_price for q in initial_gross), D(0))
        buy_reservations = sum(
            (self.buy_qty[i] * p for i, p in enumerate(self.levels[:-1])
             if p < c.initial_price), D(0)
        )
        total_required = inventory_cost + buy_reservations
        if total_required > c.capital:
            raise ValueError(
                f"insufficient starting capital: need {total_required} USDT "
                f"for initial inventory ({inventory_cost}) and BUY reservations "
                f"({buy_reservations}), have {c.capital}"
            )
        if c.fill_model not in ("touch", "through") or c.through_bps < 0:
            raise ValueError("invalid fill model or buffer")
        if c.stop_loss is not None and not (D(0) < c.stop_loss < c.lower):
            raise ValueError("stop_loss must be positive and below lower grid bound")
        if not (D(0) <= c.taker_fee_rate < D(1) and
                D(0) <= c.slippage < D(1)):
            raise ValueError("invalid taker fee or slippage")
        self.config = c
        self.usdt_free = c.capital
        self.usdt_locked = D(0)
        self.asset_free = D(0)
        self.asset_locked = D(0)
        self.last_price = c.initial_price
        self.orders = []  # historical order ledger
        self.open_orders = {}  # active orders only, keyed by order id
        self._next_order_id = 1
        self.fills = []
        self.initial_trades = []
        self.stopped = False
        self.stop_trades = []
        self.outside_candles = 0
        self.outside_entries = 0
        self._was_outside = False
        unit = c.capital/D(c.intervals)
        # Acquire starting inventory before reserving all limit orders.
        for i,price in enumerate(self.levels[:-1]):
            if price < c.initial_price:
                pass  # BUY orders are placed after initial inventory purchases
            else:
                target = self.levels[i+1]
                qty = self.buy_qty[i]
                # Initial spot purchase: gross amount includes the base-asset fee.
                gross = ((qty / (D(1)-c.fee_rate)) / c.qty_step).to_integral_value(rounding="ROUND_UP") * c.qty_step
                cost = gross*c.initial_price
                if cost > self.usdt_free:
                    raise ValueError("insufficient capital for initial inventory")
                fee = gross*c.fee_rate
                net = gross-fee
                if net < qty:
                    raise RuntimeError("initial inventory fee calculation mismatch")
                self.usdt_free -= cost
                self.asset_free += net
                self.initial_trades.append({"side":"BUY","price":c.initial_price,
                    "gross_qty":gross,"net_qty":net,"fee":fee,
                    "fee_asset":"ASSET","cost_usdt":cost})
        # Reserve funds for all initial BUY and SELL orders.
        for i, price in enumerate(self.levels[:-1]):
            if price < c.initial_price:
                self._order("BUY", price, self.buy_qty[i])
            else:
                self._order("SELL", self.levels[i + 1], self.buy_qty[i])
        self._assert_balances()

    @property
    def usdt(self):
        return self.usdt_free + self.usdt_locked

    @property
    def asset(self):
        return self.asset_free + self.asset_locked

    def _assert_balances(self):
        expected_usdt = sum(
            (o["price"] * o["qty"] for o in self.open_orders.values()
             if o["side"] == "BUY"), D(0))
        expected_asset = sum(
            (o["qty"] for o in self.open_orders.values()
             if o["side"] == "SELL"), D(0))
        if self.usdt_locked != expected_usdt:
            raise RuntimeError("USDT reservation mismatch")
        if self.asset_locked != expected_asset:
            raise RuntimeError("asset reservation mismatch")
        if min(self.usdt_free, self.usdt_locked,
               self.asset_free, self.asset_locked) < 0:
            raise RuntimeError("negative balance")

    def _order(self, side, price, qty):
        if qty <= 0 or qty * price < self.config.min_notional:
            raise RuntimeError(f"{side} {qty}@{price} below minimum notional")
        if side == "BUY":
            cost = price * qty
            if self.usdt_free < cost:
                raise RuntimeError("insufficient free USDT to reserve BUY")
            self.usdt_free -= cost
            self.usdt_locked += cost
        elif side == "SELL":
            if self.asset_free < qty:
                raise RuntimeError("insufficient free asset to reserve SELL")
            self.asset_free -= qty
            self.asset_locked += qty
        else:
            raise ValueError("invalid order side")
        order = {"id": self._next_order_id, "side": side,
                 "price": price, "qty": qty, "status": "OPEN"}
        self._next_order_id += 1
        self.orders.append(order)
        self.open_orders[order["id"]] = order
        if self.config.debug:
            self._assert_balances()

    def _stop(self, trigger_price):
        if self.stopped:
            return
        # Cancel every resting order and return its reserved funds.
        for order in list(self.open_orders.values()):
            if order["side"] == "BUY":
                amount = order["price"] * order["qty"]
                self.usdt_locked -= amount
                self.usdt_free += amount
            else:
                self.asset_locked -= order["qty"]
                self.asset_free += order["qty"]
            order["status"] = "CANCELLED"
        self.open_orders.clear()
        quantity = floor_step(self.asset_free, self.config.qty_step)
        execution_price = trigger_price * (D(1) - self.config.slippage)
        fee = quantity * execution_price * self.config.taker_fee_rate
        if quantity > 0:
            self.asset_free -= quantity
            self.usdt_free += quantity * execution_price - fee
        self.stop_trades.append({
            "kind": "stop_loss", "side": "SELL",
            "price": execution_price, "trigger_price": trigger_price,
            "qty": quantity, "fee": fee, "fee_asset": "USDT",
            "dust_asset": self.asset_free
        })
        self.last_price = trigger_price
        self.stopped = True
        self._assert_balances()

    def on_price(self,price: Decimal, eligible_ids=None, _stop_path=False):
        if self.stopped:
            return
        price=D(str(price))
        if price <= 0:
            raise ValueError("price must be positive")
        if (not _stop_path and self.config.stop_loss is not None
                and price <= self.config.stop_loss):
            # Only BUY orders crossed on the way down may fill before the stop.
            self._fill_stop_path(price, None)
            return
        old=self.last_price
        pending=[o for o in self.open_orders.values()
                 if eligible_ids is None or o["id"] in eligible_ids]
        buffer = (self.config.through_bps / D("10000")
                  if self.config.fill_model == "through" else D(0))
        lo, hi = min(old, price), max(old, price)
        buys = sorted(
            (o for o in pending if o["side"] == "BUY"
             and lo <= o["price"] * (D(1) - buffer)),
            key=lambda o: o["price"], reverse=True)
        sells = sorted(
            (o for o in pending if o["side"] == "SELL"
             and hi >= o["price"] * (D(1) + buffer)),
            key=lambda o: o["price"])
        # Orders already marketable at the segment start execute before
        # orders reached later on the segment. Preserve price priority.
        at_start_buys = [o for o in buys
                         if old <= o["price"] * (D(1) - buffer)]
        at_start_sells = [o for o in sells
                          if old >= o["price"] * (D(1) + buffer)]
        reached_buys = [o for o in buys if o not in at_start_buys]
        reached_sells = [o for o in sells if o not in at_start_sells]
        crossed = (at_start_sells + at_start_buys +
                   (reached_buys + reached_sells if price < old
                    else reached_sells + reached_buys))
        for o in crossed:
            p,q=o["price"],o["qty"]
            if o["side"]=="BUY":
                fee=q*self.config.fee_rate
                if self.usdt_locked < p*q:
                    raise RuntimeError("BUY reservation missing")
                self.usdt_locked -= p*q
                self.asset_free += q-fee
                next_side="SELL"
                next_price=self.levels[self.levels.index(p)+1]
                next_qty=floor_step(q-fee,self.config.qty_step)
                fee_asset="ASSET"
            else:
                if self.asset_locked < q:
                    raise RuntimeError("SELL reservation missing")
                fee=p*q*self.config.fee_rate
                self.asset_locked -= q
                self.usdt_free += p*q-fee
                next_side="BUY"
                next_price=self.levels[self.levels.index(p)-1]
                next_qty=self.buy_qty[self.levels.index(next_price)]
                fee_asset="USDT"
            o["status"]="FILLED"
            del self.open_orders[o["id"]]
            self.fills.append({"order_id":o["id"],"side":o["side"],"price":p,
                               "qty":q,"fee":fee,"fee_asset":fee_asset})
            self._order(next_side,next_price,next_qty)
            if self.config.debug:
                self._assert_balances()
        self.last_price=price

    def _fill_stop_path(self, observed_price, eligible_ids):
        stop = self.config.stop_loss
        # No SELL fills are allowed in this conservative stop path.
        # A gap can cross BUY levels at their limit prices.
        pending = [
            o for o in self.open_orders.values()
            if o["side"] == "BUY"
            and (eligible_ids is None or o["id"] in eligible_ids)
        ]
        buffer = (self.config.through_bps / D("10000")
                  if self.config.fill_model == "through" else D(0))
        low = min(self.last_price, observed_price, stop)
        buys = sorted(
            (o for o in pending
             if low <= o["price"] * (D(1) - buffer)),
            key=lambda o: o["price"], reverse=True)
        for order in buys:
            # Execute through the existing reservation and replacement logic,
            # but restrict eligibility to this single original BUY order.
            # Temporarily shield other orders from the regular price path.
            self.on_price(order["price"] * (D(1) - buffer),
                          eligible_ids={order["id"]}, _stop_path=True)
        trigger = observed_price if observed_price <= stop else stop
        self._stop(trigger)

    def on_candle(self, candle, path="high_first", allow_same_candle_reentry=False):
        if self.stopped:
            return
        outside = candle["low"] < self.config.lower or candle["high"] > self.config.upper
        if outside:
            self.outside_candles += 1
            if not self._was_outside:
                self.outside_entries += 1
        self._was_outside = outside
        if self.config.stop_loss is not None and candle["low"] <= self.config.stop_loss:
            # The opening-to-stop downward path fills eligible BUYs, never SELLs.
            self._fill_stop_path(candle["open"], set(self.open_orders))
            return
        if path not in ("high_first", "low_first"):
            raise ValueError("invalid intrabar path")
        eligible = None if allow_same_candle_reentry else set(self.open_orders)
        points = ((candle["open"], candle["high"], candle["low"], candle["close"])
                  if path == "high_first" else
                  (candle["open"], candle["low"], candle["high"], candle["close"]))
        for point in points:
            self.on_price(point, eligible_ids=eligible)

    def pnl_breakdown(self):
        """Cost-basis attribution, with asset fees embedded in net inventory.

        The grid and stop realized figures are gross of quote-asset fees.
        Quote fees are deducted once in the reconciliation. Asset-denominated
        fees reduce acquired quantity and increase its effective unit cost.
        """
        inventory = D(0)
        basis = D(0)
        realized_grid = D(0)
        realized_stop = D(0)
        maker_quote_fees = D(0)
        taker_quote_fees = D(0)
        maker_asset_fees = D(0)

        def acquire(gross_qty, net_qty, price):
            nonlocal inventory, basis
            inventory += net_qty
            basis += gross_qty * price

        def dispose(qty, price):
            nonlocal inventory, basis
            if qty > inventory and qty - inventory > D("0.0000000001"):
                raise RuntimeError("PNL ledger sold more asset than acquired")
            cost = basis * qty / inventory if inventory else D(0)
            inventory -= qty
            basis -= cost
            return qty * price - cost

        for trade in self.initial_trades:
            acquire(trade["gross_qty"], trade["net_qty"], trade["price"])
            maker_asset_fees += trade["fee"]
        for fill in self.fills:
            if fill["side"] == "BUY":
                acquire(fill["qty"], fill["qty"] - fill["fee"], fill["price"])
                maker_asset_fees += fill["fee"]
            else:
                realized_grid += dispose(fill["qty"], fill["price"])
                maker_quote_fees += fill["fee"]
        for trade in self.stop_trades:
            realized_stop += dispose(trade["qty"], trade["price"])
            taker_quote_fees += trade["fee"]

        if abs(inventory - self.asset) > D("0.0000000001"):
            raise RuntimeError("PNL ledger inventory mismatch")
        unrealized = inventory * self.last_price - basis
        fees_quote = maker_quote_fees + taker_quote_fees
        reconciled = realized_grid + realized_stop + unrealized - fees_quote
        actual = self.usdt + self.asset * self.last_price - self.config.capital
        if abs(reconciled - actual) > D("0.00000001"):
            raise RuntimeError("PNL attribution does not reconcile to equity")
        # Dust is only unreserved, untradable asset quantity; after a stop
        # the remaining free asset is explicitly the unsellable remainder.
        dust = (self.asset_free if self.stopped else
                self.asset_free - floor_step(self.asset_free, self.config.qty_step))
        return {
            "grid_realized_gross_usdt": str(realized_grid),
            "stop_realized_gross_usdt": str(realized_stop),
            "coin_unrealized_usdt": str(unrealized),
            "maker_fees_usdt": str(maker_quote_fees),
            "taker_fees_usdt": str(taker_quote_fees),
            "initial_maker_fees_asset": str(sum(
                (t["fee"] for t in self.initial_trades), D(0))),
            "grid_maker_fees_asset": str(sum(
                (f["fee"] for f in self.fills if f["fee_asset"] == "ASSET"), D(0))),
            "asset_fees_included_in_basis": str(maker_asset_fees),
            "dust_asset": str(dust),
            "dust_value_usdt": str(dust * self.last_price),
            "remaining_asset_cost_basis_usdt": str(basis),
            "pnl_reconciled_usdt": str(reconciled),
        }

    def snapshot(self):
        if self.config.debug:
            self._assert_balances()
        equity=self.usdt+self.asset*self.last_price
        return {"usdt":str(self.usdt),"asset":str(self.asset),
                "usdt_free":str(self.usdt_free),"usdt_locked":str(self.usdt_locked),
                "asset_free":str(self.asset_free),"asset_locked":str(self.asset_locked),
                "equity":str(equity),
                "stopped":self.stopped,
                "outside_candles":self.outside_candles,
                "outside_entries":self.outside_entries,
                "dust_asset":str(self.asset_free if self.stopped else D(0)),
                "stop_trades":self.stop_trades and [{k:str(v) if isinstance(v,Decimal) else v for k,v in t.items()} for t in self.stop_trades] or [],
                "pnl":str(equity-self.config.capital),
                "roi_pct":str((equity/self.config.capital-1)*100),
                "fees_usdt":str(sum((f["fee"] for f in self.fills if f["fee_asset"]=="USDT"),D(0)) + sum((t["fee"] for t in self.stop_trades),D(0))),
                "fees_asset":str(sum((f["fee"] for f in self.fills if f["fee_asset"]=="ASSET"),D(0))
                                 +sum((t["fee"] for t in self.initial_trades),D(0))),
                "initial_trades":len(self.initial_trades),
                "fills":len(self.fills),
                "open_orders":len(self.open_orders),
                "pnl_breakdown":self.pnl_breakdown()}
