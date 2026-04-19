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
        """Gold Layer RECOMMEND_CF 테이블에서 협업 필터링 추천 결과 조회"""
        sql = """
            SELECT GAME_ID, GAME_NAME, SCORE, GENRES, HEADER_IMAGE, STORE_URL
            FROM GOLD.RECOMMEND_CF
            WHERE STEAM_ID = %(steam_id)s
            ORDER BY SCORE DESC
            LIMIT 10
        """
        return self._query(sql, {"steam_id": steam_id})

    def get_cbf_recommendations(self, steam_id: str) -> list[dict]:
        """Gold Layer RECOMMEND_CBF 테이블에서 콘텐츠 기반 추천 결과 조회"""
        sql = """
            SELECT GAME_ID, GAME_NAME, SIMILARITY AS SCORE, GENRES, HEADER_IMAGE, STORE_URL
            FROM GOLD.RECOMMEND_CBF
            WHERE STEAM_ID = %(steam_id)s
            ORDER BY SIMILARITY DESC
            LIMIT 10
        """
        return self._query(sql, {"steam_id": steam_id})

    def get_genre_trend(self, steam_id: str) -> list[dict]:
        """Gold Layer GENRE_TREND 테이블에서 장르 트렌드 추천 조회"""
        sql = """
            SELECT GAME_ID, GAME_NAME, TREND_SCORE AS SCORE, GENRES, HEADER_IMAGE, STORE_URL
            FROM GOLD.GENRE_TREND
            WHERE STEAM_ID = %(steam_id)s
            ORDER BY TREND_SCORE DESC
            LIMIT 10
        """
        return self._query(sql, {"steam_id": steam_id})

    def has_recommendations(self, steam_id: str) -> bool:
        """해당 steam_id의 추천 결과가 Gold Layer에 존재하는지 확인"""
        sql = """
            SELECT COUNT(*) AS CNT
            FROM GOLD.RECOMMEND_CF
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
            return [dict(r) for r in rows]
        except Exception as e:
            raise RuntimeError(f"Snowflake 쿼리 실패: {e}")


snowflake_svc = SnowflakeService()
