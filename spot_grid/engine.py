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
        min_order = min(
            floor_step(unit / p, c.qty_step) * p for p in self.levels
        )
        if min_order < c.min_notional:
            raise ValueError(
                f"grid order {min_order:.2f} USDT below minimum "
                f"{c.min_notional} USDT; reduce grid intervals or add capital"
            )
        self.config = c
        self.usdt = c.capital
        self.asset = D(0)
        self.last_price = c.initial_price
        self.orders = []
        self.fills = []
        unit = c.capital/D(c.intervals)
        for i,price in enumerate(self.levels[:-1]):
            if price < c.initial_price:
                self._order("BUY",price,floor_step(unit/price,c.qty_step))
            else:
                target = self.levels[i+1]
                qty = floor_step(unit/target,c.qty_step)
                cost = qty*c.initial_price
                if cost <= self.usdt and qty*target >= c.min_notional:
                    self.usdt -= cost
                    self.asset += qty
                    self._order("SELL",target,qty)

    def _order(self,side,price,qty):
        if qty>0 and qty*price>=self.config.min_notional:
            self.orders.append({"id":len(self.orders)+1,"side":side,
                                "price":price,"qty":qty,"status":"OPEN"})

    def on_price(self,price: Decimal):
        price=D(str(price))
        if price<=0:
            raise ValueError("price must be positive")
        old=self.last_price
        pending=[o for o in self.orders if o["status"]=="OPEN"]
        if price<old:
            crossed=sorted((o for o in pending if o["side"]=="BUY" and price<=o["price"]<old),
                           key=lambda o:o["price"],reverse=True)
        else:
            crossed=sorted((o for o in pending if o["side"]=="SELL" and old<o["price"]<=price),
                           key=lambda o:o["price"])
        for o in crossed:
            p,q=o["price"],o["qty"]
            if o["side"]=="BUY":
                fee=p*q*self.config.fee_rate
                if self.usdt<p*q+fee: continue
                self.usdt-=p*q+fee
                self.asset+=q
                next_side="SELL"
                next_price=self.levels[self.levels.index(p)+1]
            else:
                if self.asset<q: continue
                fee=p*q*self.config.fee_rate
                self.asset-=q
                self.usdt+=p*q-fee
                next_side="BUY"
                next_price=self.levels[self.levels.index(p)-1]
            o["status"]="FILLED"
            self.fills.append({"order_id":o["id"],"side":o["side"],"price":p,
                               "qty":q,"fee_usdt":fee})
            self._order(next_side,next_price,q)
        self.last_price=price

    def snapshot(self):
        equity=self.usdt+self.asset*self.last_price
        return {"usdt":str(self.usdt),"asset":str(self.asset),"equity":str(equity),
                "pnl":str(equity-self.config.capital),
                "roi_pct":str((equity/self.config.capital-1)*100),
                "fees_usdt":str(sum((f["fee_usdt"] for f in self.fills),D(0))),
                "fills":len(self.fills),
                "open_orders":sum(o["status"]=="OPEN" for o in self.orders)}
