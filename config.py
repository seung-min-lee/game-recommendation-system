import os


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # Steam
    STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")

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
    SNOWFLAKE_ACCOUNT = os.environ.get("SNOWFLAKE_ACCOUNT", "")
    SNOWFLAKE_USER = os.environ.get("SNOWFLAKE_USER", "")
    SNOWFLAKE_PASSWORD = os.environ.get("SNOWFLAKE_PASSWORD", "")
    SNOWFLAKE_DATABASE = os.environ.get("SNOWFLAKE_DATABASE", "GAMEFINDER")
    SNOWFLAKE_SCHEMA = os.environ.get("SNOWFLAKE_SCHEMA", "GOLD")
    SNOWFLAKE_WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "GAMEFINDER_WH")
    SNOWFLAKE_ROLE = os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN")

    # Airflow REST API (EKS 내부 서비스 주소)
    AIRFLOW_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://airflow-webserver.airflow.svc.cluster.local:8080")
    AIRFLOW_USERNAME = os.environ.get("AIRFLOW_USERNAME", "admin")
    AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_PASSWORD", "admin")
    AIRFLOW_DAG_ID = os.environ.get("AIRFLOW_DAG_ID", "game_pipeline")


config = Config()
