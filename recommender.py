# recommender.py - 게임 추천 알고리즘
#
# 구현된 알고리즘:
#   1. 장르 기반 콘텐츠 필터링  : 유저가 많이 플레이한 장르와 겹치는 미소유 게임 추천
#   2. 아이템 기반 협업 필터링  : 유사 유저의 플레이 패턴을 분석해 추천
#   3. 숨겨진 명작 추천         : 플레이타임은 적지만 장르가 맞는 고평점 게임 추천

from collections import defaultdict
from dummy_data import GAME_CATALOG, DUMMY_OWNED_GAMES


class GameRecommender:

    # ─────────────────────────────────────────
    # 통계 계산 (대시보드용)
    # ─────────────────────────────────────────
    def compute_stats(self, owned_games: list[dict]) -> dict:
        """
        프론트엔드 dashboard.html 차트에 필요한 통계 딕셔너리 반환

        반환 구조:
        {
            "total_playtime_hours": float,
            "total_games": int,
            "user_summary": { ... },
            "genre_distribution": { "장르명": 플레이타임(분), ... },
            "top5_games": [ { name, playtime_hours }, ... ]
        }
        """
        if not owned_games:
            return {}

        total_minutes = sum(g.get("playtime_minutes", 0) for g in owned_games)

        # 장르별 플레이타임 집계
        genre_minutes: dict[str, int] = defaultdict(int)
        for game in owned_games:
            minutes = game.get("playtime_minutes", 0)
            for genre in game.get("genres", []):
                genre_minutes[genre] += minutes

        # Top 5 게임 (플레이타임 기준 내림차순)
        sorted_games = sorted(owned_games, key=lambda g: g.get("playtime_minutes", 0), reverse=True)
        top5 = [
            {
                "app_id": g.get("app_id"),
                "name": g.get("name", "Unknown"),
                "playtime_hours": round(g.get("playtime_minutes", 0) / 60, 1),
                "header_image": g.get(
                    "header_image",
                    f"https://cdn.akamai.steamstatic.com/steam/apps/{g.get('app_id')}/header.jpg",
                ),
            }
            for g in sorted_games[:5]
        ]

        # 장르 분포를 퍼센트로 변환 (차트용)
        total_genre_minutes = sum(genre_minutes.values()) or 1
        genre_distribution = {
            genre: {
                "minutes": minutes,
                "percentage": round(minutes / total_genre_minutes * 100, 1),
            }
            for genre, minutes in sorted(genre_minutes.items(), key=lambda x: x[1], reverse=True)
        }

        return {
            "total_playtime_hours": round(total_minutes / 60, 1),
            "total_games": len(owned_games),
            "genre_distribution": genre_distribution,
            "top5_games": top5,
        }

    # ─────────────────────────────────────────
    # 메인 추천 엔진
    # ─────────────────────────────────────────
    def get_recommendations(self, steam_id: str, owned_games: list[dict]) -> dict:
        """
        추천 결과 페이지의 세 카테고리 데이터 반환

        반환 구조:
        {
            "genre_based":  [ 게임카드, ... ],
            "collab_based": [ 게임카드, ... ],
            "hidden_gems":  [ 게임카드, ... ],
        }
        """
        owned_ids = {g["app_id"] for g in owned_games}

        genre_recs  = self._genre_based(owned_games, owned_ids)
        collab_recs = self._collab_based(steam_id, owned_ids)
        hidden_recs = self._hidden_gems(owned_games, owned_ids)

        return {
            "genre_based":  genre_recs,
            "collab_based": collab_recs,
            "hidden_gems":  hidden_recs,
        }

    # ─────────────────────────────────────────
    # 알고리즘 1: 장르 기반 콘텐츠 필터링
    # ─────────────────────────────────────────
    def _genre_based(self, owned_games: list[dict], owned_ids: set) -> list[dict]:
        """
        로직:
          1. 유저 플레이타임을 가중치로 장르 선호도 벡터 계산
          2. 카탈로그의 미소유 게임과 장르 교집합 크기로 점수 산정
          3. 점수 높은 순으로 최대 10개 반환
        """
        # 유저 장르 선호도 가중치 (플레이타임 비례)
        genre_weight: dict[str, float] = defaultdict(float)
        total_minutes = sum(g.get("playtime_minutes", 0) for g in owned_games) or 1

        for game in owned_games:
            weight = game.get("playtime_minutes", 0) / total_minutes
            for genre in game.get("genres", []):
                genre_weight[genre] += weight

        # 미소유 게임 점수 계산
        candidates = []
        for app_id, info in GAME_CATALOG.items():
            if app_id in owned_ids:
                continue
            score = sum(genre_weight.get(g, 0) for g in info.get("genres", []))
            if score > 0:
                match_pct = self._to_match_percent(score, max_score=1.5)
                candidates.append({
                    "app_id": app_id,
                    "name": info["name"],
                    "genres": info["genres"],
                    "header_image": info["header_image"],
                    "store_url": info["store_url"],
                    "match_percent": match_pct,
                    "score": score,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return self._clean_cards(candidates[:10])

    # ─────────────────────────────────────────
    # 알고리즘 2: 아이템 기반 협업 필터링
    # ─────────────────────────────────────────
    def _collab_based(self, steam_id: str, owned_ids: set) -> list[dict]:
        """
        로직:
          1. 모든 더미 유저와 현재 유저 간의 Jaccard 유사도 계산
          2. 가장 유사한 유저들의 게임 목록에서 내가 미소유한 게임 추출
          3. 유사도 합산이 높은 게임 순으로 반환
        
        ★ 실제 서비스 확장 시: 더미 데이터 대신 DB에 저장된 유저 데이터를 사용
        """
        # 유사 유저 계산 (자기 자신 제외)
        similarities = []
        for other_id, other_games in DUMMY_OWNED_GAMES.items():
            if other_id == steam_id:
                continue
            other_ids = {g["app_id"] for g in other_games}
            jaccard = self._jaccard_similarity(owned_ids, other_ids)
            if jaccard > 0:
                similarities.append((other_id, jaccard, other_games))

        similarities.sort(key=lambda x: x[1], reverse=True)

        # 추천 점수 집계 (유사도 가중치 합산)
        rec_scores: dict[int, float] = defaultdict(float)
        for _, sim, other_games in similarities[:5]:  # 상위 5명만 사용
            for game in other_games:
                if game["app_id"] not in owned_ids:
                    rec_scores[game["app_id"]] += sim

        # 점수 → 카드 변환
        candidates = []
        for app_id, score in rec_scores.items():
            info = GAME_CATALOG.get(app_id)
            if not info:
                continue
            match_pct = self._to_match_percent(score, max_score=2.0)
            candidates.append({
                "app_id": app_id,
                "name": info["name"],
                "genres": info["genres"],
                "header_image": info["header_image"],
                "store_url": info["store_url"],
                "match_percent": match_pct,
                "score": score,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return self._clean_cards(candidates[:10])

    # ─────────────────────────────────────────
    # 알고리즘 3: 숨겨진 명작 추천
    # ─────────────────────────────────────────
    def _hidden_gems(self, owned_games: list[dict], owned_ids: set) -> list[dict]:
        """
        로직:
          - 유저의 선호 장르와 겹치는 미소유 게임 중
          - metacritic 점수가 높으면서 (87점 이상)
          - 가격이 낮거나 무료인 게임을 우선 추천
        """
        # 유저 선호 장르 추출 (상위 3개)
        genre_count: dict[str, int] = defaultdict(int)
        for game in owned_games:
            for genre in game.get("genres", []):
                genre_count[genre] += 1
        top_genres = set(sorted(genre_count, key=genre_count.get, reverse=True)[:3])

        candidates = []
        for app_id, info in GAME_CATALOG.items():
            if app_id in owned_ids:
                continue
            game_genres = set(info.get("genres", []))
            genre_overlap = len(top_genres & game_genres)
            metacritic = info.get("metacritic", 0)
            if genre_overlap == 0 or metacritic < 87:
                continue
            # 점수: 장르 겹침 * 메타크리틱 보정 + 가격 보너스
            price_bonus = 0.3 if info.get("price", 99999) == 0 else 0
            score = genre_overlap * (metacritic / 100) + price_bonus
            match_pct = self._to_match_percent(score, max_score=3.0)
            candidates.append({
                "app_id": app_id,
                "name": info["name"],
                "genres": info["genres"],
                "header_image": info["header_image"],
                "store_url": info["store_url"],
                "match_percent": match_pct,
                "metacritic": metacritic,
                "price": info.get("price", 0),
                "score": score,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return self._clean_cards(candidates[:10])

    # ─────────────────────────────────────────
    # 유틸리티
    # ─────────────────────────────────────────
    @staticmethod
    def _jaccard_similarity(set_a: set, set_b: set) -> float:
        """두 게임 세트의 Jaccard 유사도 (교집합 / 합집합)"""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union

    @staticmethod
    def _to_match_percent(score: float, max_score: float = 1.0) -> int:
        """
        알고리즘 점수 → 프론트엔드 표시용 일치율(%) 변환
        최소 60%, 최대 99%로 클램핑
        """
        ratio = min(score / max_score, 1.0)
        return int(60 + ratio * 39)  # 60 ~ 99 범위

    @staticmethod
    def _clean_cards(cards: list[dict]) -> list[dict]:
        """내부 score 필드 제거 후 반환 (프론트에 불필요한 정보 숨김)"""
        for c in cards:
            c.pop("score", None)
        return cards
