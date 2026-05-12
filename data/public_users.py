# 잘 알려진 공개 Steam 프로필 유저 목록
# KNOWN_PUBLIC_GAMES: 프로필 비공개 또는 API 키 없을 때 사용할 하드코딩 기본 게임 목록
# API로 실제 데이터 조회에 성공하면 자동으로 덮어쓰여짐

KNOWN_PUBLIC_USERS: dict[str, str] = {
    "76561198028136433": "shroud",
    "76561198000422337": "summit1g",
    "76561197985885934": "Lirik",
    "76561197993333386": "Sodapoppin",
    "76561198199386731": "xQc",
    "76561198044497329": "TimTheTatman",
    "76561198145938129": "Pokimane",
    "76561198015693446": "Ninja",
    "76561197960287930": "GabeN",
    "76561198071482715": "CohhCarnage",
}

# app_id, playtime_minutes (추정치 기반)
KNOWN_PUBLIC_GAMES: dict[str, list[dict]] = {
    "76561198028136433": [  # shroud — FPS 특화
        {"app_id": 730,     "playtime_minutes": 85000, "name": "Counter-Strike 2"},
        {"app_id": 578080,  "playtime_minutes": 32000, "name": "PUBG"},
        {"app_id": 1172470, "playtime_minutes": 18000, "name": "Apex Legends"},
        {"app_id": 359550,  "playtime_minutes": 12000, "name": "Rainbow Six Siege"},
        {"app_id": 1237970, "playtime_minutes":  5000, "name": "Titanfall 2"},
        {"app_id": 1085660, "playtime_minutes":  4000, "name": "Destiny 2"},
    ],
    "76561198000422337": [  # summit1g — FPS + GTA
        {"app_id": 730,     "playtime_minutes": 60000, "name": "Counter-Strike 2"},
        {"app_id": 271590,  "playtime_minutes": 25000, "name": "GTA V"},
        {"app_id": 359550,  "playtime_minutes": 14000, "name": "Rainbow Six Siege"},
        {"app_id": 578080,  "playtime_minutes":  9000, "name": "PUBG"},
        {"app_id": 1172470, "playtime_minutes":  8000, "name": "Apex Legends"},
        {"app_id": 440,     "playtime_minutes":  6000, "name": "Team Fortress 2"},
    ],
    "76561197985885934": [  # Lirik — Variety (Survival + RPG)
        {"app_id": 252490,  "playtime_minutes": 20000, "name": "Rust"},
        {"app_id": 271590,  "playtime_minutes": 15000, "name": "GTA V"},
        {"app_id": 292030,  "playtime_minutes": 12000, "name": "Witcher 3"},
        {"app_id": 346110,  "playtime_minutes": 10000, "name": "ARK"},
        {"app_id": 730,     "playtime_minutes":  9000, "name": "Counter-Strike 2"},
        {"app_id": 1091500, "playtime_minutes":  7000, "name": "Cyberpunk 2077"},
        {"app_id": 105600,  "playtime_minutes":  6000, "name": "Terraria"},
    ],
    "76561197993333386": [  # Sodapoppin — Variety + MMO
        {"app_id": 271590,  "playtime_minutes": 18000, "name": "GTA V"},
        {"app_id": 730,     "playtime_minutes": 15000, "name": "Counter-Strike 2"},
        {"app_id": 252490,  "playtime_minutes": 10000, "name": "Rust"},
        {"app_id": 1245620, "playtime_minutes":  8000, "name": "ELDEN RING"},
        {"app_id": 374320,  "playtime_minutes":  6000, "name": "Dark Souls III"},
        {"app_id": 292030,  "playtime_minutes":  5000, "name": "Witcher 3"},
    ],
    "76561198199386731": [  # xQc — GTA + Variety
        {"app_id": 271590,  "playtime_minutes": 30000, "name": "GTA V"},
        {"app_id": 730,     "playtime_minutes": 20000, "name": "Counter-Strike 2"},
        {"app_id": 1245620, "playtime_minutes": 10000, "name": "ELDEN RING"},
        {"app_id": 252490,  "playtime_minutes":  8000, "name": "Rust"},
        {"app_id": 1172470, "playtime_minutes":  7000, "name": "Apex Legends"},
        {"app_id": 2215430, "playtime_minutes":  5000, "name": "Baldur's Gate 3"},
    ],
    "76561198044497329": [  # TimTheTatman — FPS + Casual
        {"app_id": 730,     "playtime_minutes": 25000, "name": "Counter-Strike 2"},
        {"app_id": 1172470, "playtime_minutes": 18000, "name": "Apex Legends"},
        {"app_id": 578080,  "playtime_minutes": 12000, "name": "PUBG"},
        {"app_id": 359550,  "playtime_minutes":  8000, "name": "Rainbow Six Siege"},
        {"app_id": 271590,  "playtime_minutes":  6000, "name": "GTA V"},
    ],
    "76561198145938129": [  # Pokimane — Indie + Casual
        {"app_id": 413150,  "playtime_minutes": 15000, "name": "Stardew Valley"},
        {"app_id": 881020,  "playtime_minutes":  8000, "name": "Hollow Knight"},
        {"app_id": 1145360, "playtime_minutes":  6000, "name": "Hades"},
        {"app_id": 504230,  "playtime_minutes":  5000, "name": "Celeste"},
        {"app_id": 1794680, "playtime_minutes":  4000, "name": "Vampire Survivors"},
        {"app_id": 1426210, "playtime_minutes":  3000, "name": "It Takes Two"},
        {"app_id": 105600,  "playtime_minutes":  3000, "name": "Terraria"},
    ],
    "76561198015693446": [  # Ninja — FPS + Battle Royale
        {"app_id": 730,     "playtime_minutes": 40000, "name": "Counter-Strike 2"},
        {"app_id": 1172470, "playtime_minutes": 22000, "name": "Apex Legends"},
        {"app_id": 578080,  "playtime_minutes": 15000, "name": "PUBG"},
        {"app_id": 1240440, "playtime_minutes": 10000, "name": "Halo Infinite"},
        {"app_id": 2519060, "playtime_minutes":  6000, "name": "Helldivers 2"},
    ],
    "76561197960287930": [  # GabeN — 모든 장르 (Valve 직원)
        {"app_id": 730,     "playtime_minutes": 10000, "name": "Counter-Strike 2"},
        {"app_id": 440,     "playtime_minutes":  8000, "name": "Team Fortress 2"},
        {"app_id": 570,     "playtime_minutes":  7000, "name": "Dota 2"},
        {"app_id": 292030,  "playtime_minutes":  5000, "name": "Witcher 3"},
        {"app_id": 1245620, "playtime_minutes":  4000, "name": "ELDEN RING"},
        {"app_id": 2215430, "playtime_minutes":  3000, "name": "Baldur's Gate 3"},
    ],
    "76561198071482715": [  # CohhCarnage — RPG 특화
        {"app_id": 292030,  "playtime_minutes": 30000, "name": "Witcher 3"},
        {"app_id": 2215430, "playtime_minutes": 25000, "name": "Baldur's Gate 3"},
        {"app_id": 1091500, "playtime_minutes": 20000, "name": "Cyberpunk 2077"},
        {"app_id": 1245620, "playtime_minutes": 15000, "name": "ELDEN RING"},
        {"app_id": 1158310, "playtime_minutes": 12000, "name": "Crusader Kings III"},
        {"app_id": 524220,  "playtime_minutes": 10000, "name": "NieR: Automata"},
        {"app_id": 1382330, "playtime_minutes":  8000, "name": "Persona 5 Royal"},
        {"app_id": 1174180, "playtime_minutes":  7000, "name": "RDR2"},
    ],
}
