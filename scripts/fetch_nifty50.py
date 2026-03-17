"""
Fetch NIFTY 50 data via yfinance and save as CSV.
Usage: python scripts/fetch_nifty50.py --months 3
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=3)
    args = parser.parse_args()

    end = datetime.utcnow().date()
    start = end - timedelta(days=int(args.months * 31))
    ticker = "^NSEI"

    data = yf.download(ticker, start=start.isoformat(), end=end.isoformat(), interval="1d", progress=False)
    if data.empty:
        raise SystemExit("No data returned from yfinance.")

    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "nifty50_3mo.csv"
    data.reset_index().to_csv(out_path, index=False)
    print(f"Wrote {out_path} with {len(data)} rows.")


if __name__ == "__main__":
    main()
