"""Evaluate only forecasts actually published before the match, by timing cohort."""
from datetime import timedelta

import numpy as np
from psycopg.rows import dict_row

from .training import metrics, write_json


def quality_report(connection, *, days=180):
    now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            cursor.execute("""
                SELECT p.model_version,p.league,p.generated_at,p.scheduled_kickoff,
                       p.p_home,p.p_draw,p.p_away,p.baselines,
                       r.kind,r.reason,r.home_score,r.away_score,
                       (r.kind='finished' AND (m.status <> 'FT' OR m.home_score IS DISTINCT FROM r.home_score
                        OR m.away_score IS DISTINCT FROM r.away_score OR m.kickoff <> r.actual_kickoff
                        OR m.home_team_id <> p.home_team_id OR m.away_team_id <> p.away_team_id)) AS revised,
                       v.metadata->>'champion' AS champion
                FROM match_predictions p JOIN prediction_models v ON v.version=p.model_version
                JOIN matches m ON m.id=p.match_id
                LEFT JOIN prediction_results r ON r.prediction_id=p.id
                WHERE p.generated_at >= %s AND p.generated_at <= %s
                ORDER BY p.model_version,p.generated_at,p.id
            """, (now - timedelta(days=days), now))
            rows = cursor.fetchall()
    groups = {}
    for row in rows:
        lead_hours = (row["scheduled_kickoff"] - row["generated_at"]).total_seconds() / 3600
        cohort = "on_time_24h" if 23.5 <= lead_hours <= 24.5 else "late" if lead_hours < 23.5 else "early"
        key = (row["model_version"], cohort)
        groups.setdefault(key, []).append(row)

    def evaluate(finished):
        y = np.array([0 if row["home_score"] > row["away_score"] else
                      1 if row["home_score"] == row["away_score"] else 2 for row in finished])
        names = sorted(set.intersection(*(set(row["baselines"]) for row in finished)))
        return {name: metrics(y, np.array([row["baselines"][name] for row in finished])) for name in names}

    evaluated = []
    for (version, cohort), group in sorted(groups.items()):
        finished = [row for row in group if row["kind"] == "finished" and not row["revised"]]
        result = {
            "model_version": version, "champion": group[0]["champion"], "cohort": cohort,
            "total": len(group), "pending": sum(row["kind"] is None for row in group),
            "void": sum(row["kind"] == "void" for row in group),
            "revised_results_excluded": sum(bool(row["revised"]) for row in group),
            "evaluated": len(finished),
            "sample_status": "collecting" if len(finished) < 300 else "available_for_review",
            "metrics": evaluate(finished) if finished else None,
            "by_league": {league: evaluate([row for row in finished if row["league"] == league])
                          for league in sorted({row["league"] for row in finished})},
        }
        evaluated.append(result)
    return {
        "generated_at": now.isoformat(), "days": days, "groups": evaluated,
        "notes": ["Only immutable forecasts published before kickoff; no historical backfill.",
                  "24h cohort accepts a 30-minute scheduling tolerance; late forecasts are separate.",
                  "Postponed/cancelled games and later revised results are excluded from metrics.",
                  "300 games permit initial review, not proof of superiority or profitability."],
    }


def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_json(temporary, report)
    temporary.replace(path)
