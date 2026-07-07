"""
build_wikilink_index.py — Пересобирает WIKILINKS.md по всем карточкам эмитентов.

Использование:
    python scripts/build_wikilink_index.py

Сканирует все `.md` в `Pilot_Reports/` и собирает категоризированный индекс
всех `[[викилинки]]` с числом упоминаний. Запускается после обновления
карточек, тем или связей.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    extract_wikilinks, classify_wikilink,
)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "Pilot_Reports")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "WIKILINKS.md")


def collect_wikilinks():
    """Возвращает словарь `{wikilink: число_упоминаний}` по всем отчётам."""
    wikilinks = {}
    for root, dirs, files in os.walk(REPORTS_DIR):
        for f in files:
            if not f.endswith(".md"):
                continue
            with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                content = fh.read()
            for wl in extract_wikilinks(content):
                wikilinks[wl] = wikilinks.get(wl, 0) + 1
    return wikilinks


def categorize(wikilinks):
    """Разбивает викилинки по смысловым категориям."""
    технологии = {}
    материалы = {}
    применения = {}
    компании_российские = {}
    компании_иностранные = {}

    for name, count in wikilinks.items():
        cat = classify_wikilink(name)
        if cat == "технология":
            технологии[name] = count
        elif cat == "материал":
            материалы[name] = count
        elif cat == "конечный_рынок":
            применения[name] = count
        elif cat == "российская_компания" and count >= 2:
            компании_российские[name] = count
        elif cat == "иностранная_компания" and count >= 2:
            компании_иностранные[name] = count
        # Единичные упоминания в индекс не включаем

    return технологии, материалы, применения, компании_иностранные, компании_российские


def build_section(title, items, limit=None):
    """Строит markdown-раздел из словаря `{имя: счётчик}`."""
    lines = []
    sorted_items = sorted(items.items(), key=lambda x: -x[1])
    if limit:
        shown = sorted_items[:limit]
        total_label = f" ({len(items)} всего, показаны первые {limit})"
    else:
        shown = sorted_items
        total_label = f" ({len(items)})"

    lines.append(f"## {title}{total_label}")
    lines.append("")
    for name, count in shown:
        lines.append(f"- [[{name}]] ({count})")
    lines.append("")
    return lines


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    wikilinks = collect_wikilinks()
    тех, мат, прим, ин, лок = categorize(wikilinks)

    lines = [
        "# Индекс викилинков",
        "",
        f"> **{len(wikilinks)} уникальных викилинков** по всем отчётам. Файл генерируется автоматически.",
        f"> Пересобрать: `python scripts/build_wikilink_index.py`",
        "",
        "---",
        "",
    ]

    lines.extend(build_section("Технологии и стандарты", тех))
    lines.extend(build_section("Материалы и сырьё", мат))
    lines.extend(build_section("Конечные рынки и применения", прим))
    lines.extend(build_section("Иностранные компании", ин, limit=200))
    lines.extend(build_section("Российские компании", лок, limit=300))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Сгенерирован WIKILINKS.md: {len(wikilinks)} уникальных викилинков")
    print(f"  Технологии: {len(тех)}")
    print(f"  Материалы: {len(мат)}")
    print(f"  Применения: {len(прим)}")
    print(f"  Иностранные компании: {len(ин)}")
    print(f"  Российские компании: {len(лок)}")


if __name__ == "__main__":
    main()
