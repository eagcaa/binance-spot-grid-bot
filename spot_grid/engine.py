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

    def on_price(self,price: Decimal):
        price=D(str(price))
        if price<=0:
            raise ValueError("price must be positive")
        old=self.last_price
        pending=list(self.open_orders.values())
        if price<old:
            crossed=sorted((o for o in pending if o["side"]=="BUY" and price<=o["price"]<old),
                           key=lambda o:o["price"],reverse=True)
        else:
            crossed=sorted((o for o in pending if o["side"]=="SELL" and old<o["price"]<=price),
                           key=lambda o:o["price"])
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

    def snapshot(self):
        if self.config.debug:
            self._assert_balances()
        equity=self.usdt+self.asset*self.last_price
        return {"usdt":str(self.usdt),"asset":str(self.asset),
                "usdt_free":str(self.usdt_free),"usdt_locked":str(self.usdt_locked),
                "asset_free":str(self.asset_free),"asset_locked":str(self.asset_locked),
                "equity":str(equity),
                "pnl":str(equity-self.config.capital),
                "roi_pct":str((equity/self.config.capital-1)*100),
                "fees_usdt":str(sum((f["fee"] for f in self.fills if f["fee_asset"]=="USDT"),D(0))),
                "fees_asset":str(sum((f["fee"] for f in self.fills if f["fee_asset"]=="ASSET"),D(0))
                                 +sum((t["fee"] for t in self.initial_trades),D(0))),
                "initial_trades":len(self.initial_trades),
                "fills":len(self.fills),
                "open_orders":len(self.open_orders)}
