#!/usr/bin/env python3
"""
moex_status.py — Статус-сводка по покрытию MOEX.

Выводит краткую сводку: число российских карточек, статус проверки,
число тем и следующая очередь тикеров из MOEX ISS.

Использование:
    python scripts/moex_status.py
    python scripts/moex_status.py --json
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import найти_файлы_тикеров, настроить_вывод, ШАБЛОН_ТИКЕРА, создать_русский_парсер

КОРЕНЬ = Path(__file__).resolve().parents[1]
ДИРЕКТОРИЯ_ОТЧЁТОВ = КОРЕНЬ / "Pilot_Reports"
ДИРЕКТОРИЯ_ТЕМ = КОРЕНЬ / "themes"


def посчитать_отчёты():
    reports = найти_файлы_тикеров()
    по_сектору = {}
    for ticker, filepath in reports.items():
        sector = os.path.basename(os.path.dirname(filepath))
        по_сектору.setdefault(sector, []).append(ticker)
    return len(reports), по_сектору


def посчитать_темы():
    if not ДИРЕКТОРИЯ_ТЕМ.exists():
        return 0
    return len([f for f in ДИРЕКТОРИЯ_ТЕМ.iterdir() if f.suffix == ".md" and f.name != "README.md"])


def проверить_аудит():
    total = 0
    чистые = 0
    число_замечаний = 0
    for subdir in sorted(ДИРЕКТОРИЯ_ОТЧЁТОВ.iterdir()):
        if not subdir.is_dir():
            continue
        for md_file in sorted(subdir.glob("*.md")):
            total += 1
            content = md_file.read_text(encoding="utf-8")
            wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
            has_required = all(
                sec in content
                for sec in [
                    "## Описание деятельности",
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
                чистые += 1
            else:
                число_замечаний += 1
    return total, чистые, число_замечаний


def получить_сводку_очереди():
    try:
        from moex_blue_chip_queue import построить_отчёт, КОДЫ_ИНДЕКСОВ_ПО_УМОЛЧАНИЮ
        report = построить_отчёт(КОДЫ_ИНДЕКСОВ_ПО_УМОЛЧАНИЮ)
        queue = report.get("следующая_очередь", [])
        первые_5 = [
            {"тикер": item["тикер"], "название": item["название"]}
            for item in queue[:5]
        ]
        return len(queue), первые_5, report.get("дата_торгов")
    except Exception as e:
        return None, None, None, str(e)


def main():
    настроить_вывод()
    parser = создать_русский_парсер(description="Статус-сводка по покрытию MOEX")
    parser.add_argument("--json", action="store_true", help="Вывести в JSON")
    args = parser.parse_args()

    report_count, по_сектору = посчитать_отчёты()
    theme_count = посчитать_темы()
    audit_total, audit_clean, audit_issues = проверить_аудит()
    queue_result = получить_сводку_очереди()

    if len(queue_result) == 4:
        длина_очереди, очередь_первые_5, дата_очереди = None, None, None
        ошибка_очереди = queue_result[3]
    else:
        длина_очереди, очередь_первые_5, дата_очереди = queue_result
        ошибка_очереди = None

    audit_pct = (audit_clean / audit_total * 100) if audit_total > 0 else 0

    result = {
        "отчёты": report_count,
        "секторы": len(по_сектору),
        "по_сектору": {k: len(v) for k, v in sorted(по_сектору.items())},
        "темы": theme_count,
        "проверка": {
            "всего": audit_total,
            "чистых": audit_clean,
            "замечаний": audit_issues,
            "доля_%": round(audit_pct, 1),
        },
        "очередь": {
            "непокрытых": длина_очереди,
            "дата": дата_очереди,
            "первые_5": очередь_первые_5,
        },
    }

    if ошибка_очереди:
        result["очередь"]["ошибка"] = ошибка_очереди

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("=" * 50)
    print("  Статус покрытия MOEX")
    print("=" * 50)
    print()
    print(f"  Карточки:       {report_count}")
    print(f"  Секторы:        {len(по_сектору)}")
    print(f"  Темы:           {theme_count}")
    print()
    print(f"  Проверка:      {audit_clean}/{audit_total} ({audit_pct:.0f}%) проходят")
    if audit_issues:
        print(f"                  {audit_issues} с замечаниями")
    print()

    if длина_очереди is not None:
        print(f"  Очередь MOEX:   {длина_очереди} непокрытых ({дата_очереди})")
        if очередь_первые_5:
            print("  Следующие:")
            for item in очередь_первые_5:
                print(f"    - {item['тикер']} ({item['название']})")
    else:
        print(f"  Очередь MOEX:   недоступна ({ошибка_очереди})")

    print()
    print("  Секторы:")
    for sector, tickers in sorted(по_сектору.items(), key=lambda x: -len(x[1])):
        print(f"    {sector}: {len(tickers)}")
    print()
    print("=" * 50)


if __name__ == "__main__":
    main()
