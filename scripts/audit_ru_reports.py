#!/usr/bin/env python3
"""Аудит всех российских (MOEX) отчётов в Pilot_Reports/ на качество."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "Pilot_Reports"
LEGACY_THEME_MARKERS = {
    "HBM", "Tesla", "Apple", "NVIDIA", "CoWoS", "CPO", "EUV", "VCSEL",
    "ABF_載板", "低軌衛星", "光阻液", "氮化鎵", "矽光子", "矽晶圓",
    "碳化矽", "磷化銦", "資料中心", "電動車", "AI_伺服器",
}
HAN_RE = re.compile(r"[\u4e00-\u9fff]")

def check_file(filepath):
    """Вернуть список замечаний по одному отчёту."""
    issues = []
    content = filepath.read_text(encoding="utf-8")

    # 1. Ищем слишком общие викилинк-сущности.
    wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
    industry_acronyms = {
        "СПГ", "АЗС", "МСБ", "ОРЭМ", "ДПМ", "ФСТ", "СУЭК", "АТС", "ЖКХ",
        "КОМ", "РСВ", "НЛМК", "ММК", "МТС", "ВТБ", "Сбер", "Тева", "ФСБ",
        "Циан", "Юла", "ЕГРН", "ПИК", "Озон", "РЖД", "САПР", "ЧПУ",
        "ФосАгро", "Лукойл", "Газпром", "Роснефть", "Сургутнефтегаз",
        "Татнефть", "Башнефть", "НОВАТЭК", "РусГидро", "Аэрофлот",
        "Магнит", "Пятерочка", "Перекресток", "Дикси", "Лента",
        "MOEX", "ЦБ", "ФАС", "Минцифры", "44-ФЗ", "223-ФЗ",
    }
    generic_patterns = [
        r"^компания$",
        r"^предприятие$",
        r"^организация$",
        r"^сервис$",
        r"^технологии?$",
        r"^цифровы[е|ой]$",
        r"^производств[о|а|у]$",
        r"^рынок$",
        r"^инфраструктур[а|ы]$",
        r"^материалы?$",
        r"^продукци[я|и]$",
        r"^оборудовани[е|я]$",
        r"^решени[я|е]$",
        r"^поставщик[и|ов]?$",
        r"^клиент[ы|ов]?$",
    ]
    generic_wikilinks = []
    for wl in wikilinks:
        wl_stripped = wl.strip()
        if wl_stripped in industry_acronyms:
            continue
        if re.match(r"^[A-ZА-ЯЁ]{2,6}$", wl_stripped):
            continue
        base = wl_stripped.split("|")[0].strip()
        for pat in generic_patterns:
            if re.match(pat, base, re.IGNORECASE):
                generic_wikilinks.append(wl)
                break
    if generic_wikilinks:
        issues.append(f"Слишком общие викилинк-сущности: {', '.join(generic_wikilinks)}")

    # 2. Проверяем размер секции про клиентов и поставщиков.
    client_match = re.search(r"## Ключевые клиенты? и поставщики?", content)
    if client_match:
        section = content[client_match.end():]
        next_section = re.search(r"\n## ", section)
        if next_section:
            section = section[:next_section.start()]
        lines = [line for line in section.strip().split("\n") if line.strip()]
        if len(lines) < 4:
            issues.append(f"Слишком короткий блок клиентов/поставщиков: {len(lines)} строк")

    # 3. Проверяем обязательные разделы.
    required = [
        "## Описание бизнеса",
        "## Положение в цепочке поставок",
        "## Ключевые клиенты и поставщики",
        "## Финансовый обзор",
    ]
    for sec in required:
        if sec not in content:
            issues.append(f"Отсутствует обязательный раздел: {sec}")

    # 4. Проверяем минимальное число викилинков.
    if len(wikilinks) < 10:
        issues.append(f"Недостаточно викилинков: {len(wikilinks)} (нужно >= 10)")

    # 5. Ловим остаточные legacy-темы и китайские сущности в российском корпусе.
    legacy_hits = []
    for wl in wikilinks:
        base = wl.split("|")[0].strip()
        if base in LEGACY_THEME_MARKERS or HAN_RE.search(base):
            legacy_hits.append(base)
    if legacy_hits:
        issues.append(
            "Обнаружены legacy-сущности вне российского контура: "
            + ", ".join(sorted(set(legacy_hits)))
        )

    return issues


def main():
    all_issues = {}
    total = 0
    for subdir in sorted(REPORTS_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        for md_file in sorted(subdir.glob("*.md")):
            total += 1
            issues = check_file(md_file)
            if issues:
                key = f"{subdir.name}/{md_file.name}"
                all_issues[key] = issues

    print("=" * 60)
    print(f"Проверено российских отчётов: {total}")
    print(f"Отчётов с замечаниями: {len(all_issues)}/{total}")
    print("=" * 60)

    if all_issues:
        print()
        for key, issues in sorted(all_issues.items()):
            print(f"  [{key}]")
            for issue in issues:
                print(f"    - {issue}")
            print()

    if all_issues:
        sys.exit(1)

    print("Все отчёты проходят проверку качества.")
    sys.exit(0)


if __name__ == "__main__":
    main()
