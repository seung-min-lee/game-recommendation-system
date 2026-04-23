import os

def _get(key: str, default: str = "") -> str:
    """환경변수 → Streamlit secrets 순으로 fallback"""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # Steam
    STEAM_API_KEY = _get("STEAM_API_KEY", "")

    # RDS MySQL (Primary)
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_NAME = os.environ.get("DB_NAME", "gamefinder")
    DB_USER = os.environ.get("DB_USER", "admin")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    # ElastiCache Redis
    REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_TTL = int(os.environ.get("REDIS_TTL", 3600))  # 1시간

    # Snowflake
    SNOWFLAKE_ACCOUNT = _get("SNOWFLAKE_ACCOUNT", "")
    SNOWFLAKE_USER = _get("SNOWFLAKE_USER", "")
    SNOWFLAKE_PASSWORD = _get("SNOWFLAKE_PASSWORD", "")
    SNOWFLAKE_DATABASE = _get("SNOWFLAKE_DATABASE", "GAMEFINDER")
    SNOWFLAKE_SCHEMA = _get("SNOWFLAKE_SCHEMA", "GOLD")
    SNOWFLAKE_WAREHOUSE = _get("SNOWFLAKE_WAREHOUSE", "GAMEFINDER_WH")
    SNOWFLAKE_ROLE = _get("SNOWFLAKE_ROLE", "SYSADMIN")

    # Airflow REST API
    AIRFLOW_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://3.34.197.82:8080")
    AIRFLOW_USERNAME = os.environ.get("AIRFLOW_USERNAME", "admin")
    AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_PASSWORD", "admin")
    AIRFLOW_DAG_ID = os.environ.get("AIRFLOW_DAG_ID", "game_pipeline")


config = Config()
