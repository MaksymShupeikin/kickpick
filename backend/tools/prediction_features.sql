-- Read-only example: one training row per finished match in the five major leagues.
-- Change the sample dates in settings for a larger offline export.
-- History = last five games in the SAME competition, across seasons.
-- result_delay is an approximation: we do not yet store historical finished_at/observed_at.
-- kickoff + 3h is not proof of the actual publication time, especially for suspended games.
WITH settings AS (
    SELECT timestamptz '2026-10-01 00:00:00+00' AS date_from,
           timestamptz '2026-10-16 00:00:00+00' AS date_to,
           interval '24 hours' AS forecast_horizon,
           interval '3 hours' AS result_delay
), targets AS MATERIALIZED (
    SELECT m.id AS match_id, m.kickoff,
           m.kickoff - cfg.forecast_horizon AS prediction_time,
           cfg.result_delay, c.id AS competition_id, c.slug AS league, s.name AS season,
           m.home_team_id, m.away_team_id,
           CASE WHEN m.home_score > m.away_score THEN 'H'
                WHEN m.home_score < m.away_score THEN 'A'
                ELSE 'D' END AS target
    FROM matches m
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    CROSS JOIN settings cfg
    WHERE m.status = 'FT'
      AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
      AND m.kickoff >= cfg.date_from AND m.kickoff < cfg.date_to
      AND c.slug IN ('premier-league', 'laliga', 'serie-a', 'bundesliga', 'ligue-1')
), side_features AS MATERIALIZED (
    SELECT t.match_id, side.name, f.*
    FROM targets t
    CROSS JOIN LATERAL (VALUES ('home', t.home_team_id), ('away', t.away_team_id)) AS side(name, team_id)
    CROSS JOIN LATERAL (
        SELECT count(*) AS history_games,
               avg(p.goals_for) AS goals_for_5,
               avg(p.goals_against) AS goals_against_5,
               avg(CASE WHEN p.goals_for > p.goals_against THEN 3.0
                        WHEN p.goals_for = p.goals_against THEN 1.0 ELSE 0.0 END) AS points_5,
               avg(xg.for_value) AS xg_for_5,
               avg(xg.against_value) AS xg_against_5,
               count(xg.for_value) AS xg_history_games,
               max(p.kickoff) AS latest_history_kickoff,
               max(p.kickoff + t.result_delay) AS latest_assumed_available_at
        FROM (
            SELECT h.id, h.kickoff, h.details,
                   h.home_team_id = side.team_id AS played_at_home,
                   CASE WHEN h.home_team_id = side.team_id THEN h.home_score ELSE h.away_score END AS goals_for,
                   CASE WHEN h.home_team_id = side.team_id THEN h.away_score ELSE h.home_score END AS goals_against
            FROM matches h
            JOIN seasons hs ON hs.id = h.season_id
            WHERE (h.home_team_id = side.team_id OR h.away_team_id = side.team_id)
              AND hs.competition_id = t.competition_id
              AND h.status = 'FT'
              AND h.home_score IS NOT NULL AND h.away_score IS NOT NULL
              AND h.kickoff < t.prediction_time - t.result_delay
            ORDER BY h.kickoff DESC, h.id DESC
            LIMIT 5
        ) p
        LEFT JOIN LATERAL (
            SELECT CASE WHEN stat->>'home' ~ '^[0-9]+([.][0-9]+)?$'
                             AND stat->>'away' ~ '^[0-9]+([.][0-9]+)?$'
                        THEN (stat->>CASE WHEN p.played_at_home THEN 'home' ELSE 'away' END)::double precision
                   END AS for_value,
                   CASE WHEN stat->>'home' ~ '^[0-9]+([.][0-9]+)?$'
                             AND stat->>'away' ~ '^[0-9]+([.][0-9]+)?$'
                        THEN (stat->>CASE WHEN p.played_at_home THEN 'away' ELSE 'home' END)::double precision
                   END AS against_value
            FROM jsonb_array_elements(coalesce(p.details->'stats', '[]'::jsonb)) stat
            WHERE stat->>'name' = 'Expected goals (xG)'
            LIMIT 1
        ) xg ON true
    ) f
)
SELECT t.match_id, t.kickoff, t.prediction_time, t.league, t.season,
       t.home_team_id, t.away_team_id,
       h.history_games AS home_history_games, a.history_games AS away_history_games,
       h.goals_for_5 AS home_goals_for_5, a.goals_for_5 AS away_goals_for_5,
       h.goals_against_5 AS home_goals_against_5, a.goals_against_5 AS away_goals_against_5,
       h.points_5 AS home_points_5, a.points_5 AS away_points_5,
       h.xg_for_5 AS home_xg_for_5, a.xg_for_5 AS away_xg_for_5,
       h.xg_against_5 AS home_xg_against_5, a.xg_against_5 AS away_xg_against_5,
       h.xg_history_games AS home_xg_history_games, a.xg_history_games AS away_xg_history_games,
       h.latest_history_kickoff AS home_latest_history_kickoff,
       a.latest_history_kickoff AS away_latest_history_kickoff,
       h.latest_assumed_available_at AS home_latest_assumed_available_at,
       a.latest_assumed_available_at AS away_latest_assumed_available_at,
       t.target
FROM targets t
JOIN side_features h ON h.match_id = t.match_id AND h.name = 'home'
JOIN side_features a ON a.match_id = t.match_id AND a.name = 'away'
ORDER BY t.kickoff, t.match_id;
