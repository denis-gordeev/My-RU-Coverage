#!/usr/bin/env python3
"""
moex_status.py — Статус-сводка по покрытию MOEX.

Выводит краткий summary: число российских карточек, статус аудита,
число тем и следующая очередь тикеров из MOEX ISS.

Использование:
    python scripts/moex_status.py
    python scripts/moex_status.py --json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import find_ticker_files, setup_stdout, TICKER_PATTERN

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "Pilot_Reports"
THEMES_DIR = ROOT / "themes"


def count_reports():
    reports = find_ticker_files()
    by_sector = {}
    for ticker, filepath in reports.items():
        sector = os.path.basename(os.path.dirname(filepath))
        by_sector.setdefault(sector, []).append(ticker)
    return len(reports), by_sector


def count_themes():
    if not THEMES_DIR.exists():
        return 0
    return len([f for f in THEMES_DIR.iterdir() if f.suffix == ".md" and f.name != "README.md"])


def check_audit():
    total = 0
    clean = 0
    issues_count = 0
    for subdir in sorted(REPORTS_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        for md_file in sorted(subdir.glob("*.md")):
            total += 1
            content = md_file.read_text(encoding="utf-8")
            wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
            has_required = all(
                sec in content
                for sec in [
                    "## Описание бизнеса",
                    "## Положение в цепочке поставок",
                    "## Ключевые клиенты и поставщики",
                    "## Финансовый обзор",
                ]
            )
            has_metadata = all(
                re.search(pat, content)
                for pat in [
                    r"\*\*Сектор:\*\*",
                    r"\*\*Отрасль:\*\*",
                    r"\*\*Рыночная капитализация:\*\*",
                ]
            )
            min_wikilinks = len(wikilinks) >= 10
            if has_required and has_metadata and min_wikilinks:
                clean += 1
            else:
                issues_count += 1
    return total, clean, issues_count


def get_queue_summary():
    try:
        from moex_blue_chip_queue import build_report, DEFAULT_INDEX_CODES
        report = build_report(DEFAULT_INDEX_CODES)
        queue = report.get("next_queue", [])
        top5 = [
            {"ticker": item["ticker"], "name": item["shortnames"]}
            for item in queue[:5]
        ]
        return len(queue), top5, report.get("tradedate")
    except Exception as e:
        return None, None, None, str(e)


def main():
    setup_stdout()
    parser = argparse.ArgumentParser(description="Статус-сводка по покрытию MOEX")
    parser.add_argument("--json", action="store_true", help="Вывести в JSON")
    args = parser.parse_args()

    report_count, by_sector = count_reports()
    theme_count = count_themes()
    audit_total, audit_clean, audit_issues = check_audit()
    queue_result = get_queue_summary()

    if len(queue_result) == 4:
        queue_len, queue_top5, queue_date = None, None, None
        queue_error = queue_result[3]
    else:
        queue_len, queue_top5, queue_date = queue_result
        queue_error = None

    audit_pct = (audit_clean / audit_total * 100) if audit_total > 0 else 0

    result = {
        "reports": report_count,
        "sectors": len(by_sector),
        "by_sector": {k: len(v) for k, v in sorted(by_sector.items())},
        "themes": theme_count,
        "audit": {
            "total": audit_total,
            "clean": audit_clean,
            "issues": audit_issues,
            "pct": round(audit_pct, 1),
        },
        "queue": {
            "missing": queue_len,
            "date": queue_date,
            "top5": queue_top5,
        },
    }

    if queue_error:
        result["queue"]["error"] = queue_error

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("=" * 50)
    print("  Статус покрытия MOEX")
    print("=" * 50)
    print()
    print(f"  Карточки:       {report_count}")
    print(f"  Секторы:        {len(by_sector)}")
    print(f"  Темы:           {theme_count}")
    print()
    print(f"  Аудит:          {audit_clean}/{audit_total} ({audit_pct:.0f}%) проходят")
    if audit_issues:
        print(f"                  {audit_issues} с замечаниями")
    print()

    if queue_len is not None:
        print(f"  Очередь MOEX:   {queue_len} непокрытых ({queue_date})")
        if queue_top5:
            print("  Следующие:")
            for item in queue_top5:
                print(f"    - {item['ticker']} ({item['name']})")
    else:
        print(f"  Очередь MOEX:   недоступна ({queue_error})")

    print()
    print("  Секторы:")
    for sector, tickers in sorted(by_sector.items(), key=lambda x: -len(x[1])):
        print(f"    {sector}: {len(tickers)}")
    print()
    print("=" * 50)


if __name__ == "__main__":
    main()
