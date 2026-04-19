import snowflake.connector
from config import config


class SnowflakeService:
    def __init__(self):
        self._conn = None

    def _connect(self):
        return snowflake.connector.connect(
            account=config.SNOWFLAKE_ACCOUNT,
            user=config.SNOWFLAKE_USER,
            password=config.SNOWFLAKE_PASSWORD,
            database=config.SNOWFLAKE_DATABASE,
            schema=config.SNOWFLAKE_SCHEMA,
            warehouse=config.SNOWFLAKE_WAREHOUSE,
            role=config.SNOWFLAKE_ROLE,
        )

    def get_cf_recommendations(self, steam_id: str) -> list[dict]:
        sql = """
            SELECT APP_ID, GAME_NAME, SCORE, HEADER_IMAGE, STORE_URL
            FROM GOLD.RECOMMEND_CF
            WHERE STEAM_ID = %(steam_id)s
            ORDER BY SCORE DESC
            LIMIT 10
        """
        return self._query(sql, {"steam_id": steam_id})

    def get_cbf_recommendations(self, steam_id: str) -> list[dict]:
        sql = """
            SELECT APP_ID, GAME_NAME, SIMILARITY AS SCORE, GENRES, HEADER_IMAGE, STORE_URL
            FROM GOLD.RECOMMEND_CBF
            WHERE STEAM_ID = %(steam_id)s
            ORDER BY SIMILARITY DESC
            LIMIT 10
        """
        return self._query(sql, {"steam_id": steam_id})

    def get_genre_trend(self, steam_id: str) -> list[dict]:
        sql = """
            SELECT APP_ID, GAME_NAME, SCORE, METACRITIC, GENRES, HEADER_IMAGE, STORE_URL
            FROM GOLD.HIDDEN_GEMS
            WHERE STEAM_ID = %(steam_id)s
            ORDER BY SCORE DESC
            LIMIT 10
        """
        return self._query(sql, {"steam_id": steam_id})

    def has_recommendations(self, steam_id: str) -> bool:
        sql = """
            SELECT COUNT(*) AS CNT
            FROM GOLD.RECOMMEND_CBF
            WHERE STEAM_ID = %(steam_id)s
        """
        rows = self._query(sql, {"steam_id": steam_id})
        return rows[0]["CNT"] > 0 if rows else False

    def _query(self, sql: str, params: dict) -> list[dict]:
        try:
            conn = self._connect()
            cursor = conn.cursor(snowflake.connector.DictCursor)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return [{k.lower(): v for k, v in dict(r).items()} for r in rows]
        except Exception as e:
            raise RuntimeError(f"Snowflake 쿼리 실패: {e}")


snowflake_svc = SnowflakeService()
