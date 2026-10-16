-- One read-only snapshot. Never use current standings, squad totals or target lineups.
SELECT m.id AS match_id, m.kickoff, m.status,
       c.slug AS league, s.name AS season,
       m.home_team_id, m.away_team_id,
       ht.name AS home_team, at.name AS away_team,
       m.home_score, m.away_score,
       stats.home_xg, stats.away_xg, stats.home_shots, stats.away_shots,
       stats.home_shots_on_target, stats.away_shots_on_target,
       stats.home_possession, stats.away_possession,
       stats.home_corners, stats.away_corners
FROM matches m
JOIN seasons s ON s.id = m.season_id
JOIN competitions c ON c.id = s.competition_id
JOIN teams ht ON ht.id = m.home_team_id
JOIN teams at ON at.id = m.away_team_id
LEFT JOIN LATERAL (
    SELECT max(h) FILTER (WHERE name = 'Expected goals (xG)') AS home_xg,
           max(a) FILTER (WHERE name = 'Expected goals (xG)') AS away_xg,
           max(h) FILTER (WHERE name = 'Total shots') AS home_shots,
           max(a) FILTER (WHERE name = 'Total shots') AS away_shots,
           max(h) FILTER (WHERE name = 'Shots on target') AS home_shots_on_target,
           max(a) FILTER (WHERE name = 'Shots on target') AS away_shots_on_target,
           max(h) FILTER (WHERE name = 'Ball possession') AS home_possession,
           max(a) FILTER (WHERE name = 'Ball possession') AS away_possession,
           max(h) FILTER (WHERE name = 'Corners') AS home_corners,
           max(a) FILTER (WHERE name = 'Corners') AS away_corners
    FROM (
        SELECT stat->>'name' AS name,
               CASE WHEN stat->>'home' ~ '^[0-9]+([.][0-9]+)?$'
                    THEN (stat->>'home')::double precision END AS h,
               CASE WHEN stat->>'away' ~ '^[0-9]+([.][0-9]+)?$'
                    THEN (stat->>'away')::double precision END AS a
        FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(m.details->'stats') = 'array'
                 THEN m.details->'stats' ELSE '[]'::jsonb END
        ) stat
    ) parsed
) stats ON true
WHERE c.slug = ANY(%(leagues)s)
  AND m.kickoff >= timestamptz '2016-07-01'
  AND (
      (m.status = 'FT' AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
       AND m.home_score >= 0 AND m.away_score >= 0
       AND m.kickoff + interval '3 hours' < %(as_of)s)
      OR (m.status = 'NS' AND m.kickoff > %(as_of)s
          AND m.kickoff <= %(as_of)s + interval '24 hours')
  )
ORDER BY m.kickoff, m.id;
