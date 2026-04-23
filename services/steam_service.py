from __future__ import annotations
import os
import requests
import concurrent.futures
from data.dummy_data import GAME_CATALOG, DUMMY_OWNED_GAMES

def _get_api_key() -> str:
    key = os.environ.get("STEAM_API_KEY", "")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("STEAM_API_KEY", "")
    except Exception:
        return ""


class SteamService:

    def get_user_summary(self, steam_id: str) -> dict | None:
        """실제 Steam API로만 조회. 존재하지 않는 ID면 None 반환."""
        key = _get_api_key()
        if not key:
            return None
        try:
            url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            res = requests.get(url, params={"key": key, "steamids": steam_id}, timeout=5)
            players = res.json().get("response", {}).get("players", [])
            if not players:
                return None
            p = players[0]
            return {
                "steam_id": steam_id,
                "username": p.get("personaname", f"User_{steam_id[-6:]}"),
                "avatar_url": p.get("avatarfull", ""),
            }
        except Exception:
            return None

    def get_owned_games(self, steam_id: str) -> list[dict]:
        """실제 Steam API로만 조회. API 키 없거나 유저 미존재 시 빈 리스트 반환."""
        key = _get_api_key()
        if not key:
            return []
        try:
            url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            res = requests.get(url, params={
                "key": key,
                "steamid": steam_id,
                "include_appinfo": True,
                "include_played_free_games": True,
            }, timeout=5)
            games = res.json().get("response", {}).get("games", [])
            if not games:
                return []
            result = []
            for g in games:
                app_id = g.get("appid")
                catalog = GAME_CATALOG.get(app_id, {})
                result.append({
                    "app_id": app_id,
                    "name": g.get("name", catalog.get("name", f"Game_{app_id}")),
                    "playtime_minutes": g.get("playtime_forever", 0),
                    "genres": catalog.get("genres", []),
                    "header_image": catalog.get(
                        "header_image",
                        f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    ),
                    "store_url": catalog.get("store_url", f"https://store.steampowered.com/app/{app_id}"),
                })
            return result
        except Exception:
            return []

    def get_friend_list(self, steam_id: str) -> list[str]:
        """공개 친구 목록 반환. 비공개면 빈 리스트."""
        key = _get_api_key()
        if not key:
            return []
        try:
            url = "https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
            res = requests.get(url, params={"key": key, "steamid": steam_id, "relationship": "friend"}, timeout=5)
            if res.status_code != 200:
                return []
            friends = res.json().get("friendslist", {}).get("friends", [])
            return [f["steamid"] for f in friends]
        except Exception:
            return []

    def get_friends_games(self, steam_id: str, max_friends: int = 20) -> dict[str, list[dict]]:
        """
        친구들의 소유 게임 목록을 병렬로 가져옴.
        반환: {friend_steam_id: [{"app_id", "playtime_minutes", "name"}]}
        친구 목록 비공개이거나 API 키 없으면 빈 dict.
        """
        friend_ids = self.get_friend_list(steam_id)
        if not friend_ids:
            return {}

        # 플레이타임이 있는 친구 우선 (소팅은 불가하므로 무작위 max_friends)
        friend_ids = friend_ids[:max_friends]
        key = _get_api_key()

        def _fetch_one(fid: str) -> tuple[str, list[dict]]:
            try:
                url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
                res = requests.get(url, params={
                    "key": key,
                    "steamid": fid,
                    "include_appinfo": True,
                    "include_played_free_games": True,
                }, timeout=4)
                games = res.json().get("response", {}).get("games", [])
                parsed = [
                    {
                        "app_id": g["appid"],
                        "playtime_minutes": g.get("playtime_forever", 0),
                        "name": g.get("name", f"Game_{g['appid']}"),
                    }
                    for g in games
                    if g.get("playtime_forever", 0) > 0  # 플레이한 게임만
                ]
                return fid, parsed
            except Exception:
                return fid, []

        result: dict[str, list[dict]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_fetch_one, fid): fid for fid in friend_ids}
            done, _ = concurrent.futures.wait(futures, timeout=12)
            for fut in done:
                fid, games = fut.result()
                if games:
                    result[fid] = games
        return result

    def get_friends_profiles(self, friend_ids: list[str]) -> dict[str, dict]:
        """최대 100명까지 한 번에 프로필 배치 fetch."""
        if not friend_ids or not _get_api_key():
            return {}
        result: dict[str, dict] = {}
        for i in range(0, len(friend_ids), 100):
            chunk = friend_ids[i:i + 100]
            try:
                url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
                res = requests.get(url, params={"key": _get_api_key(), "steamids": ",".join(chunk)}, timeout=5)
                for p in res.json().get("response", {}).get("players", []):
                    result[p["steamid"]] = {
                        "username": p.get("personaname", f"User_{p['steamid'][-4:]}"),
                        "avatar_url": p.get("avatarfull", ""),
                    }
            except Exception:
                pass
        return result

    def get_reviews(self, app_id: int, num: int = 160) -> dict:
        """
        Steam Store 리뷰 API + 한국어 번역.
        helpful 100개 + recent 100개를 합쳐 중복 제거 후 최대 num개 반환.
        """
        def _fetch(filter_type: str, language: str = "all", purchase_type: str = "steam") -> dict:
            try:
                res = requests.get(
                    f"https://store.steampowered.com/appreviews/{app_id}",
                    params={
                        "json": 1,
                        "num_per_page": 100,
                        "language": language,
                        "review_type": "all",
                        "purchase_type": purchase_type,
                        "filter": filter_type,
                    },
                    timeout=10,
                )
                return res.json()
            except Exception:
                return {}

        # helpful 100개 + recent 100개 병렬 수집
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(_fetch, "helpful", "all", "steam")
            f2 = ex.submit(_fetch, "recent",  "all", "steam")
            data1 = f1.result()
            data2 = f2.result()

        summary = data1.get("query_summary") or data2.get("query_summary") or {}

        # 중복 제거 (recommendationid 기준)
        seen: set = set()
        raw_list: list = []
        for data in [data1, data2]:
            for r in data.get("reviews", []):
                rid = r.get("recommendationid")
                if rid and rid not in seen:
                    seen.add(rid)
                    raw_list.append(r)

        # 리뷰가 없으면 english/all로 재시도
        if not raw_list:
            data_fb = _fetch("helpful", "english", "all")
            summary = data_fb.get("query_summary", {})
            raw_list = data_fb.get("reviews", [])

        raw_list = raw_list[:num]

        if not raw_list:
            return {"summary": {}, "reviews": []}

        total    = summary.get("total_reviews", 0)
        positive = summary.get("total_positive", 0)
        pct      = round(positive / total * 100) if total > 0 else 0

        raw_reviews = []
        for r in raw_list:
            text = r.get("review", "").strip().replace("\n", " ")
            if not text:
                continue
            if len(text) > 2000:
                text = text[:2000] + "..."
            raw_reviews.append({
                "text": text,
                "voted_up": r.get("voted_up", True),
                "playtime_hours": round(r.get("author", {}).get("playtime_forever", 0) / 60, 1),
                "language": r.get("language", ""),
            })

        reviews = self._translate_reviews(raw_reviews)
        return {
            "summary": {
                "total": total,
                "positive_pct": pct,
                "score_desc": summary.get("review_score_desc", ""),
            },
            "reviews": reviews,
        }

    @staticmethod
    def _is_korean(text: str) -> bool:
        """한국어 판단 — 중국어/일본어가 조금이라도 있으면 무조건 번역 대상."""
        korean  = sum(1 for c in text if '가' <= c <= '힣')
        chinese = sum(1 for c in text if '一' <= c <= '鿿')
        japanese = sum(1 for c in text if '぀' <= c <= 'ヿ')
        letters = sum(1 for c in text if c.isalpha())
        if letters == 0:
            return True
        # 중국어 또는 일본어가 전체의 5% 이상이면 번역 필요
        if (chinese + japanese) / letters >= 0.05:
            return False
        return korean / letters >= 0.5

    def _translate_reviews(self, reviews: list[dict]) -> list[dict]:
        """한국어가 아닌 리뷰를 순차 번역 (rate-limit 대응)."""
        from deep_translator import GoogleTranslator

        translated = list(reviews)
        needs = [
            (i, r) for i, r in enumerate(reviews)
            if r.get("text") and not self._is_korean(r["text"])
        ]
        if not needs:
            return reviews

        def _do(item):
            idx, r = item
            for attempt in range(3):
                try:
                    import time
                    if attempt:
                        time.sleep(attempt * 0.5)
                    t = GoogleTranslator(source="auto", target="ko").translate(r["text"])
                    return idx, (t or r["text"])
                except Exception:
                    continue
            return idx, r["text"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(_do, item) for item in needs]
            done, _ = concurrent.futures.wait(futures, timeout=60)
            for fut in done:
                try:
                    idx, text = fut.result()
                    translated[idx] = {**translated[idx], "text": text}
                except Exception:
                    pass

        return translated

    def get_game_detail(self, app_id: int) -> dict | None:
        info = GAME_CATALOG.get(app_id)
        if info:
            return {"app_id": app_id, **info}
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&filters=basic,genres"
            res = requests.get(url, timeout=4)
            data = res.json().get(str(app_id), {})
            if data.get("success"):
                d = data["data"]
                return {
                    "app_id": app_id,
                    "name": d.get("name"),
                    "genres": [g["description"] for g in d.get("genres", [])],
                    "header_image": d.get("header_image") or f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    "store_url": f"https://store.steampowered.com/app/{app_id}",
                    "metacritic": 0,
                    "price": 0,
                }
        except Exception:
            pass
        return None

    def get_game_details_batch(self, app_ids: list[int]) -> dict[int, dict]:
        """여러 게임의 메타데이터를 병렬로 가져옴 (GAME_CATALOG 미등록 게임용)."""
        result: dict[int, dict] = {}

        def _fetch(app_id: int) -> tuple[int, dict | None]:
            return app_id, self.get_game_detail(app_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(_fetch, aid): aid for aid in app_ids}
            done, _ = concurrent.futures.wait(futures, timeout=15)
            for fut in done:
                aid, info = fut.result()
                if info:
                    result[aid] = info
        return result

    def get_price_info_batch(self, app_ids: list[int], cc: str = "kr") -> dict[int, dict]:
        """
        Steam Store API로 현재 가격/할인 정보를 병렬 조회.
        반환 형식 per app_id:
          {"is_free": bool, "discount_percent": int,
           "original": str, "final": str, "final_int": int}
        조회 실패 시 해당 app_id 키 없음.
        """
        def _fetch_price(app_id: int) -> tuple[int, dict | None]:
            try:
                url = (
                    f"https://store.steampowered.com/api/appdetails"
                    f"?appids={app_id}&cc={cc}&filters=price_overview"
                )
                res = requests.get(url, timeout=5)
                data = res.json().get(str(app_id), {})
                if not data.get("success"):
                    return app_id, None
                po = data.get("data", {}).get("price_overview")
                if po is None:
                    # price_overview 없으면 무료 게임
                    return app_id, {"is_free": True, "discount_percent": 0,
                                    "original": "무료", "final": "무료", "final_int": 0}
                return app_id, {
                    "is_free": False,
                    "discount_percent": po.get("discount_percent", 0),
                    "original": po.get("initial_formatted", ""),
                    "final":    po.get("final_formatted", ""),
                    "final_int": po.get("final", 0),
                }
            except Exception:
                return app_id, None

        result: dict[int, dict] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_fetch_price, aid): aid for aid in app_ids}
            done, _ = concurrent.futures.wait(futures, timeout=12)
            for fut in done:
                try:
                    aid, info = fut.result()
                    if info is not None:
                        result[aid] = info
                except Exception:
                    pass
        return result
