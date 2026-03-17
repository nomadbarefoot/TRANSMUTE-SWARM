"""
Oracle for finance MA strategy.
Reads prices from data/nifty50_3mo.csv and computes negative Sharpe (lower is better).
Usage: python oracles/evaluate_finance.py --mode quick|full
"""
import argparse
import csv
import math
from pathlib import Path


def load_prices(path: Path) -> list[float]:
    prices: list[float] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            val = row.get("Close") or row.get("Adj Close") or row.get("close")
            if val is None:
                continue
            try:
                prices.append(float(val))
            except ValueError:
                continue
    return prices


def compute_returns(prices: list[float]) -> list[float]:
    returns: list[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        cur = prices[i]
        if prev <= 0:
            returns.append(0.0)
        else:
            returns.append((cur / prev) - 1.0)
    return returns


def compute_sharpe(strategy_returns: list[float]) -> float:
    if not strategy_returns:
        return -1e9
    mean = sum(strategy_returns) / len(strategy_returns)
    var = sum((r - mean) ** 2 for r in strategy_returns) / len(strategy_returns)
    std = math.sqrt(var)
    if std == 0:
        return -1e9
    return (mean / std) * math.sqrt(252.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["quick", "full"], default="full")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    data_path = root / "data" / "nifty50_3mo.csv"
    if not data_path.exists():
        raise SystemExit(f"Missing data file: {data_path}")

    prices = load_prices(data_path)
    if len(prices) < 30:
        raise SystemExit("Not enough data rows to evaluate.")

    # Load strategy
    import importlib.util

    spec = importlib.util.spec_from_file_location("finance_ma", root / "solutions" / "finance_ma.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    signals = mod.compute_signal(prices)
    if len(signals) != len(prices):
        raise SystemExit("compute_signal must return list of same length as prices.")

    returns = compute_returns(prices)
    # Align signals to returns (use previous day signal)
    strategy_returns = []
    for i in range(1, len(prices)):
        pos = signals[i - 1]
        strategy_returns.append(returns[i - 1] * (1.0 if pos else 0.0))

    sharpe = compute_sharpe(strategy_returns)
    sharpe_neg = -sharpe

    print("---")
    print(f"finance_sharpe_neg:  {sharpe_neg:.6f}")
    print(f"n_points:           {len(prices)}")
    print(f"mode:               {args.mode}")


if __name__ == "__main__":
    main()
