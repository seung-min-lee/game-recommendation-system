from flask import Flask, jsonify, request
from flask_cors import CORS
from services.steam_service import SteamService
from ml.recommender import GameRecommender
from services.cache_service import cache
from services.snowflake_service import snowflake_svc
from services.airflow_service import airflow_svc

app = Flask(__name__)
CORS(app)

import json as _json

def _fmt(g: dict) -> dict:
    genres = g.get("genres", [])
    if isinstance(genres, str):
        try:
            genres = _json.loads(genres)
        except Exception:
            genres = [genres]
    return {
        "app_id":       g.get("app_id"),
        "name":         g.get("game_name"),
        "header_image": g.get("header_image"),
        "store_url":    g.get("store_url"),
        "genres":       genres,
        "score":        float(g.get("score") or 0),
        "metacritic":   g.get("metacritic"),
        "match_percent": g.get("metacritic") or min(int(float(g.get("score") or 0)), 100),
    }

steam = SteamService()
recommender = GameRecommender()


# ─────────────────────────────────────────
# 헬스체크
# ─────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "message": "Game Finder API is running",
        "cache": cache.is_available(),
    })


# ─────────────────────────────────────────
# 1. 유저 프로필
# ─────────────────────────────────────────
@app.route("/api/user/<steam_id>", methods=["GET"])
def get_user(steam_id):
    cache_key = f"user:{steam_id}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        user = steam.get_user_summary(steam_id)
        if not user:
            return jsonify({"error": "유저를 찾을 수 없습니다."}), 404
        cache.set(cache_key, user, ttl=600)
        return jsonify(user)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────
# 2. 대시보드 통계
# ─────────────────────────────────────────
@app.route("/api/stats/<steam_id>", methods=["GET"])
def get_stats(steam_id):
    cache_key = f"stats:{steam_id}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        owned_games = steam.get_owned_games(steam_id)
        if not owned_games:
            return jsonify({"error": "게임 데이터를 불러올 수 없습니다."}), 404
        stats = recommender.compute_stats(owned_games)
        cache.set(cache_key, stats, ttl=1800)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────
# 3. 추천 요청
#    순서: Redis 캐시 → Snowflake Gold Layer → Airflow DAG 트리거(로컬 폴백)
# ─────────────────────────────────────────
@app.route("/api/recommend/<steam_id>", methods=["GET"])
def get_recommendations(steam_id):
    cache_key = f"recommend:{steam_id}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({**cached, "source": "cache"})

    # Snowflake Gold Layer 조회
    try:
        if snowflake_svc.has_recommendations(steam_id):
            result = {
                "genre_based":  [_fmt(g) for g in snowflake_svc.get_cbf_recommendations(steam_id)],
                "collab_based": [_fmt(g) for g in snowflake_svc.get_cf_recommendations(steam_id)],
                "hidden_gems":  [_fmt(g) for g in snowflake_svc.get_genre_trend(steam_id)],
                "source": "snowflake",
            }
            cache.set(cache_key, result)
            return jsonify(result)
    except Exception:
        pass  # Snowflake 연결 안 되면 로컬 추천으로 폴백

    # Airflow DAG 트리거 (파이프라인 실행 요청)
    try:
        dag_run_id = airflow_svc.trigger_pipeline(steam_id)
        return jsonify({
            "status": "processing",
            "dag_run_id": dag_run_id,
            "message": "추천 파이프라인을 시작했습니다. /api/recommend/{steam_id}/status로 상태를 확인하세요.",
        }), 202
    except Exception:
        pass  # Airflow도 안 되면 로컬 추천으로 폴백

    # 로컬 추천 (더미 데이터 기반, 개발/테스트용)
    try:
        owned_games = steam.get_owned_games(steam_id)
        if not owned_games:
            return jsonify({"error": "게임 데이터를 불러올 수 없습니다."}), 404
        result = {**recommender.get_recommendations(steam_id, owned_games), "source": "local"}
        cache.set(cache_key, result, ttl=600)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────
# 4. DAG 실행 상태 폴링
# ─────────────────────────────────────────
@app.route("/api/recommend/<steam_id>/status", methods=["GET"])
def get_recommend_status(steam_id):
    dag_run_id = request.args.get("dag_run_id")
    if not dag_run_id:
        return jsonify({"error": "dag_run_id 파라미터가 필요합니다."}), 400

    try:
        state = airflow_svc.get_run_status(dag_run_id)
        response = {"state": state}

        # 파이프라인 완료 시 Snowflake에서 결과 조회
        if state == "success":
            cache_key = f"recommend:{steam_id}"
            result = {
                "genre_based":  [_fmt(g) for g in snowflake_svc.get_cbf_recommendations(steam_id)],
                "collab_based": [_fmt(g) for g in snowflake_svc.get_cf_recommendations(steam_id)],
                "hidden_gems":  [_fmt(g) for g in snowflake_svc.get_genre_trend(steam_id)],
                "source": "snowflake",
            }
            cache.set(cache_key, result)
            response["result"] = result

        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────
# 5. 게임 상세 정보
# ─────────────────────────────────────────
@app.route("/api/game/<int:app_id>", methods=["GET"])
def get_game_detail(app_id):
    cache_key = f"game:{app_id}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        game = steam.get_game_detail(app_id)
        if not game:
            return jsonify({"error": "게임 정보를 찾을 수 없습니다."}), 404
        cache.set(cache_key, game, ttl=86400)  # 게임 정보는 24시간 캐싱
        return jsonify(game)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────
# 에러 핸들러
# ─────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "요청한 리소스를 찾을 수 없습니다."}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "서버 내부 오류가 발생했습니다."}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
