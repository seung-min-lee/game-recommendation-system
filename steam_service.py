import os
import requests
from dummy_data import GAME_CATALOG, DUMMY_OWNED_GAMES

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")


class SteamService:

    def get_user_summary(self, steam_id: str) -> dict | None:
        if STEAM_API_KEY:
            try:
                url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
                res = requests.get(url, params={"key": STEAM_API_KEY, "steamids": steam_id}, timeout=5)
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
        if STEAM_API_KEY:
            try:
                url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
                res = requests.get(url, params={
                    "key": STEAM_API_KEY,
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

        if steam_id in DUMMY_OWNED_GAMES:
            return DUMMY_OWNED_GAMES[steam_id]

        default_id = next(iter(DUMMY_OWNED_GAMES))
        return DUMMY_OWNED_GAMES[default_id]

    def get_game_detail(self, app_id: int) -> dict | None:
        info = GAME_CATALOG.get(app_id)
        if info:
            return {"app_id": app_id, **info}
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
            res = requests.get(url, timeout=5)
            data = res.json().get(str(app_id), {})
            if data.get("success"):
                d = data["data"]
                return {
                    "app_id": app_id,
                    "name": d.get("name"),
                    "genres": [g["description"] for g in d.get("genres", [])],
                    "header_image": d.get("header_image"),
                    "store_url": f"https://store.steampowered.com/app/{app_id}",
                }
        except Exception:
            pass
        return None
