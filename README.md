# My RU Coverage

База исследовательских заметок по акциям с упором на российский рынок. Репозиторий использует Markdown-отчёты, связанные через `[[wikilinks]]`, чтобы собирать граф компаний, технологий, материалов и конечных рынков.

## Текущее состояние

- 42 российских отчёта в `Pilot_Reports/` проходят аудит качества (`scripts/audit_ru_reports.py`).
- `themes/` содержит 31 российскую тему.
- `WIKILINKS.md`, `network/graph_data.json` и `network/index.html` пересобираются из актуального российского корпуса.
- Для MOEX-workflow приоритетны `scripts/moex_blue_chip_queue.py`, `scripts/generate_moex_reports.py`, `scripts/update_financials.py`, `scripts/update_valuation.py`.
- Статус-сводка по покрытию: `python scripts/moex_status.py`.
- Legacy-тайваньский корпус описан в [LEGACY.md](LEGACY.md).

## Что внутри

- `Pilot_Reports/` — карточки компаний по отраслям.
- `scripts/` — генерация, обновление финансов, аудит, сбор индекса викалинков, граф связей.
- `WIKILINKS.md` — автогенерируемый индекс сущностей.
- `network/` — интерактивный граф ко-встречаемости викалинков.
- `themes/` — тематические подборки и карты цепочек поставок.
- `TODO.md` — живой журнал automation rounds, сделанных фиксов и следующей очереди.
- `Pilot_Reports_LEGACY/` — архив тайваньского корпуса (не обслуживается).

Каждый новый отчёт должен содержать:

1. `## Описание бизнеса` — краткое описание бизнеса и метаданные.
2. `## Положение в цепочке поставок` — позиция в цепочке поставок.
3. `## Ключевые клиенты и поставщики` — основные контрагенты.
4. `## Финансовый обзор` — финансовый блок, который обновляется скриптами.

## Быстрый старт

```bash
pip install -r requirements.txt
```

Добавить новый тикер:

```bash
python scripts/add_ticker.py SBER Сбер
python scripts/add_ticker.py GAZP Газпром --sector Энергетика
```

Обновить финансовый блок:

```bash
python scripts/update_financials.py SBER
python scripts/update_financials.py SBER GAZP
python scripts/update_financials.py --sector Энергетика
```

Обновить только мультипликаторы:

```bash
python scripts/update_valuation.py SBER
python scripts/update_valuation.py --sector Энергетика
```

Применить заранее подготовленное обогащение:

```bash
python scripts/update_enrichment.py --data enrichment.json SBER
```

Прогнать аудит качества российских карточек:

```bash
python scripts/audit_ru_reports.py
```

Статус-сводка по покрытию MOEX:

```bash
python scripts/moex_status.py
```

Пересобрать индекс и граф:

```bash
python scripts/build_wikilink_index.py
python scripts/build_network.py
python scripts/build_themes.py
```

Проверить актуальное покрытие официальной очереди MOEX:

```bash
python scripts/moex_blue_chip_queue.py
python scripts/moex_blue_chip_queue.py --index MOEXBC
python scripts/moex_blue_chip_queue.py --index MOEXBMI
```

Сгенерировать базовые MOEX-карточки из живой очереди:

```bash
python scripts/generate_moex_reports.py
python scripts/generate_moex_reports.py --index MOEXBMI --top 5
python scripts/generate_moex_reports.py DOMRF AKRN AFLT
```

## Правила данных

- Используйте конкретные `[[wikilinks]]`, а не общие категории.
- Для новых материалов основной язык описаний и заголовков: русский.
- Финансовый раздел не редактируется вручную.
- Единицы: `.ME` -> `млн руб.`
- Российские карточки не должны содержать legacy-темы и китайские викалинки.

## Источники

- Финансовые данные: `yfinance`.
- Бизнес-описания и связи: сайты эмитентов, e-disclosure.ru, годовые отчёты, презентации для инвесторов, отраслевые обзоры.

## Ограничения

- `yfinance` не закрывает все российские тикеры по годовым и квартальным формам, поэтому часть отчётов требует внешних источников или ручного ввода.
- Legacy-корпус по Тайваню описан в [LEGACY.md](LEGACY.md).
