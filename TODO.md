# TODO

Живой список задач по репозиторию. Обновляется после каждого automation round.

## Выполнено в этом раунде (2026-04-09, automation round)

- [x] Сгенерирована следующая волна `MOEXBMI`: `AQUA` (Инарктика), `BELU` (НоваБев Групп), `ETLN` (Эталон), `EUTR` (ЕвроТранс), `DATA` (Аренадата) через `scripts/generate_moex_reports.py`.
- [x] Обогащены карточки `AQUA`, `BELU`, `ETLN`, `EUTR`, `DATA`: добавлены русскоязычные описания бизнеса, положение в цепочке поставок, клиенты/поставщики и тематические `[[wikilinks]]`.
- [x] `ETLN` перенесён в `Real Estate/`, `EUTR` — в `Industrials/`, `DATA` — в `Technology/`.
- [x] `scripts/build_themes.py` расширен новыми российскими темами: `автомобилестроение`, `АЗС`, `конгломерат`, `программное обеспечение`.
- [x] Пересобраны `themes/`, `WIKILINKS.md` и `network/` после расширения RU-корпуса; локальные проверки пройдены через `.venv/bin/python -m py_compile scripts/build_themes.py scripts/generate_moex_reports.py scripts/add_ticker.py scripts/utils.py scripts/build_wikilink_index.py scripts/build_network.py`.
- [x] На 2026-04-09 повторно проверена очередь `MOEXBMI`: покрыто 17 из 20, остались `APTK`, `BAZA`, `ELFV`.
- [x] На 2026-04-09 `gh issue list` и `gh pr list` по-прежнему недоступны без `gh auth login` (HTTP 401).

## Следующие действия

- [ ] Продолжить следующую подочередь `MOEXBMI`: `APTK`, `BAZA`, `ELFV`.
- [ ] Дожать источник финансовых данных для `X5`: карточка уже заведена по официальному составу `MOEXBC`, но текущий `yfinance` не отдаёт пригодные метаданные, valuation snapshot и финансовые таблицы.
- [ ] Дожать источник финансовых данных для `YDEX` и `OZON`: текущий `yfinance` по-прежнему не отдаёт пригодные метаданные и финансовые таблицы даже после явных alias-кандидатов.
- [ ] Найти источник полных финансовых таблиц для `T`: `TCSG.ME` уже даёт капитализацию, EV и valuation snapshot, но годовые и квартальные формы в `yfinance` остаются пустыми.
- [ ] Рассмотреть архивацию legacy-тайваньского корпуса (1,734 файла) в отдельную директорию `Pilot_Reports_LEGACY/` для уменьшения шума в автогенерируемых артефактах.

## Внешние очереди

- [ ] Открытые issues: на 2026-04-09 `gh issue list --repo denis-gordeev/My-RU-Coverage` недоступен без авторизации и возвращает `HTTP 401: Requires authentication`; нужна авторизация через `gh auth login` или публичная ручная перепроверка.
- [ ] Открытые PR: на 2026-04-09 `gh pr list --repo denis-gordeev/My-RU-Coverage --json number,title,headRefName,state` недоступен без авторизации и возвращает `HTTP 401: Requires authentication`; нужна авторизация через `gh auth login` или публичная ручная перепроверка.
