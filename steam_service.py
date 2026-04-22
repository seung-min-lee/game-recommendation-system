from __future__ import annotations
import os
import requests
import concurrent.futures
from dummy_data import GAME_CATALOG, DUMMY_OWNED_GAMES

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
        if _get_api_key():
            try:
                url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
                res = requests.get(url, params={"key": _get_api_key(), "steamids": steam_id}, timeout=5)
                players = res.json().get("response", {}).get("players", [])
                if players:
                    p = players[0]
                    return {
                        "steam_id": steam_id,
                        "username": p.get("personaname", f"User_{steam_id[-6:]}"),
                        "avatar_url": p.get("avatarfull", ""),
                    }
            except Exception:
                pass

        return {
            "steam_id": steam_id,
            "username": f"User_{steam_id[-6:]}",
            "avatar_url": "",
        }

    def get_owned_games(self, steam_id: str) -> list[dict]:
        if _get_api_key():
            try:
                url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
                res = requests.get(url, params={
                    "key": _get_api_key(),
                    "steamid": steam_id,
                    "include_appinfo": True,
                    "include_played_free_games": True,
                }, timeout=5)
                games = res.json().get("response", {}).get("games", [])
                if games:
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
                pass

        source = DUMMY_OWNED_GAMES.get(steam_id) or DUMMY_OWNED_GAMES[next(iter(DUMMY_OWNED_GAMES))]
        result = []
        for g in source:
            app_id = g["app_id"]
            catalog = GAME_CATALOG.get(app_id, {})
            result.append({
                **g,
                "genres": catalog.get("genres", g.get("genres", [])),
                "header_image": catalog.get("header_image", g.get("header_image", "")),
                "store_url": catalog.get("store_url", g.get("store_url", "")),
            })
        return result

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
