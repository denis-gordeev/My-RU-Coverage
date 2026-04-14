#!/usr/bin/env python3
"""Аудит всех российских (MOEX) отчётов в Pilot_Reports/ на качество."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "Pilot_Reports"

# Quality checks
def check_file(filepath):
    """Return list of issues for a report."""
    issues = []
    content = filepath.read_text(encoding="utf-8")

    # 1. Check for generic wikilinks (too short / too generic)
    wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)
    # Russian industry acronyms that are NOT generic
    industry_acronyms = {
        'СПГ', 'АЗС', 'МСБ', 'ОРЭМ', 'ДПМ', 'ФСТ', 'СУЭК', 'АТС', 'ЖКХ',
        'КОМ', 'РСВ', 'НЛМК', 'ММК', 'МТС', 'ВТБ', 'Сбер', 'Тева', 'ФСБ',
        'Циан', 'Юла', 'ЕГРН', 'ПИК', 'Озон', 'РЖД', 'САПР', 'ЧПУ',
        'ФосАгро', 'Лукойл', 'Газпром', 'Роснефть', 'Сургутнефтегаз',
        'Татнефть', 'Башнефть', 'НОВАТЭК', 'РусГидро', 'Аэрофлот',
        'Магнит', 'Пятерочка', 'Перекресток', 'Дикси', 'Лента',
        'MOEX', 'ЦБ', 'ФАС', 'Минцифры', '44-ФЗ', '223-ФЗ',
    }
    generic_patterns = [
        r'^компания$',
        r'^предприятие$',
        r'^организация$',
        r'^сервис$',
        r'^технологии?$',
        r'^цифровы[е|ой]$',
        r'^производств[о|а|у]$',
        r'^рынок$',
        r'^инфраструктур[а|ы]$',
        r'^материалы?$',
        r'^продукци[я|и]$',
        r'^оборудовани[е|я]$',
        r'^решени[я|е]$',
        r'^поставщик[и|ов]?$',
        r'^клиент[ы|ов]?$',
    ]
    generic_wikilinks = []
    for wl in wikilinks:
        wl_stripped = wl.strip()
        # Skip known industry acronyms
        if wl_stripped in industry_acronyms:
            continue
        # Skip acronyms (all uppercase, 2-6 chars)
        if re.match(r'^[A-ZА-ЯЁ]{2,6}$', wl_stripped):
            continue
        # Skip very short wikilinks that are part of pipe syntax
        base = wl_stripped.split('|')[0].strip()
        for pat in generic_patterns:
            if re.match(pat, base, re.IGNORECASE):
                generic_wikilinks.append(wl)
                break
    if generic_wikilinks:
        issues.append(f"Generic wikilinks: {', '.join(generic_wikilinks)}")

    # 2. Check client/supplier section length
    client_match = re.search(r'## Ключевые клиенты? и поставщики?', content)
    if client_match:
        section = content[client_match.end():]
        next_section = re.search(r'\n## ', section)
        if next_section:
            section = section[:next_section.start()]
        # Count non-empty lines
        lines = [l for l in section.strip().split('\n') if l.strip()]
        if len(lines) < 4:
            issues.append(f"Short clients/suppliers section: {len(lines)} lines")

    # 3. Check for required sections
    required = [
        '## Описание бизнеса',
        '## Положение в цепочке поставок',
        '## Ключевые клиенты и поставщики',
        '## Финансовый обзор',
    ]
    for sec in required:
        if sec not in content:
            issues.append(f"Missing section: {sec}")

    # 4. Check wikilink count
    if len(wikilinks) < 10:
        issues.append(f"Too few wikilinks: {len(wikilinks)} (want >= 10)")

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

    print(f"=" * 60)
    print(f"TOTAL: {total} Russian reports audited")
    print(f"Reports with issues: {len(all_issues)}/{total}")
    print(f"=" * 60)

    if all_issues:
        print()
        for key, issues in sorted(all_issues.items()):
            print(f"  [{key}]")
            for issue in issues:
                print(f"    - {issue}")
            print()

    # Return non-zero if issues found
    if all_issues:
        sys.exit(1)
    else:
        print("Все отчёты проходят проверку качества.")
        sys.exit(0)


if __name__ == "__main__":
    main()
