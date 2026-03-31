"""
update_valuation.py — Refresh ONLY the valuation multiples in ticker reports.

Much faster than update_financials.py since it only fetches stock.info (no financial statements).
Updates: P/E (TTM), Forward P/E, P/S, P/B, EV/EBITDA, stock price, and period dates.
Preserves all other content including financial tables.

Usage:
  python scripts/update_valuation.py                     # ALL tickers
  python scripts/update_valuation.py SBER                # Single ticker
  python scripts/update_valuation.py SBER GAZP LKOH      # Multiple tickers
  python scripts/update_valuation.py --batch 101         # By batch
  python scripts/update_valuation.py --sector Energy     # By sector
  python scripts/update_valuation.py --dry-run SBER      # Preview without writing
"""

import os
import re
import sys
import time

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    find_ticker_files, parse_scope_args, setup_stdout,
    fetch_valuation_data, build_valuation_table, update_metadata,
    DEFAULT_MARKET_SUFFIXES, get_market_profile,
    SECTION_HEADER_REGEX,
)


def fetch_valuation(ticker):
    """Fetch valuation multiples only. Tries local suffixes in priority order."""
    for suffix in DEFAULT_MARKET_SUFFIXES:
        try:
            stock = yf.Ticker(f"{ticker}{suffix}")
            info = stock.info
            if not info or not info.get("currentPrice"):
                continue

            valuation = fetch_valuation_data(info)

            market_cap = (
                f"{info['marketCap'] / 1_000_000:,.0f}"
                if info.get("marketCap")
                else None
            )
            enterprise_value = (
                f"{info['enterpriseValue'] / 1_000_000:,.0f}"
                if info.get("enterpriseValue")
                else None
            )
            market_profile = get_market_profile(suffix)
            return {
                "valuation": valuation,
                "market_cap": market_cap,
                "enterprise_value": enterprise_value,
                "suffix": suffix,
                "unit_label": market_profile["unit_label"],
            }
        except Exception:
            continue
    return None


def update_file(filepath, ticker, dry_run=False):
    """Update only the valuation section in a ticker file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    data = fetch_valuation(ticker)
    if data is None:
        print(f"  {ticker}: SKIP (no data)")
        return False

    new_table = build_valuation_table(data["valuation"])

    if re.search(SECTION_HEADER_REGEX["valuation"], content):
        content = re.sub(
            rf"{SECTION_HEADER_REGEX['valuation']}.*?(?=\n{SECTION_HEADER_REGEX['annual']})",
            new_table + "\n",
            content,
            flags=re.DOTALL,
        )
    elif re.search(SECTION_HEADER_REGEX["financial"], content):
        annual_match = re.search(SECTION_HEADER_REGEX["annual"], content)
        if annual_match:
            content = content[: annual_match.start()] + new_table + "\n\n" + content[annual_match.start() :]

    content = update_metadata(
        content,
        data.get("market_cap"),
        data.get("enterprise_value"),
        data.get("unit_label", "млн руб."),
    )

    if dry_run:
        print(f"  {ticker}: WOULD UPDATE ({data['suffix']})")
        return True

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  {ticker}: UPDATED ({data['suffix']})")
    return True


def main():
    setup_stdout()

    args = list(sys.argv[1:])
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")

    tickers, sector, desc = parse_scope_args(args)
    print(f"Updating valuation for {desc}...")
    files = find_ticker_files(tickers, sector)

    if not files:
        print("No matching files found.")
        return

    print(f"Found {len(files)} files.\n")
    updated = failed = skipped = 0

    for ticker in sorted(files.keys()):
        try:
            if update_file(files[ticker], ticker, dry_run):
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  {ticker}: ERROR ({e})")
            failed += 1
        time.sleep(0.3)

    print(f"\nDone. Updated: {updated} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    main()
