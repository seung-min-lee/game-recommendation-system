{{ config(schema='SILVER', materialized='table') }}

SELECT
    app_id,
    name,
    genres,
    tags,
    metacritic,
    price,
    loaded_at AS updated_at
FROM {{ source('bronze', 'RAW_GAME_METADATA') }}
