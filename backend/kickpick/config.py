import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://kickpick:kickpick@localhost:5432/kickpick")
HISTORY_SEASONS = int(os.environ.get("HISTORY_SEASONS", "5"))

# (FotMob league id, slug, display name, kind) — order is the order in the app
COMPETITIONS = [
    (47, "premier-league", "Premier League", "league"),
    (87, "laliga", "LaLiga", "league"),
    (55, "serie-a", "Serie A", "league"),
    (54, "bundesliga", "Bundesliga", "league"),
    (53, "ligue-1", "Ligue 1", "league"),
    (57, "eredivisie", "Eredivisie", "league"),
    (42, "champions-league", "Champions League", "cup"),
    (73, "europa-league", "Europa League", "cup"),
    (10216, "conference-league", "Conference League", "cup"),
    (50, "euro", "EURO", "international"),
    (77, "world-cup", "World Cup", "international"),
    (9806, "nations-league", "Nations League", "international"),
]
