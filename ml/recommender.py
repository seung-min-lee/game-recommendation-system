from __future__ import annotations
from collections import defaultdict
from data.dummy_data import GAME_CATALOG, DUMMY_OWNED_GAMES
from ml.lightgcn import LightGCN


class GameRecommender:

    def compute_stats(self, owned_games: list[dict]) -> dict:
        if not owned_games:
            return {}

        total_minutes = sum(g.get("playtime_minutes", 0) for g in owned_games)

        genre_minutes: dict[str, int] = defaultdict(int)
        for game in owned_games:
            minutes = game.get("playtime_minutes", 0)
            for genre in game.get("genres", []):
                genre_minutes[genre] += minutes

        sorted_games = sorted(owned_games, key=lambda g: g.get("playtime_minutes", 0), reverse=True)
        top5 = [
            {
                "app_id": g.get("app_id"),
                "name": g.get("name", "Unknown"),
                "playtime_hours": round(g.get("playtime_minutes", 0) / 60, 1),
                "genres": g.get("genres", []),
                "header_image": g.get(
                    "header_image",
                    f"https://cdn.akamai.steamstatic.com/steam/apps/{g.get('app_id')}/header.jpg",
                ),
            }
            for g in sorted_games[:5]
        ]

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

    def get_recommendations(
        self,
        steam_id: str,
        owned_games: list[dict],
        real_users: dict[str, list[dict]] | None = None,
    ) -> dict:
        """
        real_users: {friend_steam_id: [{"app_id", "playtime_minutes", "name"}]}
                    SteamService.get_friends_games() 반환값. 없으면 더미 유저 사용.
        """
        owned_ids = {g["app_id"] for g in owned_games}
        genre_recs  = self._genre_based(owned_games, owned_ids)
        collab_recs = self._collab_based(steam_id, owned_ids, real_users)
        hidden_recs = self._hidden_gems(owned_games, owned_ids)
        graph_recs  = self._lightgcn(steam_id, owned_games, owned_ids, real_users)

        return {
            "genre_based":  genre_recs,
            "collab_based": collab_recs,
            "hidden_gems":  hidden_recs,
            "graph_based":  graph_recs,
        }

    # ── 알고리즘 1: 장르 기반 콘텐츠 필터링 ─────────────────────────────────
    def _genre_based(self, owned_games: list[dict], owned_ids: set) -> list[dict]:
        genre_weight: dict[str, float] = defaultdict(float)
        total_minutes = sum(g.get("playtime_minutes", 0) for g in owned_games) or 1

        for game in owned_games:
            weight = game.get("playtime_minutes", 0) / total_minutes
            for genre in game.get("genres", []):
                genre_weight[genre] += weight

        # 이론적 최대 점수 = 모든 장르 가중치 합 (게임 한 개가 모든 장르를 커버할 때)
        max_possible = sum(genre_weight.values()) or 1.0

        top_genre = max(genre_weight, key=genre_weight.get) if genre_weight else ""
        candidates = []
        for app_id, info in GAME_CATALOG.items():
            if app_id in owned_ids:
                continue
            matched = [g for g in info.get("genres", []) if genre_weight.get(g, 0) > 0]
            score = sum(genre_weight.get(g, 0) for g in info.get("genres", []))
            if score > 0:
                # 실제 장르 가중치 비율 → 진짜 일치도
                match_pct = min(95, max(58, int(58 + (score / max_possible) * 37)))
                genre_str = " · ".join(matched[:2]) if matched else top_genre
                candidates.append({
                    "app_id": app_id,
                    "name": info["name"],
                    "genres": info["genres"],
                    "header_image": info["header_image"],
                    "store_url": info["store_url"],
                    "match_percent": match_pct,
                    "reason": f"당신의 {genre_str} 플레이 패턴과 일치",
                    "score": score,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return self._clean_cards(candidates[:20])

    # ── 알고리즘 2: 유사 유저 기반 협업 필터링 ──────────────────────────────
    def _collab_based(
        self,
        steam_id: str,
        owned_ids: set,
        real_users: dict[str, list[dict]] | None = None,
    ) -> list[dict]:
        """
        real_users가 있으면 실제 스팀 친구 데이터 사용.
        없거나 비어있으면 더미 유저로 폴백.
        추천 후보는 GAME_CATALOG 범위 내에서 결정하고,
        카탈로그에 없는 게임은 Steam Store API로 메타데이터 보완.
        """
        # ── 유저 풀 결정 ─────────────────────────────────────────────────────
        using_real = bool(real_users)
        user_pool: dict[str, list[dict]] = real_users if using_real else {}

        # 더미 유저는 항상 보조로 포함 (실제 친구가 부족할 때 채우기)
        for uid, games in DUMMY_OWNED_GAMES.items():
            if uid != steam_id and uid not in user_pool:
                user_pool[uid] = games

        # ── 현재 유저 장르 프로필 (폴백 유사도용) ────────────────────────────
        user_genre_set: set[str] = set()
        for app_id in owned_ids:
            user_genre_set.update(GAME_CATALOG.get(app_id, {}).get("genres", []))

        # ── Jaccard 유사도 계산 ───────────────────────────────────────────────
        similarities: list[tuple[str, float, list[dict]]] = []
        for other_id, other_games in user_pool.items():
            other_ids = {g["app_id"] for g in other_games}
            jaccard = self._jaccard_similarity(owned_ids, other_ids)
            if jaccard > 0:
                similarities.append((other_id, jaccard, other_games))

        # 겹치는 게임이 없으면 장르 유사도로 폴백
        if not similarities:
            for other_id, other_games in user_pool.items():
                other_genre_set: set[str] = set()
                for g in other_games:
                    other_genre_set.update(GAME_CATALOG.get(g["app_id"], {}).get("genres", []))
                genre_sim = self._jaccard_similarity(user_genre_set, other_genre_set)
                if genre_sim > 0:
                    similarities.append((other_id, genre_sim * 0.6, other_games))

        similarities.sort(key=lambda x: x[1], reverse=True)
        top_sims = similarities[:10]  # 상위 10명 사용

        # ── 추천 점수 집계 ────────────────────────────────────────────────────
        rec_scores: dict[int, float] = defaultdict(float)
        game_user_count: dict[int, int] = defaultdict(int)
        for _, sim, other_games in top_sims:
            for game in other_games:
                aid = game["app_id"]
                if aid not in owned_ids:
                    rec_scores[aid] += sim
                    game_user_count[aid] += 1

        is_fallback = not any(
            len({g["app_id"] for g in og} & owned_ids) > 0
            for _, _, og in top_sims
        )

        # 유사 유저 전체 유사도 합 = 이 게임을 모든 유사 유저가 가졌을 때의 최대 점수
        max_collab_score = sum(sim for _, sim, _ in top_sims) or 1.0

        # ── 카드 변환: GAME_CATALOG 우선, 없으면 Steam API ───────────────────
        candidates = []
        for app_id, score in sorted(rec_scores.items(), key=lambda x: x[1], reverse=True)[:20]:
            info = GAME_CATALOG.get(app_id) or self._fetch_game_info(app_id)
            if not info:
                continue
            # 유사 유저 중 몇 %가 이 게임을 가지고 있는가 (가중치 반영)
            match_pct = min(95, max(58, int(58 + (score / max_collab_score) * 37)))
            n = game_user_count.get(app_id, 1)
            if using_real and not is_fallback:
                reason = f"스팀 친구 {n}명이 즐겨한 게임"
            elif using_real:
                reason = f"스팀 친구 {n}명 취향 기반 추천 (장르 유사도)"
            elif is_fallback:
                reason = f"취향이 비슷한 유저 {n}명이 즐겨한 게임 (장르 유사도 기반)"
            else:
                reason = f"취향이 비슷한 유저 {n}명이 즐겨한 게임"
            candidates.append({
                "app_id": app_id,
                "name": info["name"],
                "genres": info.get("genres", []),
                "header_image": info.get("header_image", f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"),
                "store_url": info.get("store_url", f"https://store.steampowered.com/app/{app_id}"),
                "match_percent": match_pct,
                "reason": reason,
                "score": score,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return self._clean_cards(candidates[:15])

    # ── 알고리즘 3: 숨겨진 명작 ──────────────────────────────────────────────
    def _hidden_gems(self, owned_games: list[dict], owned_ids: set) -> list[dict]:
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
            price_bonus = 0.3 if info.get("price", 99999) == 0 else 0
            score = genre_overlap * (metacritic / 100) + price_bonus
            # 장르 일치율 (내 상위 3장르 중 몇 개 겹치는가) 60% + 품질 점수 40%
            # metacritic 87~100 구간을 0~100%로 정규화
            genre_pct  = genre_overlap / len(top_genres) * 100
            quality_pct = max(0.0, (metacritic - 87) / 13 * 100)
            raw = (genre_pct * 0.6 + quality_pct * 0.4) / 100  # 0.0 ~ 1.0
            match_pct  = min(95, max(58, int(58 + raw * 37)))
            common = sorted(top_genres & game_genres)
            genre_str = " · ".join(common[:2]) if common else ""
            price_str = "무료" if info.get("price", 0) == 0 else f"₩{info['price']:,}"
            reason = f"MC {metacritic}점 고평점 · {genre_str} · {price_str}"
            candidates.append({
                "app_id": app_id,
                "name": info["name"],
                "genres": info["genres"],
                "header_image": info["header_image"],
                "store_url": info["store_url"],
                "match_percent": match_pct,
                "metacritic": metacritic,
                "price": info.get("price", 0),
                "reason": reason,
                "score": score,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return self._clean_cards(candidates[:10])

    # ── 알고리즘 4: LightGCN ─────────────────────────────────────────────────
    def _lightgcn(
        self,
        steam_id: str,
        owned_games: list[dict],
        owned_ids: set,
        real_users: dict[str, list[dict]] | None = None,
    ) -> list[dict]:
        interactions = []
        # 실제 친구 데이터가 있으면 학습에 포함
        extra_users = real_users or {}
        for uid, games in {**DUMMY_OWNED_GAMES, **extra_users}.items():
            for g in games:
                interactions.append((uid, g["app_id"], g.get("playtime_minutes", 1)))
        for g in owned_games:
            interactions.append((steam_id, g["app_id"], g.get("playtime_minutes", 1)))

        try:
            model = LightGCN(n_layers=3, emb_dim=64, lr=0.01, n_epochs=300)
            model.fit(interactions)
            if steam_id in model.user_index:
                scored = model.recommend(steam_id, owned_ids, top_k=12)
            else:
                scored = model.recommend_new_user(owned_games, owned_ids, top_k=12)
        except Exception:
            return []

        if not scored:
            return []
        max_score = scored[0][1] if scored[0][1] > 0 else 1.0
        min_score = scored[-1][1]
        score_range = max_score - min_score or 1.0

        candidates = []
        for app_id, score in scored:
            info = GAME_CATALOG.get(app_id) or self._fetch_game_info(app_id)
            if not info:
                continue
            # GNN 임베딩 내적값: 결과 내 상대 순위 반영
            # 1위 → 최대 95%, 꼴찌 → max_score 대비 절대값 기반 하한
            relative_pct = (score - min_score) / score_range  # 0.0 ~ 1.0
            absolute_pct = min(1.0, max(0.0, score / (max_score or 1.0)))  # 절대 강도
            combined = relative_pct * 0.5 + absolute_pct * 0.5
            match_pct  = min(95, max(58, int(58 + combined * 37)))
            genre_str = " · ".join(info.get("genres", [])[:2])
            n_users = len(extra_users) + len(DUMMY_OWNED_GAMES)
            reason = f"GNN이 {n_users}명 플레이 그래프에서 분석 · {genre_str}"
            candidates.append({
                "app_id": app_id,
                "name": info["name"],
                "genres": info.get("genres", []),
                "header_image": info.get("header_image", f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"),
                "store_url": info.get("store_url", f"https://store.steampowered.com/app/{app_id}"),
                "match_percent": match_pct,
                "metacritic": info.get("metacritic"),
                "reason": reason,
            })
        return candidates

    # ── 유틸리티 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _fetch_game_info(app_id: int) -> dict | None:
        """GAME_CATALOG에 없는 게임의 메타데이터를 Steam Store API에서 가져옴."""
        try:
            import requests as _req
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&filters=basic,genres"
            res = _req.get(url, timeout=4)
            data = res.json().get(str(app_id), {})
            if data.get("success"):
                d = data["data"]
                return {
                    "name": d.get("name", f"Game_{app_id}"),
                    "genres": [g["description"] for g in d.get("genres", [])],
                    "header_image": d.get("header_image") or f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    "store_url": f"https://store.steampowered.com/app/{app_id}",
                    "metacritic": 0,
                    "price": 0,
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _jaccard_similarity(set_a: set, set_b: set) -> float:
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    @staticmethod
    def _clean_cards(cards: list[dict]) -> list[dict]:
        for c in cards:
            c.pop("score", None)
        return cards
