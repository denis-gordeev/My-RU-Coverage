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
    извлечь_викилинки, классифицировать_викилинк,
)

ДИРЕКТОРИЯ_ОТЧЁТОВ = os.path.join(os.path.dirname(__file__), "..", "Pilot_Reports")
ФАЙЛ_ВЫВОДА = os.path.join(os.path.dirname(__file__), "..", "WIKILINKS.md")


def собрать_викилинки():
    """Возвращает словарь `{wikilink: число_упоминаний}` по всем отчётам."""
    викилинки = {}
    for root, dirs, files in os.walk(ДИРЕКТОРИЯ_ОТЧЁТОВ):
        for f in files:
            if not f.endswith(".md"):
                continue
            with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                content = fh.read()
            for wl in извлечь_викилинки(content):
                викилинки[wl] = викилинки.get(wl, 0) + 1
    return викилинки


def категоризировать(викилинки):
    """Разбивает викилинки по смысловым категориям."""
    технологии = {}
    материалы = {}
    применения = {}
    компании_российские = {}
    компании_иностранные = {}

    for name, count in викилинки.items():
        cat = классифицировать_викилинк(name)
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

    return технологии, материалы, применения, компании_иностранные, компании_российские


def построить_секцию(заголовок, элементы, лимит=None):
    """Строит markdown-раздел из словаря `{имя: счётчик}`."""
    lines = []
    отсортированные = sorted(элементы.items(), key=lambda x: -x[1])
    if лимит:
        показанные = отсортированные[:лимит]
        метка_итого = f" ({len(элементы)} всего, показаны первые {лимит})"
    else:
        показанные = отсортированные
        метка_итого = f" ({len(элементы)})"

    lines.append(f"## {заголовок}{метка_итого}")
    lines.append("")
    for name, count in показанные:
        lines.append(f"- [[{name}]] ({count})")
    lines.append("")
    return lines


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    викилинки = собрать_викилинки()
    тех, мат, прим, ин, лок = категоризировать(викилинки)

    lines = [
        "# Индекс викилинков",
        "",
        f"> **{len(викилинки)} уникальных викилинков** по всем отчётам. Файл генерируется автоматически.",
        f"> Пересобрать: `python scripts/build_wikilink_index.py`",
        "",
        "---",
        "",
    ]

    lines.extend(построить_секцию("Технологии и стандарты", тех))
    lines.extend(построить_секцию("Материалы и сырьё", мат))
    lines.extend(построить_секцию("Конечные рынки и применения", прим))
    lines.extend(построить_секцию("Иностранные компании", ин, лимит=200))
    lines.extend(построить_секцию("Российские компании", лок, лимит=300))

    with open(ФАЙЛ_ВЫВОДА, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Сгенерирован WIKILINKS.md: {len(викилинки)} уникальных викилинков")
    print(f"  Технологии: {len(тех)}")
    print(f"  Материалы: {len(мат)}")
    print(f"  Применения: {len(прим)}")
    print(f"  Иностранные компании: {len(ин)}")
    print(f"  Российские компании: {len(лок)}")


if __name__ == "__main__":
    main()
