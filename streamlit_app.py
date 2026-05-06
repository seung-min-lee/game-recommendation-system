import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from services.steam_service import SteamService
from ml.recommender import GameRecommender

try:
    from services.snowflake_service import snowflake_svc
    _snowflake_ok = True
except Exception:
    _snowflake_ok = False

st.set_page_config(
    page_title="Game Finder",
    page_icon="🎮",
    layout="wide",
)

steam = SteamService()
recommender = GameRecommender()

# ── 전역 CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');

    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
        background-color: #141414 !important;
        color: #e5e5e5 !important;
        font-family: 'Noto Sans KR', -apple-system, sans-serif !important;
    }
    [data-testid="stHeader"] { background: #141414 !important; }
    [data-testid="stSidebar"] { background: #141414 !important; }
    .block-container { padding-top: 2rem !important; max-width: 1200px !important; }

    /* 입력창 */
    div[data-testid="stTextInput"] input {
        background-color: #333333 !important;
        border: none !important;
        border-radius: 4px !important;
        color: #ffffff !important;
        font-size: 1rem !important;
        padding: 16px 20px !important;
    }
    div[data-testid="stTextInput"] input:focus {
        background-color: #454545 !important;
        box-shadow: none !important;
    }

    /* 버튼 */
    .stButton > button {
        background-color: #E50914 !important;
        color: white !important;
        border: none !important;
        border-radius: 4px !important;
        font-size: 1rem !important;
        font-weight: bold !important;
        padding: 14px 30px !important;
        width: 100% !important;
        transition: background-color 0.2s !important;
    }
    .stButton > button:hover {
        background-color: #c90812 !important;
        border: none !important;
    }

    /* 탭 */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #141414 !important;
        border-bottom: 2px solid #2f2f2f !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #b3b3b3 !important;
        font-weight: bold !important;
        background-color: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #ffffff !important;
        border-bottom: 3px solid #E50914 !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        background-color: #141414 !important;
        padding-top: 20px !important;
    }

    /* 구분선 */
    hr { border-color: #2f2f2f !important; }
    h1, h2, h3, h4 { color: #ffffff !important; }
    p { color: #e5e5e5; }

    /* 리뷰 페이지 라디오 버튼 소형화 */
    div[data-testid="stRadio"] label {
        font-size: 0.72rem !important;
        padding: 2px 6px !important;
    }
    div[data-testid="stRadio"] > div {
        gap: 4px !important;
        flex-wrap: wrap !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state 초기화 ──────────────────────────────────────────────────────
for key, default in [
    ("page", "login"),
    ("steam_id", None),
    ("user", None),
    ("stats", None),
    ("recs", None),
    ("owned_games", []),
    ("friends_games", {}),
    ("friends_profiles", {}),
    ("friends_count", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
def _get_recs(steam_id, owned_games, friends_games=None):
    if _snowflake_ok:
        try:
            if snowflake_svc.has_recommendations(steam_id):
                import json as _j
                def _fmt(g):
                    genres = g.get("genres", [])
                    if isinstance(genres, str):
                        try: genres = _j.loads(genres)
                        except: genres = [genres]
                    return {
                        "app_id": g.get("app_id"), "name": g.get("game_name"),
                        "header_image": g.get("header_image"), "store_url": g.get("store_url"),
                        "genres": genres,
                        "match_percent": g.get("metacritic") or min(int(float(g.get("score") or 0)), 100),
                        "metacritic": g.get("metacritic"),
                    }
                return {
                    "genre_based":  [_fmt(g) for g in snowflake_svc.get_cbf_recommendations(steam_id)],
                    "collab_based": [_fmt(g) for g in snowflake_svc.get_cf_recommendations(steam_id)],
                    "hidden_gems":  [_fmt(g) for g in snowflake_svc.get_genre_trend(steam_id)],
                    "source": "snowflake",
                }
        except Exception:
            pass
    return {
        **recommender.get_recommendations(steam_id, owned_games, real_users=friends_games or {}),
        "source": "local",
    }


def _next_steam_sale() -> tuple[str, int]:
    """다음 주요 스팀 세일 이름과 D-day(남은 일수)를 반환."""
    from datetime import date
    today = date.today()
    y = today.year
    # 매년 반복되는 주요 Steam 세일 일정 (근사치)
    schedule = [
        ("Spring Sale",  date(y, 3, 13)),
        ("Summer Sale",  date(y, 6, 26)),
        ("Autumn Sale",  date(y, 11, 27)),
        ("Winter Sale",  date(y, 12, 19)),
        ("Spring Sale",  date(y + 1, 3, 13)),
        ("Summer Sale",  date(y + 1, 6, 26)),
    ]
    for name, d in schedule:
        if d > today:
            return name, (d - today).days
    return ("Winter Sale", 365)


def _render_carousel(games: list):
    html = _carousel_html(games)
    components.html(html, height=360, scrolling=False)


def _review_card_html(r: dict, idx: int) -> str:
    """리뷰 카드 HTML — 고정 높이 + 하단 화살표 접기/펼치기."""
    icon  = "👍" if r["voted_up"] else "👎"
    color = "#46d369" if r["voted_up"] else "#E50914"
    pt    = r.get("playtime_hours", 0)
    text  = (r.get("text") or "(리뷰 내용 없음)").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<div class="card" id="card-{idx}" style="border-top:3px solid {color};">'
        f'  <div class="card-header" style="color:{color};">{icon}&nbsp; 플레이 {pt}시간</div>'
        f'  <div class="card-wrap" id="wrap-{idx}">'
        f'    <div class="card-body" id="body-{idx}">{text}</div>'
        f'    <div class="fade" id="fade-{idx}"></div>'
        f'  </div>'
        f'  <button class="toggle-btn" id="btn-{idx}" onclick="toggle({idx})" style="display:none;">▼</button>'
        f'</div>'
    )


def _show_reviews_panel(games: list, key_prefix: str):
    """캐러셀 아래 — 게임 선택 → Steam 리뷰(한국어 번역) + 페이지네이션."""
    if not games:
        return

    PER_PAGE = 10

    names    = [g.get("name", "Unknown") for g in games]
    selected = st.selectbox(
        "",
        options=["🔍 게임을 선택하면 Steam 리뷰를 표시합니다"] + names,
        key=f"review_sel_{key_prefix}",
        label_visibility="collapsed",
    )
    if selected.startswith("🔍"):
        return

    game = next((g for g in games if g.get("name") == selected), None)
    if not game:
        return

    app_id    = game["app_id"]
    cache_key = f"_rv_{app_id}"

    if cache_key not in st.session_state:
        with st.spinner("Steam 리뷰 불러오는 중 (한국어 번역 포함)..."):
            st.session_state[cache_key] = steam.get_reviews(app_id, num=100)

    rv          = st.session_state[cache_key]
    summary     = rv.get("summary", {})
    all_reviews = rv.get("reviews", [])

    total = summary.get("total", 0)
    pct   = summary.get("positive_pct", 0)
    desc  = summary.get("score_desc", "")
    mc    = game.get("metacritic") or 0

    pct_color = "#46d369" if pct >= 85 else ("#f5c518" if pct >= 60 else "#E50914")

    mc_badge = (
        f'<span style="background:#1a1a2e;color:#7986cb;border:1px solid #7986cb;'
        f'border-radius:4px;padding:2px 8px;font-size:0.8rem;font-weight:bold;">'
        f'Metacritic {mc}</span>'
    ) if mc else ""

    # ── 요약 헤더 (완전한 HTML — unclosed div 없음) ───────────────────────────
    st.markdown(
        f'<div style="background:#181818;border-radius:10px;padding:16px 22px;'
        f'margin-top:4px;border-left:4px solid {pct_color};">'
        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-size:1.05rem;font-weight:bold;color:#fff;">{selected}</span>'
        f'<span style="background:{pct_color};color:#000;border-radius:4px;'
        f'padding:2px 9px;font-size:0.82rem;font-weight:bold;">{desc}</span>'
        f'<span style="color:{pct_color};font-weight:bold;">👍 {pct}%</span>'
        f'<span style="color:#737373;font-size:0.8rem;">전체 리뷰 {total:,}개</span>'
        f'{mc_badge}'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    if not all_reviews:
        st.markdown(
            '<div style="background:#181818;border-radius:8px;padding:20px 24px;margin-top:10px;">'
            '<p style="color:#737373;font-size:0.9rem;margin:0;">'
            '⚠️ 이 게임의 Steam 리뷰를 가져올 수 없습니다.<br>'
            '<span style="font-size:0.8rem;">Steam 구매 리뷰가 없거나 API 응답이 없는 경우입니다.</span>'
            '</p></div>',
            unsafe_allow_html=True,
        )
        return

    # ── 정렬 (오른쪽 끝, 가로 1행) ───────────────────────────────────────────
    _, sort_col = st.columns([1, 3])
    with sort_col:
        sort_key = f"_rv_sort_{key_prefix}_{app_id}"
        sort_opt = st.radio(
            "",
            options=["👍 많은 순", "👎 많은 순", "⏱ 플레이타임 많은 순", "⏱ 플레이타임 적은 순"],
            key=sort_key,
            horizontal=True,
            label_visibility="collapsed",
        )

    # 정렬 적용
    if sort_opt == "👍 많은 순":
        sorted_reviews = sorted(all_reviews, key=lambda r: (not r["voted_up"], -r.get("playtime_hours", 0)))
    elif sort_opt == "👎 많은 순":
        sorted_reviews = sorted(all_reviews, key=lambda r: (r["voted_up"], -r.get("playtime_hours", 0)))
    elif sort_opt == "⏱ 플레이타임 많은 순":
        sorted_reviews = sorted(all_reviews, key=lambda r: -r.get("playtime_hours", 0))
    else:
        sorted_reviews = sorted(all_reviews, key=lambda r: r.get("playtime_hours", 0))

    total_pages = max(1, (len(sorted_reviews) + PER_PAGE - 1) // PER_PAGE)
    page_key    = f"_rv_pg_{key_prefix}_{app_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    cur_page = min(st.session_state[page_key], total_pages - 1)

    page_reviews = sorted_reviews[cur_page * PER_PAGE:(cur_page + 1) * PER_PAGE]

    # ── 리뷰 카드 그리드 — components.html (고정 높이 + 하단 화살표 접기/펼치기) ──
    CARD_H     = 170   # 카드 콘텐츠 영역 고정 높이(px)
    OVERHEAD   = 95    # 헤더 + 버튼 + 패딩 합계(px)
    CPL        = 44    # 카드 너비 기준 한 줄당 글자 수 근사치
    LINE_H     = 22    # 한 줄 높이(px)

    def _expanded_h(r: dict) -> int:
        lines = max(1, -(-len(r.get("text") or "") // CPL))  # ceiling division
        return max(CARD_H, lines * LINE_H) + OVERHEAD

    # 행마다 가장 긴 카드 높이로 계산 (전부 펼쳐졌을 때 기준)
    total_height = 30  # 상하 패딩
    for i in range(0, len(page_reviews), 3):
        row = page_reviews[i:i + 3]
        total_height += max(_expanded_h(r) for r in row) + 14  # gap

    cards_html = "".join(_review_card_html(r, i) for i, r in enumerate(page_reviews))
    row_count  = (len(page_reviews) + 2) // 3
    base_height = total_height
    components.html(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    background: #141414;
    font-family: 'Noto Sans KR', -apple-system, sans-serif;
    overflow-x: hidden;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    padding: 6px 2px 10px;
    /* 각 행의 카드 높이를 auto로 — 카드가 직접 고정 */
    align-items: start;
  }}
  .card {{
    background: #202020;
    border-radius: 8px;
    padding: 14px 16px 0;
    display: flex;
    flex-direction: column;
  }}
  .card-header {{
    font-weight: bold;
    font-size: 0.82rem;
    margin-bottom: 10px;
    flex-shrink: 0;
    white-space: nowrap;
  }}
  /* 텍스트 영역 래퍼 — 고정 높이, 넘치면 숨김 */
  .card-wrap {{
    position: relative;
    height: {CARD_H}px;
    overflow: hidden;
    transition: height 0.28s ease;
  }}
  .card-wrap.expanded {{
    height: auto;
    overflow: visible;
  }}
  /* 하단 gradient fade — 텍스트가 잘릴 때만 표시 */
  .fade {{
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 40px;
    background: linear-gradient(transparent, #202020);
    pointer-events: none;
    transition: opacity 0.2s;
  }}
  .card-wrap.expanded .fade {{
    display: none;
  }}
  .card-body {{
    font-size: 0.81rem;
    line-height: 1.65;
    color: #d0d0d0;
    word-break: break-word;
  }}
  /* 하단 화살표 버튼 */
  .toggle-btn {{
    width: 100%;
    background: none;
    border: none;
    border-top: 1px solid #2e2e2e;
    color: #666;
    font-size: 0.85rem;
    cursor: pointer;
    padding: 7px 0 9px;
    text-align: center;
    flex-shrink: 0;
    transition: color 0.15s, background 0.15s;
    border-radius: 0 0 8px 8px;
    margin-top: 6px;
  }}
  .toggle-btn:hover {{ color: #bbb; background: #272727; }}
</style>
</head><body>
<div class="grid" id="grid">{cards_html}</div>
<script>
  var CARD_H = {CARD_H};

  document.addEventListener('DOMContentLoaded', function() {{
    // 각 카드: 텍스트가 고정 높이를 초과하면 fade + 버튼 표시
    document.querySelectorAll('.card-wrap').forEach(function(wrap) {{
      var idx  = wrap.id.replace('wrap-', '');
      var body = document.getElementById('body-' + idx);
      var btn  = document.getElementById('btn-' + idx);
      var fade = document.getElementById('fade-' + idx);
      if (body.scrollHeight <= CARD_H + 4) {{
        // 텍스트가 짧음 — fade · 버튼 숨김
        if (fade) fade.style.display = 'none';
        btn.style.display = 'none';
      }} else {{
        btn.style.display = 'block';
      }}
    }});
  }});

  function toggle(idx) {{
    var wrap = document.getElementById('wrap-' + idx);
    var btn  = document.getElementById('btn-' + idx);
    var expanded = wrap.classList.toggle('expanded');
    btn.textContent = expanded ? '▲' : '▼';
  }}
</script>
</body></html>""",
        height=base_height,
        scrolling=False,
    )

    # ── 페이지 번호 (카드 그리드 바로 아래, 여백 없음) ──────────────────────
    if total_pages > 1:
        _, pg_col, _ = st.columns([1.5, 6, 0.1])
        with pg_col:
            st.markdown(
                f'<p style="color:#737373;font-size:0.75rem;margin:0 0 2px;">'
                f'총 {len(sorted_reviews)}개 리뷰 · 페이지당 {PER_PAGE}개</p>',
                unsafe_allow_html=True,
            )
            chosen = st.radio(
                "",
                options=list(range(1, min(total_pages, 16) + 1)),
                index=cur_page,
                horizontal=True,
                key=f"rv_radio_{key_prefix}_{app_id}",
                label_visibility="collapsed",
                format_func=lambda p: f"{p}",
            )
            if chosen - 1 != cur_page:
                st.session_state[page_key] = chosen - 1
                st.rerun()


def _price_badge_html(pi: dict | None, next_sale_name: str, next_sale_dday: int) -> str:
    """가격/할인 배지 HTML 반환."""
    if pi is None:
        # 가격 정보 없음 — D-day만 표시
        return (
            f'<div style="display:flex;align-items:center;gap:6px;margin:5px 0 0;">'
            f'<span style="color:#aaa;font-size:0.72rem;">🗓 {next_sale_name} D-{next_sale_dday}</span>'
            f'</div>'
        )
    if pi.get("is_free"):
        return (
            f'<div style="margin:5px 0 0;">'
            f'<span style="background:#46d369;color:#000;border-radius:3px;'
            f'padding:2px 7px;font-size:0.75rem;font-weight:bold;">무료</span>'
            f'</div>'
        )
    disc = pi.get("discount_percent", 0)
    final = pi.get("final", "")
    original = pi.get("original", "")
    if disc > 0:
        # 현재 할인 중
        return (
            f'<div style="display:flex;align-items:center;gap:5px;margin:5px 0 0;flex-wrap:wrap;">'
            f'<span style="background:#FF6B35;color:#fff;border-radius:3px;'
            f'padding:2px 6px;font-size:0.78rem;font-weight:bold;">-{disc}%</span>'
            f'<span style="color:#aaa;text-decoration:line-through;font-size:0.72rem;">{original}</span>'
            f'<span style="color:#46d369;font-weight:bold;font-size:0.82rem;">{final}</span>'
            f'</div>'
        )
    else:
        # 할인 없음 — 현재가 + 다음 세일 D-day
        return (
            f'<div style="display:flex;align-items:center;gap:6px;margin:5px 0 0;flex-wrap:wrap;">'
            f'<span style="color:#e5e5e5;font-size:0.80rem;">{final}</span>'
            f'<span style="color:#888;font-size:0.70rem;">· 🗓 D-{next_sale_dday}</span>'
            f'</div>'
        )


def _carousel_html(games: list) -> str:
    if not games:
        return '<p style="color:#b3b3b3;padding:20px 0;">추천 결과가 없습니다.</p>'
    next_sale_name, next_sale_dday = _next_steam_sale()
    cards = ""
    for g in games:
        name       = (g.get("name") or "Unknown").replace("'", "&#39;")
        img        = g.get("header_image") or "https://via.placeholder.com/280x150/181818/555?text=No+Image"
        match_pct  = g.get("match_percent", 0)
        store_url  = g.get("store_url", "#")
        metacritic = g.get("metacritic")
        reason     = g.get("reason", "")
        price_info = g.get("price_info")  # 가격 정보 (없으면 None)
        mc_html    = f'<span style="background:#E50914;color:#fff;border-radius:3px;padding:1px 6px;font-size:0.72rem;font-weight:bold;">MC {metacritic}</span>' if metacritic else ""
        reason_html = (
            f'<p style="color:#a0a0b0;font-size:0.72rem;margin:5px 0 0;'
            f'line-height:1.35;border-top:1px solid #2a2a2a;padding-top:5px;">'
            f'🤖 {reason}</p>'
        ) if reason else ""
        price_html = _price_badge_html(price_info, next_sale_name, next_sale_dday)
        cards += f"""
        <div onclick="window.open('{store_url}','_blank')" style="
            background:#181818; border-radius:8px; overflow:hidden;
            cursor:pointer; width:240px; flex:0 0 auto; scroll-snap-align:start;
            transition:transform 0.3s,box-shadow 0.3s;
            " onmouseover="this.style.transform='scale(1.06)';this.style.boxShadow='0 15px 30px rgba(0,0,0,0.7)';this.style.zIndex='10'"
               onmouseout="this.style.transform='scale(1)';this.style.boxShadow='none';this.style.zIndex='1'">
            <img src="{img}" style="width:100%;height:135px;object-fit:cover;"
                 onerror="this.src='https://via.placeholder.com/240x135/181818/555?text=No+Image'">
            <div style="padding:12px;">
                <p style="color:#fff;font-size:0.93rem;font-weight:bold;margin:0 0 6px;
                           white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</p>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="color:#46d369;font-weight:bold;font-size:0.88rem;">{match_pct}% 일치</span>
                    {mc_html}
                </div>
                {price_html}
                <p style="color:#E50914;font-size:0.78rem;margin:5px 0 0;font-weight:bold;">스토어 이동 ➔</p>
                {reason_html}
            </div>
        </div>"""
    return f"""
    <div style="display:flex;overflow-x:auto;scroll-snap-type:x mandatory;
                gap:16px;padding:10px 0 20px;scrollbar-width:thin;
                scrollbar-color:#333 #141414;">
        {cards}
    </div>"""


# ── LightGCN 그래프 ────────────────────────────────────────────────────────────
def _build_lightgcn_graph(steam_id, owned_games, rec_games):
    import math
    from data.dummy_data import DUMMY_OWNED_GAMES, GAME_CATALOG

    all_interactions = {}
    for uid, games in DUMMY_OWNED_GAMES.items():
        all_interactions[uid] = {g["app_id"]: g.get("playtime_minutes", 1) for g in games}
    all_interactions[steam_id] = {g["app_id"]: g.get("playtime_minutes", 1) for g in owned_games}

    users    = list(all_interactions.keys())
    game_ids = sorted({aid for gs in all_interactions.values() for aid in gs})
    owned_ids = {g["app_id"] for g in owned_games}
    rec_ids   = {g["app_id"] for g in rec_games}

    # ── 유저: 왼쪽 세로 배치, 내 유저는 중앙 고정
    n_u = len(users)
    me_idx = users.index(steam_id) if steam_id in users else 0
    user_pos: dict = {}
    others = [u for u in users if u != steam_id]
    for i, u in enumerate(others):
        y = (i + 1) / (len(others) + 1)
        user_pos[u] = (-1.0, y)
    user_pos[steam_id] = (-1.0, 0.5)

    # ── 게임: 오른쪽 원형 배치 (장르별 클러스터)
    genre_order: dict[str, int] = {}
    for aid in game_ids:
        g = GAME_CATALOG.get(aid, {}).get("genres", ["기타"])
        genre = g[0] if g else "기타"
        if genre not in genre_order:
            genre_order[genre] = len(genre_order)

    n_g = len(game_ids)
    game_pos: dict = {}
    for i, aid in enumerate(game_ids):
        angle = 2 * math.pi * i / max(n_g, 1) - math.pi / 2
        r = 0.72
        game_pos[aid] = (1.0 + r * math.cos(angle), 0.5 + r * math.sin(angle) * 0.85)

    fig = go.Figure()

    # ── 엣지: 타 유저(희미) / 내 보유(파랑) / 내 추천(빨강) 3개 trace로 묶기
    def _edge_xy(uid_list, game_map, is_me_flag, category):
        xs, ys = [], []
        for uid, games in all_interactions.items():
            if (uid == steam_id) != is_me_flag:
                continue
            ux, uy = user_pos[uid]
            for aid in games:
                if category == "rec"   and aid not in rec_ids:   continue
                if category == "owned" and aid in rec_ids:        continue
                gx, gy = game_pos[aid]
                xs += [ux, gx, None]
                ys += [uy, gy, None]
        return xs, ys

    other_ex, other_ey = _edge_xy(users, game_pos, False, "all")
    owned_ex, owned_ey = _edge_xy(users, game_pos, True,  "owned")
    rec_ex,   rec_ey   = _edge_xy(users, game_pos, True,  "rec")

    fig.add_trace(go.Scatter(
        x=other_ex, y=other_ey, mode="lines",
        line=dict(width=0.4, color="rgba(255,255,255,0.05)"),
        hoverinfo="none", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=owned_ex, y=owned_ey, mode="lines",
        line=dict(width=1.4, color="rgba(100,160,255,0.45)"),
        hoverinfo="none", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=rec_ex, y=rec_ey, mode="lines",
        line=dict(width=2.2, color="rgba(229,9,20,0.75)"),
        hoverinfo="none", showlegend=False,
    ))

    # ── 유저 노드
    for uid in users:
        ux, uy = user_pos[uid]
        is_me  = uid == steam_id
        label  = "👤 나" if is_me else f"U_{uid[-4:]}"
        fig.add_trace(go.Scatter(
            x=[ux], y=[uy], mode="markers+text",
            marker=dict(
                size=26 if is_me else 13,
                color="#E50914" if is_me else "#4a4a5a",
                symbol="circle",
                line=dict(width=2 if is_me else 1,
                          color="white" if is_me else "#777"),
            ),
            text=[label],
            textposition="middle left",
            textfont=dict(size=13 if is_me else 9,
                          color="white" if is_me else "#888"),
            hovertemplate=(
                f"<b>{label}</b><br>"
                f"게임 수: {len(all_interactions[uid])}<extra></extra>"
            ),
            showlegend=False,
        ))

    # ── 게임 노드
    for aid in game_ids:
        gx, gy = game_pos[aid]
        name   = GAME_CATALOG.get(aid, {}).get("name", f"Game_{aid}")
        genres = ", ".join(GAME_CATALOG.get(aid, {}).get("genres", [])[:2])
        short  = name[:14] + ("…" if len(name) > 14 else "")
        if aid in rec_ids:
            clr, sym, sz = "#FF3B3B", "star", 18
            label = f"⭐ {short}"
            tfont = dict(size=10, color="#FF6B6B")
        elif aid in owned_ids:
            clr, sym, sz = "#64A0FF", "square", 14
            label = f"🎮 {short}"
            tfont = dict(size=9, color="#90C0FF")
        else:
            clr, sym, sz = "#3a3a4a", "circle", 7
            label = ""
            tfont = dict(size=8, color="#555")
        fig.add_trace(go.Scatter(
            x=[gx], y=[gy],
            mode="markers+text" if label else "markers",
            marker=dict(size=sz, color=clr, symbol=sym,
                        line=dict(width=1.2 if aid in rec_ids | owned_ids else 0,
                                  color="#ffffff" if aid in rec_ids else "#3a5a80")),
            text=[label] if label else [],
            textposition="top center",
            textfont=tfont,
            hovertemplate=f"<b>{name}</b><br>{genres}<extra></extra>",
            showlegend=False,
        ))

    # ── 범례 전용 trace
    for lbl, clr, sym in [
        ("현재 유저",    "#E50914", "circle"),
        ("다른 유저",    "#4a4a5a", "circle"),
        ("추천 게임 ⭐", "#FF3B3B", "star"),
        ("보유 게임",    "#64A0FF", "square"),
        ("기타 게임",    "#3a3a4a", "circle"),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=clr, symbol=sym,
                        line=dict(width=1, color="white")),
            name=lbl, showlegend=True,
        ))

    fig.update_layout(
        paper_bgcolor="#0e0e0e",
        plot_bgcolor="#0e0e0e",
        font_color="#e5e5e5",
        height=620,
        margin=dict(l=140, r=60, t=50, b=30),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-1.5, 2.1]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-0.25, 1.25], scaleanchor="x", scaleratio=1),
        legend=dict(
            x=0.01, y=0.99, xanchor="left", yanchor="top",
            bgcolor="rgba(20,20,20,0.85)",
            bordercolor="#333", borderwidth=1,
            font=dict(color="white", size=11),
        ),
        annotations=[
            dict(x=-1.0, y=1.12, xref="x", yref="y",
                 text="<b>유저 노드</b>", showarrow=False,
                 font=dict(size=12, color="#b3b3b3")),
            dict(x=1.0, y=1.12, xref="x", yref="y",
                 text="<b>게임 노드</b>", showarrow=False,
                 font=dict(size=12, color="#b3b3b3")),
        ],
    )
    return fig


# ── 나 & 친구 통계 탭 ────────────────────────────────────────────────────────
def _render_stats_tab():
    import math
    from collections import Counter
    from data.dummy_data import GAME_CATALOG

    owned_games      = st.session_state.get("owned_games", [])
    friends_games    = st.session_state.get("friends_games", {})
    friends_profiles = st.session_state.get("friends_profiles", {})
    username         = (st.session_state.get("user") or {}).get("username", "나")

    # ── 공통 유틸: 장르별 플레이타임(시간) 집계
    def _genre_hours(games: list[dict]) -> dict[str, float]:
        result: dict[str, float] = {}
        for g in games:
            hrs = g.get("playtime_minutes", 0) / 60
            for genre in GAME_CATALOG.get(g.get("app_id"), {}).get("genres", []):
                result[genre] = result.get(genre, 0) + hrs
        return result

    my_genre_hrs = _genre_hours(owned_games)
    my_total_hrs = sum(g.get("playtime_minutes", 0) for g in owned_games) / 60

    # ── 상단 요약 카드
    top5 = sorted(owned_games, key=lambda g: g.get("playtime_minutes", 0), reverse=True)[:5]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div style="background:#1a1a1a;border-radius:10px;padding:18px;text-align:center;border-top:3px solid #E50914;">
            <div style="color:#737373;font-size:0.8rem;">총 플레이타임</div>
            <div style="font-size:2rem;font-weight:800;color:#fff;">{my_total_hrs:,.0f}<span style="font-size:1rem;color:#b3b3b3;">h</span></div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div style="background:#1a1a1a;border-radius:10px;padding:18px;text-align:center;border-top:3px solid #64A0FF;">
            <div style="color:#737373;font-size:0.8rem;">보유 게임 수</div>
            <div style="font-size:2rem;font-weight:800;color:#fff;">{len(owned_games)}<span style="font-size:1rem;color:#b3b3b3;">개</span></div>
        </div>""", unsafe_allow_html=True)
    with c3:
        top_genre = max(my_genre_hrs, key=my_genre_hrs.get) if my_genre_hrs else "-"
        st.markdown(f"""
        <div style="background:#1a1a1a;border-radius:10px;padding:18px;text-align:center;border-top:3px solid #46d369;">
            <div style="color:#737373;font-size:0.8rem;">최다 장르</div>
            <div style="font-size:1.5rem;font-weight:800;color:#fff;">{top_genre}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 내 장르 분포 + 최다 플레이 Top5 (좌우 분할)
    left, right = st.columns([1, 1])

    with left:
        st.markdown('<h3 style="font-size:1.1rem;color:#E50914;margin-bottom:8px;">🎯 장르 플레이타임 분포</h3>', unsafe_allow_html=True)
        if my_genre_hrs:
            top_genres = sorted(my_genre_hrs.items(), key=lambda x: x[1], reverse=True)[:8]
            labels = [g for g, _ in top_genres]
            values = [round(h, 1) for _, h in top_genres]
            GENRE_COLORS = [
                "#E50914","#64A0FF","#46d369","#f5c518","#a855f7",
                "#f97316","#06b6d4","#ec4899",
            ]
            fig_pie = go.Figure(go.Pie(
                labels=labels, values=values,
                hole=0.52,
                marker=dict(colors=GENRE_COLORS[:len(labels)],
                            line=dict(color="#0e0e0e", width=2)),
                textinfo="label+percent",
                textfont=dict(size=11, color="white"),
                hovertemplate="<b>%{label}</b><br>%{value}h<extra></extra>",
            ))
            fig_pie.update_layout(
                paper_bgcolor="#141414", plot_bgcolor="#141414",
                font_color="#e5e5e5", height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with right:
        st.markdown('<h3 style="font-size:1.1rem;color:#64A0FF;margin-bottom:8px;">🏆 최다 플레이 게임 Top 5</h3>', unsafe_allow_html=True)
        if top5:
            names = [g.get("name", f"Game_{g.get('app_id')}")[:20] for g in top5]
            hours = [round(g.get("playtime_minutes", 0) / 60, 1) for g in top5]
            fig_top5 = go.Figure(go.Bar(
                x=hours, y=names, orientation="h",
                marker=dict(
                    color=hours,
                    colorscale=[[0, "#2a3a5a"], [1, "#64A0FF"]],
                    line=dict(width=0),
                ),
                text=[f"{h}h" for h in hours],
                textposition="outside",
                textfont=dict(color="#b3b3b3", size=11),
                hovertemplate="<b>%{y}</b><br>%{x}h<extra></extra>",
            ))
            fig_top5.update_layout(
                paper_bgcolor="#141414", plot_bgcolor="#141414",
                font_color="#b3b3b3", height=300,
                margin=dict(l=10, r=60, t=10, b=10),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", autorange="reversed"),
            )
            st.plotly_chart(fig_top5, use_container_width=True)

    # ── 친구 비교 섹션
    if not friends_games:
        st.markdown("""
        <div style="background:#1a1a1a;border-radius:10px;padding:24px;text-align:center;margin-top:16px;">
            <p style="color:#737373;">친구 목록이 비공개이거나 Steam API 키가 없어<br>친구 비교 통계를 표시할 수 없습니다.</p>
        </div>""", unsafe_allow_html=True)
        return

    st.markdown("---")
    st.markdown('<h3 style="font-size:1.2rem;margin-bottom:16px;">👥 친구와 비교</h3>', unsafe_allow_html=True)

    # Jaccard 유사도 계산 후 상위 5명만
    my_genre_set = set(my_genre_hrs)
    def _jaccard(f_games):
        fw: dict[str, float] = {}
        ft = sum(g.get("playtime_minutes", 0) for g in f_games) or 1
        for g in f_games:
            w = g.get("playtime_minutes", 0) / ft
            for genre in GAME_CATALOG.get(g.get("app_id"), {}).get("genres", []):
                fw[genre] = fw.get(genre, 0) + w
        fs = set(fw)
        inter = len(my_genre_set & fs)
        union = len(my_genre_set | fs)
        return inter / union if union else 0

    ranked = sorted(friends_games.items(), key=lambda kv: -_jaccard(kv[1]))[:5]

    # ── 장르 레이더 차트 (나 + 친구들)
    all_genres = sorted(
        {g for kv in ranked for game in kv[1]
         for g in GAME_CATALOG.get(game.get("app_id"), {}).get("genres", [])}
        | my_genre_set,
        key=lambda g: my_genre_hrs.get(g, 0), reverse=True
    )[:8]

    RADAR_COLORS = ["#E50914","#64A0FF","#46d369","#f5c518","#a855f7","#f97316"]
    fig_radar = go.Figure()

    def _normalize(hrs_dict, genres):
        vals = [hrs_dict.get(g, 0) for g in genres]
        mx = max(vals) or 1
        return [round(v / mx * 100) for v in vals]

    # 내 데이터
    my_vals = _normalize(my_genre_hrs, all_genres)
    fig_radar.add_trace(go.Scatterpolar(
        r=my_vals + [my_vals[0]],
        theta=all_genres + [all_genres[0]],
        fill="toself",
        name=f"👤 {username}",
        line=dict(color="#E50914", width=2.5),
        fillcolor="rgba(229,9,20,0.15)",
    ))

    for idx, (fid, f_games) in enumerate(ranked):
        fname = friends_profiles.get(fid, {}).get("username", f"User_{fid[-4:]}")
        fgh = _genre_hours(f_games)
        fv = _normalize(fgh, all_genres)
        clr = RADAR_COLORS[idx + 1]
        fig_radar.add_trace(go.Scatterpolar(
            r=fv + [fv[0]],
            theta=all_genres + [all_genres[0]],
            fill="toself",
            name=fname,
            line=dict(color=clr, width=1.5),
            fillcolor=f"rgba({int(clr[1:3],16)},{int(clr[3:5],16)},{int(clr[5:7],16)},0.08)",
        ))

    fig_radar.update_layout(
        polar=dict(
            bgcolor="#141414",
            radialaxis=dict(visible=True, range=[0, 100],
                            gridcolor="rgba(255,255,255,0.08)",
                            tickfont=dict(size=9, color="#555"),
                            ticksuffix="%"),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.1)",
                             tickfont=dict(size=11, color="#b3b3b3")),
        ),
        paper_bgcolor="#141414",
        font_color="#e5e5e5",
        height=420,
        margin=dict(l=60, r=60, t=30, b=30),
        legend=dict(bgcolor="rgba(20,20,20,0.85)", bordercolor="#333",
                    borderwidth=1, font=dict(size=11)),
        showlegend=True,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

    # ── 공통 게임 수 + 총 플레이타임 바 차트
    st.markdown('<h3 style="font-size:1.1rem;color:#46d369;margin-bottom:8px;">📊 친구별 공통 게임 & 총 플레이타임</h3>', unsafe_allow_html=True)
    my_app_ids = {g["app_id"] for g in owned_games}

    f_names, f_common, f_hours = [], [], []
    for fid, f_games in ranked:
        fname = friends_profiles.get(fid, {}).get("username", f"User_{fid[-4:]}")
        common = len(my_app_ids & {g["app_id"] for g in f_games})
        total_h = round(sum(g.get("playtime_minutes", 0) for g in f_games) / 60, 1)
        f_names.append(fname)
        f_common.append(common)
        f_hours.append(total_h)

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        name="공통 보유 게임 수",
        x=f_names, y=f_common,
        marker=dict(color="#46d369", line=dict(width=0)),
        yaxis="y",
        hovertemplate="<b>%{x}</b><br>공통 게임: %{y}개<extra></extra>",
    ))
    fig_bar.add_trace(go.Bar(
        name="총 플레이타임 (h)",
        x=f_names, y=f_hours,
        marker=dict(color="#64A0FF", line=dict(width=0)),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>플레이타임: %{y}h<extra></extra>",
    ))
    fig_bar.update_layout(
        barmode="group",
        paper_bgcolor="#141414", plot_bgcolor="#141414",
        font_color="#b3b3b3", height=300,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        yaxis=dict(title="공통 게임 수", gridcolor="rgba(255,255,255,0.05)",
                   titlefont=dict(color="#46d369"), tickfont=dict(color="#46d369")),
        yaxis2=dict(title="플레이타임 (h)", overlaying="y", side="right",
                    gridcolor="rgba(0,0,0,0)",
                    titlefont=dict(color="#64A0FF"), tickfont=dict(color="#64A0FF")),
        legend=dict(bgcolor="rgba(20,20,20,0.85)", bordercolor="#333",
                    borderwidth=1, orientation="h",
                    yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig_bar, use_container_width=True)


# ── 사이드바: 친구 목록 ───────────────────────────────────────────────────────
def _render_friends_sidebar():
    from collections import Counter
    from data.dummy_data import GAME_CATALOG

    friends_games    = st.session_state.get("friends_games", {})
    friends_profiles = st.session_state.get("friends_profiles", {})
    owned_games      = st.session_state.get("owned_games", [])

    with st.sidebar:
        st.markdown("""
        <style>
        [data-testid="stSidebar"] {background:#0e0e0e !important;}
        [data-testid="stSidebar"] * {color:#e5e5e5;}
        </style>
        """, unsafe_allow_html=True)

        st.markdown('<h3 style="color:#E50914;margin-bottom:4px;">👥 스팀 친구</h3>', unsafe_allow_html=True)

        if not friends_games:
            st.markdown(
                '<p style="color:#737373;font-size:0.82rem;">친구 목록이 비공개이거나<br>Steam API 키가 없습니다.<br><br>'
                '유사 패턴 기반 추천이 적용됩니다.</p>',
                unsafe_allow_html=True,
            )
            return

        # 현재 유저 장르 프로필 (플레이타임 가중)
        user_genre_w: dict[str, float] = Counter()
        total_min = sum(g.get("playtime_minutes", 0) for g in owned_games) or 1
        for g in owned_games:
            w = g.get("playtime_minutes", 0) / total_min
            for genre in g.get("genres", []):
                user_genre_w[genre] += w
        user_genre_set = set(user_genre_w)

        st.markdown(
            f'<p style="color:#b3b3b3;font-size:0.8rem;margin-bottom:12px;">'
            f'{len(friends_games)}명의 친구 데이터 기반 추천</p>',
            unsafe_allow_html=True,
        )

        user_app_ids = {g["app_id"] for g in owned_games}

        def _jaccard_sim(f_games):
            f_genre_w: dict[str, float] = Counter()
            f_total = sum(g.get("playtime_minutes", 0) for g in f_games) or 1
            for g in f_games:
                w = g.get("playtime_minutes", 0) / f_total
                for genre in GAME_CATALOG.get(g["app_id"], {}).get("genres", []):
                    f_genre_w[genre] += w
            f_genre_set = set(f_genre_w)
            inter = len(user_genre_set & f_genre_set)
            union = len(user_genre_set | f_genre_set)
            return int(inter / union * 100) if union else 0

        for fid, f_games in sorted(
            friends_games.items(),
            key=lambda kv: -_jaccard_sim(kv[1]),
        ):
            profile  = friends_profiles.get(fid, {})
            username = profile.get("username", f"User_{fid[-4:]}")
            avatar   = profile.get("avatar_url", "")

            # 친구 장르 프로필
            f_genre_w: dict[str, float] = Counter()
            f_total = sum(g.get("playtime_minutes", 0) for g in f_games) or 1
            for g in f_games:
                w = g.get("playtime_minutes", 0) / f_total
                for genre in GAME_CATALOG.get(g["app_id"], {}).get("genres", []):
                    f_genre_w[genre] += w
            f_genre_set = set(f_genre_w)

            # Jaccard 유사도
            inter = len(user_genre_set & f_genre_set)
            union = len(user_genre_set | f_genre_set)
            sim   = int(inter / union * 100) if union else 0

            # 공통 장르 (친구 플레이타임 기준 정렬)
            common_genres = sorted(
                user_genre_set & f_genre_set,
                key=lambda g: f_genre_w.get(g, 0), reverse=True,
            )[:3]

            # 공통 소유 게임 수
            f_app_ids = {g["app_id"] for g in f_games}
            common_cnt = len(user_app_ids & f_app_ids)

            # 색상
            if sim >= 70:
                clr = "#46d369"
            elif sim >= 40:
                clr = "#f5c518"
            else:
                clr = "#b3b3b3"

            av_html = (
                f'<img src="{avatar}" style="width:28px;height:28px;border-radius:50%;'
                f'margin-right:8px;vertical-align:middle;border:1px solid {clr};">'
            ) if avatar else "👤 "

            tags_html = " ".join(
                f'<span style="background:#2a2a2a;color:#b3b3b3;border-radius:3px;'
                f'padding:1px 5px;font-size:0.68rem;">{g}</span>'
                for g in common_genres
            )

            st.markdown(f"""
            <div style="margin-bottom:14px;padding:12px;background:#1a1a1a;border-radius:8px;
                        border-left:3px solid {clr};">
                <div style="display:flex;align-items:center;margin-bottom:6px;">
                    {av_html}<span style="font-weight:bold;font-size:0.86rem;color:#fff;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">{username}</span>
                </div>
                <div style="font-size:0.72rem;color:#737373;margin-bottom:6px;">
                    보유 {len(f_games)}개 &nbsp;·&nbsp; 공통 {common_cnt}개
                </div>
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
                    <div style="flex:1;background:#2f2f2f;border-radius:3px;height:5px;">
                        <div style="width:{sim}%;background:{clr};height:100%;border-radius:3px;"></div>
                    </div>
                    <span style="color:{clr};font-weight:bold;font-size:0.78rem;min-width:32px;">{sim}%</span>
                </div>
                <div>{tags_html}</div>
            </div>
            """, unsafe_allow_html=True)


# ── 페이지: 로그인 ────────────────────────────────────────────────────────────
def page_login():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style="background:rgba(0,0,0,0.75);border-radius:8px;padding:40px 40px 30px;margin-top:60px;text-align:center;">
            <div style="font-size:3.5rem;margin-bottom:10px;">🎮</div>
            <h1 style="color:#E50914;font-size:3rem;font-weight:900;letter-spacing:2px;
                       text-transform:uppercase;margin-bottom:10px;">Game Finder</h1>
            <p style="color:#b3b3b3;font-size:1rem;margin-bottom:0;line-height:1.6;">
                당신의 플레이 기록을 분석하여<br>최고의 게임을 추천합니다.
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        steam_id = st.text_input("", placeholder="스팀 ID 입력 (예: 76561198000000001)",
                                  label_visibility="collapsed")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        _, btn_col, _ = st.columns([1.3, 2, 0.25])
        with btn_col:
            login_clicked = st.button("시작하기", key="login_btn")

        st.markdown("""
        <div style="display:flex;align-items:center;color:#737373;font-size:0.9rem;margin:22px 0 14px;">
            <div style="flex:1;border-bottom:1px solid #333;"></div>
            <span style="padding:0 15px;">Steam ID를 잊어버리셨나요?</span>
            <div style="flex:1;border-bottom:1px solid #333;"></div>
        </div>
        <div style="text-align:center;margin-bottom:10px;">
            <a href="https://store.steampowered.com/login/" target="_blank"
               style="display:inline-block;background:#1b2838;color:#c7d5e0;
                      border:1px solid #4c6b22;border-radius:4px;padding:10px 24px;
                      font-size:0.9rem;font-weight:bold;text-decoration:none;
                      transition:background 0.2s;">
                🔗 Steam 로그인 페이지에서 확인하기
            </a>
        </div>
        <p style="color:#b3b3b3;font-size:0.75rem;text-align:center;margin:0;">
            로그인 후 우측 상단 프로필 → 프로필 보기 → URL의 숫자가 Steam ID입니다.
        </p>
        """, unsafe_allow_html=True)

        if login_clicked:
            if not steam_id or not steam_id.strip():
                st.error("스팀 ID를 입력해주세요.")
                return
            sid = steam_id.strip()
            with st.spinner("게임 데이터 불러오는 중..."):
                user = steam.get_user_summary(sid)
                if user is None:
                    st.error("존재하지 않는 Steam ID입니다. ID를 다시 확인해주세요.")
                    return
                owned = steam.get_owned_games(sid)
                stats = recommender.compute_stats(owned)

            with st.spinner("스팀 친구 데이터 수집 중... (친구 목록 비공개 시 생략)"):
                friends_games = steam.get_friends_games(sid, max_friends=20)
                friends_count = len(friends_games)
                friends_profiles = steam.get_friends_profiles(list(friends_games.keys())) if friends_games else {}

            with st.spinner("AI 추천 생성 중..."):
                recs = _get_recs(sid, owned, friends_games)

            st.session_state.update(
                steam_id=sid, user=user, stats=stats, recs=recs,
                owned_games=owned, friends_games=friends_games,
                friends_profiles=friends_profiles,
                friends_count=friends_count, page="dashboard",
            )
            st.rerun()

    st.markdown("""
    <div style="text-align:center;color:#ffffff;font-size:0.8rem;margin-top:40px;">
        Powered by Steam API &nbsp;·&nbsp; Not affiliated with Valve Corporation.
    </div>
    """, unsafe_allow_html=True)


# ── 페이지: 대시보드 ──────────────────────────────────────────────────────────
def page_dashboard():
    _render_friends_sidebar()

    user  = st.session_state.user or {}
    stats = st.session_state.stats or {}

    avatar   = user.get("avatar_url", "")
    username = user.get("username", "Unknown")
    total_h  = stats.get("total_playtime_hours", 0)
    total_g  = stats.get("total_games", 0)

    # 프로필 헤더 — st.columns로 레이아웃 (unclosed div 없음)
    hdr_col, btn_col = st.columns([9, 1])
    with hdr_col:
        av_html = (
            f'<img src="{avatar}" style="width:70px;height:70px;border-radius:4px;'
            f'border:2px solid #E50914;margin-right:18px;vertical-align:middle;">'
        ) if avatar else ""
        st.markdown(
            f'<div style="background:#181818;padding:22px 26px;border-radius:8px;'
            f'margin-bottom:24px;display:flex;align-items:center;">'
            f'{av_html}'
            f'<div>'
            f'<h2 style="color:#fff;font-size:1.7rem;margin:0 0 4px 0;">{username} 님의 플레이 기록</h2>'
            f'<p style="color:#b3b3b3;font-size:0.95rem;margin:0;">'
            f'총 플레이타임: {total_h:,} 시간 &nbsp;·&nbsp; 보유 게임: {total_g}개'
            f'</p></div></div>',
            unsafe_allow_html=True,
        )
    with btn_col:
        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
        if st.button("로그아웃", key="logout_btn"):
            # 리뷰·가격 캐시 포함 전체 세션 초기화
            keys_to_clear = [k for k in st.session_state.keys()]
            for k in keys_to_clear:
                del st.session_state[k]
            st.session_state.page = "login"
            st.rerun()

    # 차트 — 독립적인 st.markdown 호출만 사용 (div 분할 없음)
    genre_dist = stats.get("genre_distribution", {})
    top5       = stats.get("top5_games", [])

    # ── 장르 색상 맵 (두 차트 전에 미리 빌드) ────────────────────────────────
    import colorsys as _cs

    # 자주 등장하는 장르는 명시적으로 고정 — 비슷한 계열 장르끼리 절대 겹치지 않게
    _FIXED_GENRE_COLORS: dict[str, str] = {
        # ─ 빨강 계열 ─
        "Action":         "#FF1744",  # 선명 빨강
        "Hack and Slash": "#FF6D00",  # 진한 주황-빨강
        "Racing":         "#D50000",  # 딥 레드
        # ─ 주황/노랑 계열 ─
        "Adventure":      "#FF9100",  # 주황
        "Sandbox":        "#FFAB40",  # 연한 주황
        "Battle Royale":  "#FFD600",  # 노랑 ★ 요청
        "Simulation":     "#FFF176",  # 연노랑 (밝게)
        # ─ 초록 계열: 진하기로 완전 구분 ─
        "Open World":     "#00E676",  # 밝은 민트그린
        "Survival":       "#1B5E20",  # 매우 진한 다크그린
        "Shooter":        "#76FF03",  # 형광 라임그린 (밝게)
        "Tactical":       "#1A237E",  # 딥 네이비 (완전 다른 계열로 분리)
        # ─ 파랑/하늘 계열 ─
        "FPS":            "#00B0FF",  # 하늘파랑
        "MOBA":           "#2979FF",  # 파랑
        "Co-op":          "#82B1FF",  # 연파랑
        "Sci-fi":         "#00E5FF",  # 네온 시안
        # ─ 보라/분홍 계열 ─
        "RPG":            "#651FFF",  # 딥 퍼플
        "MMORPG":         "#AA00FF",  # 네온 바이올렛
        "Strategy":       "#D500F9",  # 마젠타 퍼플
        "Horror":         "#880E4F",  # 다크 크림즌
        "Metroidvania":   "#E040FB",  # 라이트 퍼플
        "Indie":          "#FF4081",  # 핫핑크
        "Story Rich":     "#F48FB1",  # 연분홍
        # ─ 갈색/회색 계열 ─
        "Souls-like":     "#8D6E63",  # 브라운
        "Turn-Based":     "#546E7A",  # 블루그레이
        "Roguelike":      "#00897B",  # 틸 그린
        "Platformer":     "#FFD740",  # 골드옐로
    }

    def _build_genre_color_map(genre_labels: list[str]) -> dict[str, str]:
        """고정 팔레트 우선, 없는 장르만 황금각 동적 생성."""
        golden = 0.618033988749895
        hue = 0.05  # 빨강과 겹치지 않게 약간 오프셋
        result = {}
        dynamic_idx = 0
        for genre in genre_labels:
            if genre in _FIXED_GENRE_COLORS:
                result[genre] = _FIXED_GENRE_COLORS[genre]
            else:
                # 이미 사용된 hue와 너무 가까우면 건너뜀
                s, v = (0.85, 0.92) if dynamic_idx % 2 == 0 else (0.60, 0.70)
                r, g, b = _cs.hsv_to_rgb(hue % 1.0, s, v)
                result[genre] = "#{:02X}{:02X}{:02X}".format(int(r*255), int(g*255), int(b*255))
                hue += golden
                dynamic_idx += 1
        return result

    # 파이 + top5 장르를 합쳐 통합 색상 맵 생성
    pie_labels: list[str] = [g for g, _ in list(genre_dist.items())[:8]] if genre_dist else []
    top5_extra: list[str] = []
    for game in top5:
        for genre in (game.get("genres") or []):
            if genre not in pie_labels and genre not in top5_extra:
                top5_extra.append(genre)
    genre_color_map = _build_genre_color_map(pie_labels + top5_extra)

    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown('<h3 style="text-align:center;margin-bottom:10px;color:#fff;">선호하는 장르</h3>',
                    unsafe_allow_html=True)
        if genre_dist:
            items  = list(genre_dist.items())[:8]
            labels = [g for g, _ in items]
            values = [round(v["minutes"] / 60, 1) for _, v in items]
            pcts   = [v["percentage"] for _, v in items]
            colors = [genre_color_map[g] for g in labels]
            text_labels = [f"{g}<br>{p}%" for g, p in zip(labels, pcts)]

            fig = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.42,
                marker=dict(colors=colors, line=dict(color="#141414", width=2)),
                text=text_labels,
                textinfo="text",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>%{value}시간 (%{percent})<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor="#181818", plot_bgcolor="#181818",
                font=dict(color="#e5e5e5", size=11),
                margin=dict(t=40, b=40, l=60, r=60),
                showlegend=True,
                legend=dict(font=dict(color="#b3b3b3", size=11),
                            bgcolor="rgba(0,0,0,0)", orientation="v"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown('<h3 style="text-align:center;margin-bottom:10px;color:#fff;">가장 많이 플레이한 게임</h3>',
                    unsafe_allow_html=True)
        if top5:
            names = [g["name"][:22] for g in top5]

            # 각 게임의 장르를 균등 분할한 stacked horizontal bar
            # 장르가 없는 경우 단색 처리
            all_bar_genres: list[str] = []
            for game in top5:
                for genre in (game.get("genres") or ["기타"]):
                    if genre not in all_bar_genres:
                        all_bar_genres.append(genre)

            fig2 = go.Figure()
            for genre in all_bar_genres:
                x_vals = []
                for game in top5:
                    game_genres = game.get("genres") or ["기타"]
                    if genre in game_genres:
                        # 총 플레이 시간을 장르 수로 균등 분할
                        x_vals.append(round(game["playtime_hours"] / len(game_genres), 1))
                    else:
                        x_vals.append(0)
                color = genre_color_map.get(genre, "#888888")
                fig2.add_trace(go.Bar(
                    name=genre,
                    y=names,
                    x=x_vals,
                    orientation="h",
                    marker=dict(color=color),
                    hovertemplate=f"<b>%{{y}}</b><br>{genre}: %{{x}}h<extra></extra>",
                ))

            fig2.update_layout(
                barmode="stack",
                paper_bgcolor="#181818", plot_bgcolor="#181818",
                font_color="#b3b3b3",
                margin=dict(t=10, b=10, l=10, r=10),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="플레이 시간 (h)"),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", autorange="reversed"),
                legend=dict(font=dict(color="#b3b3b3", size=10),
                            bgcolor="rgba(0,0,0,0)", orientation="h",
                            yanchor="bottom", y=1.02, xanchor="left", x=0),
                showlegend=True,
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    _, btn_col, _ = st.columns([1, 1, 1])
    with btn_col:
        if st.button("맞춤 추천작 보기 ➔", key="go_recs"):
            st.session_state.page = "recommendations"
            st.rerun()


# ── 페이지: 추천 ──────────────────────────────────────────────────────────────
def page_recommendations():
    _render_friends_sidebar()

    recs     = st.session_state.recs or {}
    username = (st.session_state.user or {}).get("username", "Unknown")

    hc1, hc2 = st.columns([7, 1])
    with hc1:
        st.markdown(f"""
        <div style="border-bottom:2px solid #2f2f2f;padding-bottom:20px;margin-bottom:40px;">
            <h1 style="font-size:2.2rem;font-weight:800;">AI 맞춤 추천 게임</h1>
            <p style="color:#b3b3b3;">{username}님을 위한 맞춤 추천</p>
        </div>
        """, unsafe_allow_html=True)
    with hc2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← 통계", key="back_btn"):
            st.session_state.page = "dashboard"
            st.rerun()

    # ── 가격/할인 정보 일괄 페치 (세션 캐시) ─────────────────────────────────
    all_rec_games = (
        recs.get("genre_based", []) +
        recs.get("collab_based", []) +
        recs.get("hidden_gems", []) +
        recs.get("graph_based", [])
    )
    price_cache_key = "_price_cache"
    if price_cache_key not in st.session_state:
        st.session_state[price_cache_key] = {}
    cached_prices: dict = st.session_state[price_cache_key]

    uncached_ids = [
        g["app_id"] for g in all_rec_games
        if g.get("app_id") and g["app_id"] not in cached_prices
    ]
    if uncached_ids:
        with st.spinner("Steam 할인 정보 확인 중..."):
            fetched = steam.get_price_info_batch(list(set(uncached_ids)))
            cached_prices.update(fetched)
            # 조회 실패한 app_id도 None으로 마킹해 재시도 방지
            for aid in uncached_ids:
                cached_prices.setdefault(aid, None)
        st.session_state[price_cache_key] = cached_prices

    def _inject_price(games: list) -> list:
        for g in games:
            g["price_info"] = cached_prices.get(g.get("app_id"))
        return games

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎮 장르 기반 추천", "👥 유사 유저 기반 추천", "💎 숨겨진 명작", "🕸️ LightGCN", "📊 나 & 친구 통계"])

    with tab1:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">🎮 장르 기반 추천</h2>', unsafe_allow_html=True)
        genre_games = _inject_price(recs.get("genre_based", []))
        _render_carousel(genre_games)
        _show_reviews_panel(genre_games, "genre")

    with tab2:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">👥 유사 유저 기반 추천</h2>', unsafe_allow_html=True)
        collab_games = _inject_price(recs.get("collab_based", []))
        _render_carousel(collab_games)
        _show_reviews_panel(collab_games, "collab")

    with tab3:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">💎 숨겨진 명작</h2>', unsafe_allow_html=True)
        hidden_games = _inject_price(recs.get("hidden_gems", []))
        _render_carousel(hidden_games)
        _show_reviews_panel(hidden_games, "hidden")

    with tab4:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">🕸️ LightGCN 그래프 추천</h2>', unsafe_allow_html=True)
        st.markdown(
            '<p style="color:#b3b3b3;font-size:0.9rem;margin-bottom:16px;">'
            'Graph Neural Network (SIGIR 2020) · '
            '<span style="color:#E50914;">빨간 별</span> = 추천 게임 &nbsp;|&nbsp; '
            '<span style="color:#fff;">흰 사각형</span> = 보유 게임</p>',
            unsafe_allow_html=True,
        )
        graph_games = _inject_price(recs.get("graph_based", []))
        fig_graph = _build_lightgcn_graph(
            st.session_state.steam_id,
            st.session_state.owned_games or [],
            graph_games,
        )
        st.plotly_chart(fig_graph, use_container_width=True)
        st.markdown("---")
        _render_carousel(graph_games)
        _show_reviews_panel(graph_games, "graph")

    with tab5:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">📊 나 & 친구 통계</h2>', unsafe_allow_html=True)
        _render_stats_tab()


# ── 라우터 ────────────────────────────────────────────────────────────────────
page = st.session_state.page
if page == "login":
    page_login()
elif page == "dashboard":
    page_dashboard()
elif page == "recommendations":
    page_recommendations()
