import os
from pathlib import Path

from sqlalchemy import URL


def read_secret(path: str | Path) -> str:
    value = Path(path).read_text().strip()
    if not value:
        raise ValueError(f"Empty secret file: {path}")
    return value


def database_url() -> str | URL:
    if value := os.environ.get("DATABASE_URL"):
        return value  # explicit override for tests and development outside Compose
    secret = os.environ.get("DATABASE_PASSWORD_FILE")
    if not secret:
        raise RuntimeError("Set DATABASE_PASSWORD_FILE or an explicit DATABASE_URL")
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("DATABASE_USER", "kickpick_api"),
        password=read_secret(secret),
        host=os.environ.get("DATABASE_HOST", "db"),
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        database=os.environ.get("DATABASE_NAME", "kickpick"),
    )


DATABASE_URL = database_url()
HISTORY_SEASONS = int(os.environ.get("HISTORY_SEASONS", "0"))  # 0 = every season FotMob lists (since 2010)
REQUEST_INTERVAL = float(os.environ.get("REQUEST_INTERVAL", "1.0"))  # seconds between FotMob requests, +0–0.5 s jitter

# (FotMob league id, slug, display name, kind) — order is the order in the app
COMPETITIONS = [
    (47, "premier-league", "Premier League", "league"),
    (87, "laliga", "LaLiga", "league"),
    (55, "serie-a", "Serie A", "league"),
    (54, "bundesliga", "Bundesliga", "league"),
    (53, "ligue-1", "Ligue 1", "league"),
    (57, "eredivisie", "Eredivisie", "league"),
    (61, "liga-portugal", "Liga Portugal", "league"),
    (40, "belgian-pro-league", "Belgian Pro League", "league"),
    (71, "super-lig", "Süper Lig", "league"),
    (64, "scottish-premiership", "Scottish Premiership", "league"),
    (48, "championship", "Championship", "league"),
    (146, "2-bundesliga", "2. Bundesliga", "league"),
    (86, "serie-b", "Serie B", "league"),
    (140, "laliga2", "LaLiga 2", "league"),
    (110, "ligue-2", "Ligue 2", "league"),
    (536, "saudi-pro-league", "Saudi Pro League", "league"),
    (130, "mls", "MLS", "league"),
    (268, "brasileirao", "Brasileirão", "league"),
    (112, "liga-profesional", "Liga Profesional", "league"),
    (230, "liga-mx", "Liga MX", "league"),
    (42, "champions-league", "Champions League", "cup"),
    (73, "europa-league", "Europa League", "cup"),
    (10216, "conference-league", "Conference League", "cup"),
    (50, "euro", "EURO", "international"),
    (77, "world-cup", "World Cup", "international"),
    (9806, "nations-league", "Nations League", "international"),
]
