{{ config(schema='SILVER', materialized='table') }}

SELECT
    steam_id,
    app_id,
    game_name,
    playtime_minutes / 60.0  AS playtime_hours,
    loaded_at                AS updated_at
FROM {{ source('bronze', 'RAW_USER_GAMES') }}
WHERE playtime_minutes > 0
