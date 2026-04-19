{{ config(schema='GOLD', materialized='table') }}

-- 콘텐츠 기반 필터링: 유저 선호 장르 기반 추천
WITH user_genre_weight AS (
    SELECT
        ug.steam_id,
        f.value::STRING                             AS genre,
        SUM(ug.playtime_hours)                      AS total_hours
    FROM {{ ref('user_game_stats') }} ug
    JOIN {{ ref('game_features') }} gf ON gf.app_id = ug.app_id,
    LATERAL FLATTEN(input => gf.genres) f
    GROUP BY ug.steam_id, f.value::STRING
),
genre_score AS (
    SELECT
        ugw.steam_id,
        gf.app_id,
        SUM(ugw.total_hours)                        AS similarity
    FROM user_genre_weight ugw
    JOIN {{ ref('game_features') }} gf,
    LATERAL FLATTEN(input => gf.genres) f
    WHERE f.value::STRING = ugw.genre
    GROUP BY ugw.steam_id, gf.app_id
)
SELECT
    gs.steam_id,
    gs.app_id,
    gf.name                                         AS game_name,
    gs.similarity,
    gf.genres,
    CONCAT('https://cdn.akamai.steamstatic.com/steam/apps/', gs.app_id, '/header.jpg') AS header_image,
    CONCAT('https://store.steampowered.com/app/', gs.app_id) AS store_url,
    CURRENT_TIMESTAMP()                             AS updated_at
FROM genre_score gs
JOIN {{ ref('game_features') }} gf ON gf.app_id = gs.app_id
WHERE NOT EXISTS (
    SELECT 1 FROM {{ ref('user_game_stats') }} owned
    WHERE owned.steam_id = gs.steam_id AND owned.app_id = gs.app_id
)
QUALIFY ROW_NUMBER() OVER (PARTITION BY gs.steam_id ORDER BY gs.similarity DESC) <= 10
