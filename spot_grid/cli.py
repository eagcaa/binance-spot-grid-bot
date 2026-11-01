import argparse
import csv
import json
from decimal import Decimal
from .engine import GridConfig, GridEngine
from .ohlc import read_ohlc, compare_paths

def main():
    p=argparse.ArgumentParser(description="Offline spot grid CSV simulation")
    p.add_argument("--csv",required=True)
    p.add_argument("--lower",type=Decimal,required=True)
    p.add_argument("--upper",type=Decimal,required=True)
    p.add_argument("--capital",type=Decimal,default=Decimal("1000"))
    p.add_argument("--intervals",type=int,default=10)
    p.add_argument("--mode",choices=["arithmetic","geometric"],default="arithmetic")
    p.add_argument("--format", choices=["price", "ohlc"], default="price")
    args=p.parse_args()
    if args.format == "ohlc":
        candles = read_ohlc(args.csv)
        config = GridConfig(args.lower, args.upper, args.intervals, args.capital,
                            candles[0]["open"], mode=args.mode)
        print(json.dumps(compare_paths(config, candles), indent=2))
        return
    with open(args.csv,newline="") as f:
        prices=[Decimal(row["price"]) for row in csv.DictReader(f)]
    if not prices:
        p.error("CSV must contain price rows")
    engine=GridEngine(GridConfig(args.lower,args.upper,args.intervals,args.capital,
                                 prices[0],mode=args.mode))
    for price in prices[1:]:
        engine.on_price(price)
    print(json.dumps(engine.snapshot(),indent=2))

if __name__=="__main__":
    main()
