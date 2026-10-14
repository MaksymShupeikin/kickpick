# KickPick

Футбольные данные (топ-лиги, еврокубки, ЧЕ, ЧМ, Лига наций) из FotMob → Postgres → FastAPI → iOS.

- Дизайн-система: [design.md](design.md)
- Спецификация: [docs/superpowers/specs/2026-10-14-kickpick-design.md](docs/superpowers/specs/2026-10-14-kickpick-design.md)

## Бэкенд

```bash
docker compose up -d --build                                   # postgres + api (:8000) + collector
docker compose exec collector python -m kickpick.collector backfill   # один раз: прошлые сезоны
docker compose logs -f collector
```

Тесты (нужен запущенный `db`):

```bash
cd backend && uv run pytest
```

Обновить фикстуры FotMob, если поменялся формат: `cd backend && uv run python tests/fixtures/fetch.py`.

## iOS

```bash
cd ios && xcodegen && open KickPick.xcodeproj
```

Симулятор ходит на `http://localhost:8000`. Для iPhone в той же Wi-Fi поменяйте `API_BASE_URL` в `ios/project.yml` на IP Мака и перегенерируйте проект.
API без авторизации — не открывайте порт 8000 в интернет.
