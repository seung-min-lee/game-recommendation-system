{{ config(schema='GOLD', materialized='table') }}

-- 협업 필터링: 유사 유저 기반 추천
-- 같은 게임을 플레이한 유저들의 게임 목록에서 미소유 게임 추천
WITH user_games AS (
    SELECT steam_id, app_id, playtime_hours
    FROM {{ ref('user_game_stats') }}
),
similar_users AS (
    SELECT
        a.steam_id                                  AS target_user,
        b.steam_id                                  AS similar_user,
        COUNT(*)                                    AS common_games,
        COUNT(*) * 1.0 /
            (SELECT COUNT(*) FROM user_games WHERE steam_id = a.steam_id) AS jaccard_sim
    FROM user_games a
    JOIN user_games b ON a.app_id = b.app_id AND a.steam_id != b.steam_id
    GROUP BY a.steam_id, b.steam_id
    HAVING COUNT(*) >= 1
),
recommendations AS (
    SELECT
        su.target_user                              AS steam_id,
        ug.app_id,
        SUM(su.jaccard_sim)                         AS score
    FROM similar_users su
    JOIN user_games ug ON ug.steam_id = su.similar_user
    WHERE NOT EXISTS (
        SELECT 1 FROM user_games owned
        WHERE owned.steam_id = su.target_user AND owned.app_id = ug.app_id
    )
    GROUP BY su.target_user, ug.app_id
)
SELECT
    r.steam_id,
    r.app_id,
    g.name                                          AS game_name,
    r.score,
    CONCAT('https://cdn.akamai.steamstatic.com/steam/apps/', r.app_id, '/header.jpg') AS header_image,
    CONCAT('https://store.steampowered.com/app/', r.app_id) AS store_url,
    CURRENT_TIMESTAMP()                             AS updated_at
FROM recommendations r
JOIN {{ ref('game_features') }} g ON g.app_id = r.app_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.steam_id ORDER BY r.score DESC) <= 10
