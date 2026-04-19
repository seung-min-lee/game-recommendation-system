{{ config(schema='GOLD', materialized='table') }}

-- 숨겨진 명작: 고평점 + 선호 장르 + 미소유 게임
WITH user_top_genres AS (
    SELECT
        ug.steam_id,
        f.value::STRING                             AS genre,
        SUM(ug.playtime_hours)                      AS total_hours,
        ROW_NUMBER() OVER (PARTITION BY ug.steam_id ORDER BY SUM(ug.playtime_hours) DESC) AS rn
    FROM {{ ref('user_game_stats') }} ug
    JOIN {{ ref('game_features') }} gf ON gf.app_id = ug.app_id,
    LATERAL FLATTEN(input => gf.genres) f
    GROUP BY ug.steam_id, f.value::STRING
    QUALIFY rn <= 3
)
SELECT
    utg.steam_id,
    gf.app_id,
    gf.name                                         AS game_name,
    COUNT(*) * (gf.metacritic / 100.0)              AS score,
    gf.metacritic,
    gf.genres,
    CONCAT('https://cdn.akamai.steamstatic.com/steam/apps/', gf.app_id, '/header.jpg') AS header_image,
    CONCAT('https://store.steampowered.com/app/', gf.app_id) AS store_url,
    CURRENT_TIMESTAMP()                             AS updated_at
FROM user_top_genres utg
JOIN {{ ref('game_features') }} gf,
LATERAL FLATTEN(input => gf.genres) f
WHERE f.value::STRING = utg.genre
  AND gf.metacritic >= 87
  AND NOT EXISTS (
      SELECT 1 FROM {{ ref('user_game_stats') }} owned
      WHERE owned.steam_id = utg.steam_id AND owned.app_id = gf.app_id
  )
GROUP BY utg.steam_id, gf.app_id, gf.name, gf.metacritic, gf.genres
QUALIFY ROW_NUMBER() OVER (PARTITION BY utg.steam_id ORDER BY score DESC) <= 10
