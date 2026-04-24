from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

import os
import requests
import snowflake.connector

# ──────────────────────────────────────────────
# 공통 설정
# ──────────────────────────────────────────────
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")
SNOWFLAKE_CONN = {
    "account":   os.environ.get("SNOWFLAKE_ACCOUNT", ""),
    "user":      os.environ.get("SNOWFLAKE_USER", ""),
    "password":  os.environ.get("SNOWFLAKE_PASSWORD", ""),
    "database":  "GAMEFINDER",
    "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    "role":      os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
}

default_args = {
    "owner": "gamefinder",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# ──────────────────────────────────────────────
# DAG 정의
# ──────────────────────────────────────────────
with DAG(
    dag_id="game_pipeline",
    description="Steam 데이터 수집 → Snowflake Bronze/Silver/Gold 변환 파이프라인",
    default_args=default_args,
    schedule_interval="0 0 * * *",   # 매일 자정 실행
    start_date=days_ago(1),
    catchup=False,                    # 과거 미실행 DAG 백필 비활성화
    max_active_runs=1,
    tags=["gamefinder", "steam", "snowflake"],
    params={"steam_id": ""},          # Flask API에서 트리거 시 전달
) as dag:

    # ── Task 1: 게임 메타데이터 수집 → Bronze ─────────────────
    def ingest_game_metadata(**context):
        steam_id = context["params"].get("steam_id", "")
        conn = snowflake.connector.connect(**SNOWFLAKE_CONN, schema="BRONZE")
        cursor = conn.cursor()

        url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        res = requests.get(url, params={
            "key": STEAM_API_KEY,
            "steamid": steam_id,
            "include_appinfo": True,
            "include_played_free_games": True,
        }, timeout=10)
        games = res.json().get("response", {}).get("games", [])

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BRONZE.RAW_GAME_METADATA (
                app_id      NUMBER,
                name        STRING,
                genres      ARRAY,
                tags        ARRAY,
                metacritic  NUMBER,
                price       NUMBER,
                loaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
            )
        """)
        for g in games:
            app_id = g.get("appid")
            name   = g.get("name", f"Game_{app_id}")
            cursor.execute("""
                MERGE INTO BRONZE.RAW_GAME_METADATA t
                USING (SELECT %(app_id)s AS app_id) s ON t.app_id = s.app_id
                WHEN NOT MATCHED THEN INSERT (app_id, name, genres, tags, metacritic, price)
                VALUES (%(app_id)s, %(name)s, ARRAY_CONSTRUCT(), ARRAY_CONSTRUCT(), 0, 0)
            """, {"app_id": app_id, "name": name})

        cursor.close()
        conn.close()
        print(f"[ingest_game_metadata] {len(games)}개 게임 수집 완료")

    # ── Task 2: 유저 플레이 기록 수집 → Bronze ────────────────
    def ingest_user_games(**context):
        steam_id = context["params"].get("steam_id", "")
        conn = snowflake.connector.connect(**SNOWFLAKE_CONN, schema="BRONZE")
        cursor = conn.cursor()

        url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        res = requests.get(url, params={
            "key": STEAM_API_KEY,
            "steamid": steam_id,
            "include_appinfo": True,
            "include_played_free_games": True,
        }, timeout=10)
        games = res.json().get("response", {}).get("games", [])

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BRONZE.RAW_USER_GAMES (
                steam_id         STRING,
                app_id           NUMBER,
                game_name        STRING,
                playtime_minutes NUMBER,
                loaded_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
            )
        """)
        for g in games:
            cursor.execute("""
                INSERT INTO BRONZE.RAW_USER_GAMES (steam_id, app_id, game_name, playtime_minutes)
                VALUES (%(steam_id)s, %(app_id)s, %(name)s, %(playtime)s)
            """, {
                "steam_id": steam_id,
                "app_id":   g.get("appid"),
                "name":     g.get("name", ""),
                "playtime": g.get("playtime_forever", 0),
            })

        cursor.close()
        conn.close()
        print(f"[ingest_user_games] {steam_id} — {len(games)}개 기록 수집 완료")

    # ── Task 3: Bronze → Silver 정제 (dbt) ───────────────────
    def transform_silver(**context):
        import subprocess
        result = subprocess.run(
            ["dbt", "run", "--select", "silver", "--profiles-dir", "/opt/airflow/dbt"],
            capture_output=True, text=True, cwd="/opt/airflow/gamefinder_dbt"
        )
        if result.returncode != 0:
            raise RuntimeError(f"dbt silver 실패:\n{result.stderr}")
        print(f"[transform_silver] 완료\n{result.stdout}")

    # ── Task 4: Silver → Gold 추천 생성 (dbt) ────────────────
    def build_gold_recommendations(**context):
        import subprocess
        result = subprocess.run(
            ["dbt", "run", "--select", "gold", "--profiles-dir", "/opt/airflow/dbt"],
            capture_output=True, text=True, cwd="/opt/airflow/gamefinder_dbt"
        )
        if result.returncode != 0:
            raise RuntimeError(f"dbt gold 실패:\n{result.stderr}")
        print(f"[build_gold_recommendations] 완료\n{result.stdout}")

    # ── Task 인스턴스 ─────────────────────────────────────────
    t1 = PythonOperator(task_id="ingest_game_metadata",    python_callable=ingest_game_metadata)
    t2 = PythonOperator(task_id="ingest_user_games",       python_callable=ingest_user_games)
    t3 = PythonOperator(task_id="transform_silver",        python_callable=transform_silver)
    t4 = PythonOperator(task_id="build_gold_recommendations", python_callable=build_gold_recommendations)

    # ── 실행 순서 ─────────────────────────────────────────────
    [t1, t2] >> t3 >> t4
