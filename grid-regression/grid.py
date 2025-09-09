import backtrader as bt
import akshare as ak
import argparse
import pandas as pd
import json


class GridStrategy(bt.Strategy):
    params = (
        ("grid_up_pct", 0.02),
        ("grid_down_pct", 0.02),
        ("unit_cash", 10000),
        ("total_units", 10),
        ("buy_strategy", "by_latest_buy"),  # by_latest_buy / by_latest_sell
        ("json_only", False),               # only generate json for regression result, don't print it on console
        ("json_output", None),              # the json file to store regression result
    )

    def __init__(self):
        self.units_bought = 0
        self.last_buy_price = None
        self.last_sell_price = None
        self.trades = []
        self.buy_count = 0
        self.sell_count = 0
        self.initial_cash = None

    def log_trade(self, action, price, size):
        # the transaction detail
        self.trades.append({
            "date": str(self.data.datetime.date(0)),
            # buy or sell
            "action": action,
            # unit price
            "price": round(price, 3),
            # the amount that buy or sell
            "size": int(size),
            # the total cash after execute this transaction
            "cash": round(self.broker.get_cash(), 2),
            # the total value after execute this transaction
            "value": round(self.broker.get_value(), 2),
        })

    def start(self):
        self.initial_cash = self.broker.get_value()

    def next(self):
        price = self.data.close[0]

        if self.units_bought == 0 and self.broker.get_cash() >= self.params.unit_cash:
            size = int(self.params.unit_cash / price)
            self.buy(size=size)
            self.units_bought += 1
            self.last_buy_price = price
            self.buy_count += 1
            self.log_trade("BUY INIT", price, size)
            return

        # determine whether sell
        if self.units_bought > 0 and price >= self.last_buy_price * (1 + self.params.grid_up_pct):
            size = int(self.params.unit_cash / price)
            self.sell(size=size)
            self.units_bought -= 1
            self.last_sell_price = price
            self.last_buy_price = price
            self.sell_count += 1
            self.log_trade("SELL", price, size)

        # calculate buy price
        reference_price = None
        if self.params.buy_strategy == "by_latest_sell" and self.last_sell_price:
            reference_price = self.last_sell_price
        elif self.params.buy_strategy == "by_latest_buy" and self.last_buy_price:
            reference_price = self.last_buy_price

        # determine whether buy
        if (
            reference_price
            and self.units_bought < self.params.total_units
            and self.broker.get_cash() >= self.params.unit_cash
            and price <= reference_price * (1 - self.params.grid_down_pct)
        ):
            size = int(self.params.unit_cash / price)
            self.buy(size=size)
            self.units_bought += 1
            self.last_buy_price = price
            self.buy_count += 1
            self.log_trade("BUY", price, size)

    def stop(self):
        self.buy_count = 0 if self.sell_count == 0 else self.buy_count
        final_value = self.broker.get_value()
        profit = final_value - self.initial_cash
        profit_pct = (profit / self.initial_cash) * 100

        # json result for grid regression
        # sample response
        # { "initial_cash": 100000.0, "final_value": 116606.88, "profit": 16606.88, "profit_pct": 16.61, "buy_count": 1, "sell_count": 1, "trades": [ { "date": "2024-01-02", "action": "BUY INIT", "price": 1.316, "size": 7598, "cash": 100000.0, "value": 100000.0 }, { "date": "2024-01-09", "action": "SELL", "price": 1.37, "size": 7299, "cash": 90023.83, "value": 100433.09 } ] }
        result = {
            "initial_cash": round(self.initial_cash, 2),
            "final_value": round(self.initial_cash, 2) if self.sell_count == 0 else round(final_value, 2) ,
            "profit": 0.0 if self.sell_count == 0 else round(profit, 2),
            "profit_pct": 0.0 if self.sell_count == 0 else round(profit_pct, 2),
            "buy_count": 0 if self.sell_count == 0 else self.buy_count,
            "sell_count": self.sell_count,
            # the details of each transactions.
            "trades": [] if self.sell_count == 0 else self.trades
        }
        json_str = json.dumps(result, ensure_ascii=False, indent=2)

        # Print transaction details if json_only is not set on command line
        if not self.params.json_only:
            print("\n===== 交易明细 =====")
            for t in self.trades:
                print(f"{t['date']} {t['action']}: {t['price']} x {t['size']}股  "
                      f"资金={t['cash']:.2f}  总资产={t['value']:.2f}")

            print("\n===== 统计结果 =====")
            print("总买入次数: %s", result["buy_count"])
            print(f"总卖出次数: {self.sell_count}")
            print("最终收益: %s 元", result["profit"])
            print("收益率: %s", result["profit_pct"])

        print("\n===== JSON 结果 =====")
        print(json_str)

        # generate json file for transaction details if json_output is set on command line
        if self.params.json_output:
            with open(self.params.json_output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"JSON 结果已导出到: {self.params.json_output}")


def get_etf_data(symbol, start_date=None, end_date=None):
    df = ak.fund_etf_hist_sina(symbol=symbol)
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    df.set_index("date", inplace=True)
    df.rename(columns={
        "close": "Close", "open": "Open", "high": "High", "low": "Low", "volume": "Volume"
    }, inplace=True)
    return df



# python grid.py --symbol sh513520 --start_date 2024-01-01 --end_date 2025-09-09 --grid_up_pct 0.02 --grid_down_pct 0.02 --unit_cash 10000 --total_units 10 --buy_strategy by_latest_sell --json_only --json_output backtest_result.json
# python grid.py --symbol sh513520 --start_date 2024-01-01 --end_date 2025-09-09 --grid_up_pct 0.02 --grid_down_pct 0.02 --unit_cash 10000 --total_units 10 --buy_strategy by_latest_sell
if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--symbol", default="sh513520", help="ETF代码")
    parser.add_argument("--start_date", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end_date", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--grid_up_pct", type=float, default=0.02, help="网格卖出涨幅")
    parser.add_argument("--grid_down_pct", type=float, default=0.02, help="网格买入跌幅")
    parser.add_argument("--unit_cash", type=float, default=10000, help="每格资金")
    parser.add_argument("--total_units", type=int, default=10, help="总份数")
    parser.add_argument("--buy_strategy", choices=["by_latest_buy", "by_latest_sell"],
                        default="by_latest_buy", help="买入策略参考价格")
    parser.add_argument("--json_only", action="store_true", help="只输出 JSON，不打印交易明细")
    parser.add_argument("--json_output", help="导出 JSON 文件名（可选）")
    args = parser.parse_args()

    df = get_etf_data(args.symbol, args.start_date, args.end_date)

    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(args.unit_cash * args.total_units)

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.addstrategy(
        GridStrategy,
        grid_up_pct=args.grid_up_pct,
        grid_down_pct=args.grid_down_pct,
        unit_cash=args.unit_cash,
        total_units=args.total_units,
        buy_strategy=args.buy_strategy,
        json_only=args.json_only,
        json_output=args.json_output,
    )

    print(f"初始资金: {cerebro.broker.getvalue():.2f}")
    cerebro.run()
    print(f"回测结束资金: {cerebro.broker.getvalue():.2f}")
