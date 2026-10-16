#!/usr/bin/env bash
# Load a KickPick database dump (pg_dump -Fc) into a fresh install, before its first `docker compose up`.
# Afterwards `docker compose up -d --build` gives the tables to the migration role and grants the others
# (db-init), and the migrations find the schema already at head.
#
#   deploy/restore.sh kickpick.dump
set -euo pipefail
dump=${1:?usage: deploy/restore.sh path/to/kickpick.dump}
[ -f "$dump" ] || { echo "No such file: $dump" >&2; exit 1; }
cd "$(dirname "$0")/.."

docker compose up -d --wait db
if [ "$(docker compose exec -T db psql -U kickpick -d kickpick -Atc "select to_regclass('public.matches') is not null")" = t ]; then
  echo "The database already has tables: restore only into a fresh install." >&2
  echo "On a fresh install, 'docker compose down -v' deletes the empty database first." >&2
  exit 1
fi
# objects belong to the admin for now; db-init hands them to the migration role
docker compose exec -T db pg_restore -U kickpick -d kickpick --no-owner --no-privileges --exit-on-error < "$dump"
docker compose exec -T db psql -U kickpick -d kickpick -Atc \
  "select 'restored: ' || (select count(*) from matches) || ' matches, ' || (select count(*) from players) || ' players'"
