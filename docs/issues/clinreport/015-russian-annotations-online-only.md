# 015 · Russian annotations need internet; no reload / offline copy

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P3 | robustness | `database.get_ru_annotations`, `service.ru_annotations` |

## Problem

The OMIM/secondary-findings Russian overrides are downloaded from a public Google Sheet during «Обработать» (10 s timeout per
sheet, cached 10 min per GUI process, a failure is also cached 10 min). Consequences:

- offline or with Google blocked → reports fall back to English OMIM text (a warning banner is shown);
- a sheet edit is picked up only after ≤ 10 min or a GUI restart; no "reload" button;
- first «Обработать» after start is slower (two HTTP requests);
- the sheet URL is public and hard-coded.

## TODO

- [ ] Persist the last successful download to `<OC conf dir>/clinreport_ru_annotations.json` and use it when offline
      (banner: «используются сохранённые аннотации от <date>»).
- [ ] «Обновить аннотации» action (settings dialog) → clears the cache.
- [ ] Make the sheet URL/gids a setting (default = current).

## Acceptance

Offline processing uses the last known Russian texts; the user can force a refresh.
