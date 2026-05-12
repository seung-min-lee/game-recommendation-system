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
    ("selected_friend", None),
    ("genre_explorer_page", "genre_explorer"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
def _genre_vector(games: list[dict], game_catalog: dict) -> dict[str, float]:
    """플레이타임 가중 장르 벡터 반환 (L2 정규화)."""
    import math
    vec: dict[str, float] = {}
    for g in games:
        hrs = g.get("playtime_minutes", 0) / 60
        for genre in game_catalog.get(g.get("app_id"), {}).get("genres", []):
            vec[genre] = vec.get(genre, 0.0) + hrs
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {g: v / norm for g, v in vec.items()}


def _cosine_sim(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """두 장르 벡터의 코사인 유사도 (0~1)."""
    return sum(vec_a.get(g, 0.0) * vec_b.get(g, 0.0) for g in vec_a)


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
    rows = max(1, (len(games) + 3) // 4)
    components.html(html, height=rows * 330 + 40, scrolling=False)


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
            cursor:pointer; box-sizing:border-box;
            width:calc(25% - 12px); min-width:180px;
            transition:transform 0.3s,box-shadow 0.3s;
            " onmouseover="this.style.transform='scale(1.04)';this.style.boxShadow='0 12px 28px rgba(0,0,0,0.7)';this.style.zIndex='10'"
               onmouseout="this.style.transform='scale(1)';this.style.boxShadow='none';this.style.zIndex='1'">
            <img src="{img}" style="width:100%;height:130px;object-fit:cover;"
                 onerror="this.src='https://via.placeholder.com/240x130/181818/555?text=No+Image'">
            <div style="padding:12px;">
                <p style="color:#fff;font-size:0.9rem;font-weight:bold;margin:0 0 6px;
                           white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</p>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="color:#46d369;font-weight:bold;font-size:0.85rem;">{match_pct}% 일치</span>
                    {mc_html}
                </div>
                {price_html}
                <p style="color:#E50914;font-size:0.75rem;margin:5px 0 0;font-weight:bold;">스토어 이동 ➔</p>
                {reason_html}
            </div>
        </div>"""
    n = len(games)
    height = 320 * ((n + 3) // 4) + 40
    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:16px;padding:10px 0 20px;">
        {cards}
    </div>"""


# ── LightGCN 그래프 ────────────────────────────────────────────────────────────
def _build_lightgcn_graph(steam_id, owned_games, rec_games):
    from data.dummy_data import DUMMY_OWNED_GAMES, GAME_CATALOG
    import math

    all_interactions = {}
    for uid, games in DUMMY_OWNED_GAMES.items():
        all_interactions[uid] = {g["app_id"]: g.get("playtime_minutes", 1) for g in games}
    all_interactions[steam_id] = {g["app_id"]: g.get("playtime_minutes", 1) for g in owned_games}

    users     = list(all_interactions.keys())
    owned_ids = {g["app_id"] for g in owned_games}
    rec_ids   = {g["app_id"] for g in rec_games}
    rec_name_map = {g["app_id"]: g.get("name", "") for g in rec_games}

    rec_list   = sorted(rec_ids)
    other_list = sorted({aid for gs in all_interactions.values() for aid in gs} - rec_ids)

    # ── 레이아웃: x축 고정, y축 균등 분포
    n_u     = len(users)
    n_other = len(other_list)
    n_rec   = len(rec_list)

    user_pos  = {u:   (0.0, i / max(n_u - 1, 1))                        for i, u   in enumerate(users)}
    other_pos = {aid: (1.0, i / max(n_other - 1, 1))                    for i, aid in enumerate(other_list)}
    rec_pos   = {aid: (2.0, 0.1 + i * 0.80 / max(n_rec - 1, 1))        for i, aid in enumerate(rec_list)}
    game_pos  = {**other_pos, **rec_pos}

    # 최대 플레이타임 (엣지 굵기 정규화용)
    all_pt = [pt for gs in all_interactions.values() for pt in gs.values()]
    max_pt = max(all_pt) if all_pt else 1

    fig = go.Figure()

    # ── 컬럼 구분선 (배경 세로선)
    for cx in [0.5, 1.5]:
        fig.add_shape(type="line",
            x0=cx, x1=cx, y0=-0.05, y1=1.05,
            line=dict(color="rgba(255,255,255,0.06)", width=1, dash="dot"),
        )

    # ── 엣지: 타 유저 (한 trace로 묶음, 노란색)
    ox, oy = [], []
    for uid, games in all_interactions.items():
        if uid == steam_id:
            continue
        ux, uy = user_pos[uid]
        for aid, pt in games.items():
            if aid not in game_pos:
                continue
            gx, gy = game_pos[aid]
            ox += [ux, gx, None]; oy += [uy, gy, None]
    if ox:
        fig.add_trace(go.Scatter(x=ox, y=oy, mode="lines",
            line=dict(width=0.6, color="rgba(255,210,40,0.22)"),
            hoverinfo="none", showlegend=False))

    # ── 엣지: 내 보유 게임 — 플레이타임 비례 굵기로 개별 추가
    for aid, pt in all_interactions.get(steam_id, {}).items():
        if aid not in game_pos or aid in rec_ids:
            continue
        ux, uy = user_pos[steam_id]
        gx, gy = game_pos[aid]
        w = 0.8 + 3.2 * math.log1p(pt) / math.log1p(max_pt)
        alpha = 0.35 + 0.50 * pt / max_pt
        fig.add_trace(go.Scatter(
            x=[ux, gx, None], y=[uy, gy, None], mode="lines",
            line=dict(width=round(w, 1), color=f"rgba(100,180,255,{alpha:.2f})"),
            hoverinfo="none", showlegend=False,
        ))

    # ── 엣지: 내 추천 게임 — 빨강 글로우 (두꺼운 희미한 + 얇은 선명)
    for aid in rec_ids:
        if aid not in game_pos:
            continue
        ux, uy = user_pos[steam_id]
        gx, gy = game_pos[aid]
        # 글로우 레이어
        fig.add_trace(go.Scatter(
            x=[ux, gx, None], y=[uy, gy, None], mode="lines",
            line=dict(width=6, color="rgba(255,60,60,0.12)"),
            hoverinfo="none", showlegend=False,
        ))
        # 선명 레이어
        fig.add_trace(go.Scatter(
            x=[ux, gx, None], y=[uy, gy, None], mode="lines",
            line=dict(width=2, color="rgba(255,90,90,0.95)"),
            hoverinfo="none", showlegend=False,
        ))

    # ── 노드: 다른 유저 (한 trace)
    other_ux = [user_pos[u][0] for u in users if u != steam_id]
    other_uy = [user_pos[u][1] for u in users if u != steam_id]
    other_unames = [f"User_{u[-4:]}" for u in users if u != steam_id]
    other_ucounts = [len(all_interactions[u]) for u in users if u != steam_id]
    if other_ux:
        fig.add_trace(go.Scatter(
            x=other_ux, y=other_uy, mode="markers+text",
            marker=dict(size=16, color="#8888aa", symbol="circle",
                        line=dict(width=1.5, color="rgba(255,255,255,0.4)")),
            text=other_unames, textposition="middle left",
            textfont=dict(size=9, color="#aaaacc"),
            hovertext=[f"<b>{n}</b><br>보유 게임 {c}개" for n, c in zip(other_unames, other_ucounts)],
            hoverinfo="text", name="다른 유저",
        ))

    # ── 노드: 기타 게임 (내가 없는 게임, 한 trace)
    bg_gx = [other_pos[aid][0] for aid in other_list if aid not in owned_ids]
    bg_gy = [other_pos[aid][1] for aid in other_list if aid not in owned_ids]
    bg_hover = [
        f"<b>{GAME_CATALOG.get(aid,{}).get('name', f'Game_{aid}')}</b><br>"
        f"{', '.join(GAME_CATALOG.get(aid,{}).get('genres',[])[:2])}"
        for aid in other_list if aid not in owned_ids
    ]
    if bg_gx:
        fig.add_trace(go.Scatter(
            x=bg_gx, y=bg_gy, mode="markers",
            marker=dict(size=6, color="rgba(80,80,100,0.7)", symbol="circle",
                        line=dict(width=0)),
            hovertext=bg_hover, hoverinfo="text", name="기타 게임",
        ))

    # ── 노드: 내 보유 게임 (한 trace, 크기 = 플레이타임 비례)
    owned_in_other = [aid for aid in other_list if aid in owned_ids]
    if owned_in_other:
        ox2 = [other_pos[aid][0] for aid in owned_in_other]
        oy2 = [other_pos[aid][1] for aid in owned_in_other]
        sizes2 = [
            10 + 12 * math.log1p(all_interactions[steam_id].get(aid, 0)) / math.log1p(max_pt)
            for aid in owned_in_other
        ]
        hover2 = [
            f"<b>{GAME_CATALOG.get(aid,{}).get('name', f'Game_{aid}')}</b><br>"
            f"{', '.join(GAME_CATALOG.get(aid,{}).get('genres',[])[:2])}<br>"
            f"플레이 {round(all_interactions[steam_id].get(aid,0)/60)}시간"
            for aid in owned_in_other
        ]
        labels2 = [
            GAME_CATALOG.get(aid, {}).get("name", f"Game_{aid}")[:13]
            for aid in owned_in_other
        ]
        fig.add_trace(go.Scatter(
            x=ox2, y=oy2, mode="markers+text",
            marker=dict(size=sizes2, color="#5BA4FF", symbol="square",
                        line=dict(width=1.2, color="rgba(180,220,255,0.6)")),
            text=labels2, textposition="middle right",
            textfont=dict(size=8, color="#99BBFF"),
            hovertext=hover2, hoverinfo="text", name="내 보유 게임",
        ))

    # ── 노드: 추천 게임 — 글로우 효과 (외곽 큰 원 + 내부 별)
    if rec_list:
        rx2 = [rec_pos[aid][0] for aid in rec_list]
        ry2 = [rec_pos[aid][1] for aid in rec_list]
        rec_names = [
            rec_name_map.get(aid) or GAME_CATALOG.get(aid, {}).get("name") or f"Game_{aid}"
            for aid in rec_list
        ]
        rec_hover = [
            f"<b>{n}</b><br>"
            f"{', '.join(GAME_CATALOG.get(aid,{}).get('genres',[])[:3])}<br>"
            f"<span style='color:#ff9090'>⭐ 추천 게임</span>"
            for n, aid in zip(rec_names, rec_list)
        ]
        # 글로우 원
        fig.add_trace(go.Scatter(
            x=rx2, y=ry2, mode="markers",
            marker=dict(size=36, color="rgba(255,60,60,0.08)", symbol="circle",
                        line=dict(width=0)),
            hoverinfo="none", showlegend=False,
        ))
        # 별 노드
        fig.add_trace(go.Scatter(
            x=rx2, y=ry2, mode="markers+text",
            marker=dict(size=20, color="#FF4444", symbol="star",
                        line=dict(width=2, color="#FFB0B0")),
            text=[f"  {n[:20]}" for n in rec_names],
            textposition="middle right",
            textfont=dict(size=10, color="#FF9090", family="Arial"),
            hovertext=rec_hover, hoverinfo="text", name="⭐ 추천 게임",
        ))

    # ── 노드: 나 (마지막에 그려서 위에 표시)
    my_game_count = len(all_interactions.get(steam_id, {}))
    username_label = (st.session_state.user or {}).get("username", "나")
    ux0, uy0 = user_pos[steam_id]
    # 글로우
    fig.add_trace(go.Scatter(
        x=[ux0], y=[uy0], mode="markers",
        marker=dict(size=50, color="rgba(229,9,20,0.10)", symbol="circle", line=dict(width=0)),
        hoverinfo="none", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[ux0], y=[uy0], mode="markers+text",
        marker=dict(size=28, color="#E50914", symbol="circle",
                    line=dict(width=2.5, color="white")),
        text=[f"  {username_label}"],
        textposition="middle right",
        textfont=dict(size=13, color="#FF6666", family="Arial Black"),
        hovertext=f"<b>{username_label}</b><br>보유 게임 {my_game_count}개",
        hoverinfo="text", name="나",
    ))

    # ── 열 헤더 annotation
    col_annots = [
        dict(x=0.0,  y=1.06, text="<b>유저</b>",            font=dict(size=13, color="#aaaacc")),
        dict(x=0.5,  y=1.06, text="<b>보유 · 기타 게임</b>", font=dict(size=13, color="#88aaff")),
        dict(x=1.0,  y=1.06, text="<b>⭐ 추천 게임</b>",     font=dict(size=13, color="#FF8888")),
    ]
    annotations = [
        dict(**a, xref="paper", yref="paper", showarrow=False)
        for a in col_annots
    ]

    fig.update_layout(
        paper_bgcolor="#0e0e0e",
        plot_bgcolor="#111111",
        font_color="#e5e5e5",
        height=720,
        margin=dict(l=160, r=220, t=50, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.5, 2.85]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.08, 1.12]),
        legend=dict(
            bgcolor="rgba(20,20,20,0.92)", bordercolor="#333", borderwidth=1,
            font=dict(color="#ccc", size=11), itemsizing="constant",
            x=1.02, y=0.98,
        ),
        hoverlabel=dict(bgcolor="#1a1a2e", font_color="#fff", bordercolor="#555"),
        annotations=annotations,
    )
    return fig


# ── 친구 1:1 비교 패널 ───────────────────────────────────────────────────────
def _render_friend_comparison(fid: str):
    from data.dummy_data import GAME_CATALOG

    owned_games      = st.session_state.get("owned_games", [])
    friends_games    = st.session_state.get("friends_games", {})
    friends_profiles = st.session_state.get("friends_profiles", {})
    username         = (st.session_state.get("user") or {}).get("username", "나")

    f_games  = friends_games.get(fid, [])
    profile  = friends_profiles.get(fid, {})
    fname    = profile.get("username", f"User_{fid[-4:]}")
    favatar  = profile.get("avatar_url", "")

    def _genre_hours(games):
        res: dict[str, float] = {}
        for g in games:
            hrs = g.get("playtime_minutes", 0) / 60
            for genre in GAME_CATALOG.get(g.get("app_id"), {}).get("genres", []):
                res[genre] = res.get(genre, 0) + hrs
        return res

    my_gh  = _genre_hours(owned_games)
    f_gh   = _genre_hours(f_games)
    my_total = sum(g.get("playtime_minutes", 0) for g in owned_games) / 60
    f_total  = sum(g.get("playtime_minutes", 0) for g in f_games) / 60

    my_ids = {g["app_id"] for g in owned_games}
    f_ids  = {g["app_id"] for g in f_games}
    common_ids = my_ids & f_ids

    # 코사인 유사도 (플레이타임 가중)
    my_vec = _genre_vector(owned_games, GAME_CATALOG)
    f_vec  = _genre_vector(f_games,     GAME_CATALOG)
    sim = int(_cosine_sim(my_vec, f_vec) * 100)
    sim_clr = "#46d369" if sim >= 70 else "#f5c518" if sim >= 40 else "#b3b3b3"

    # ── 헤더
    fav_html = f'<img src="{favatar}" style="width:40px;height:40px;border-radius:50%;border:2px solid {sim_clr};margin-right:10px;vertical-align:middle;">' if favatar else "👤 "
    st.markdown(f"""
    <div style="background:#1e1e1e;border-radius:12px;padding:18px 22px;margin-bottom:20px;
                border:1px solid #2f2f2f;display:flex;align-items:center;gap:16px;">
        <div style="font-size:1.1rem;font-weight:700;color:#fff;">👤 {username}</div>
        <div style="color:#555;font-size:1.4rem;">vs</div>
        <div style="display:flex;align-items:center;">{fav_html}
            <span style="font-size:1.1rem;font-weight:700;color:#fff;">{fname}</span>
        </div>
        <div style="margin-left:auto;text-align:right;">
            <div style="font-size:0.75rem;color:#737373;">장르 유사도</div>
            <div style="font-size:1.6rem;font-weight:800;color:{sim_clr};">{sim}%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 요약 카드 4개
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("내 총 플레이타임",   f"{my_total:,.0f}h",    "#E50914"),
        (f"{fname} 플레이타임", f"{f_total:,.0f}h",    "#64A0FF"),
        ("내 보유 게임",        f"{len(owned_games)}개", "#46d369"),
        ("공통 보유 게임",      f"{len(common_ids)}개",  sim_clr),
    ]
    for col, (title, val, clr) in zip([c1, c2, c3, c4], cards):
        with col:
            st.markdown(f"""
            <div style="background:#1a1a1a;border-radius:10px;padding:14px;text-align:center;
                        border-top:3px solid {clr};margin-bottom:12px;">
                <div style="color:#737373;font-size:0.75rem;">{title}</div>
                <div style="font-size:1.5rem;font-weight:800;color:#fff;">{val}</div>
            </div>""", unsafe_allow_html=True)

    # ── 레이더 차트 (장르 비교)
    all_genres = sorted(
        (set(my_gh) | set(f_gh)),
        key=lambda g: my_gh.get(g, 0) + f_gh.get(g, 0), reverse=True
    )[:10]

    def _norm(gh, genres):
        vals = [gh.get(g, 0) for g in genres]
        mx = max(vals) or 1
        return [round(v / mx * 100) for v in vals]

    my_v = _norm(my_gh,  all_genres)
    f_v  = _norm(f_gh,   all_genres)

    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=my_v + [my_v[0]], theta=all_genres + [all_genres[0]],
        fill="toself", name=f"👤 {username}",
        line=dict(color="#E50914", width=2.5),
        fillcolor="rgba(229,9,20,0.15)",
    ))
    fig_radar.add_trace(go.Scatterpolar(
        r=f_v + [f_v[0]], theta=all_genres + [all_genres[0]],
        fill="toself", name=fname,
        line=dict(color="#64A0FF", width=2),
        fillcolor="rgba(100,160,255,0.12)",
    ))
    fig_radar.update_layout(
        polar=dict(
            bgcolor="#141414",
            radialaxis=dict(visible=True, range=[0, 100],
                            gridcolor="rgba(255,255,255,0.08)",
                            tickfont=dict(size=8, color="#555"), ticksuffix="%"),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.1)",
                             tickfont=dict(size=11, color="#ccc")),
        ),
        paper_bgcolor="#141414", font_color="#e5e5e5",
        height=380, margin=dict(l=50, r=50, t=30, b=30),
        legend=dict(bgcolor="rgba(20,20,20,0.9)", bordercolor="#333",
                    borderwidth=1, font=dict(size=11)),
    )

    # ── 플레이타임 비교 바 차트 (공통 게임 상위 10개)
    common_game_list = []
    my_pt  = {g["app_id"]: g.get("playtime_minutes", 0) for g in owned_games}
    f_pt   = {g["app_id"]: g.get("playtime_minutes", 0) for g in f_games}
    for aid in sorted(common_ids, key=lambda a: my_pt.get(a, 0) + f_pt.get(a, 0), reverse=True)[:10]:
        name = GAME_CATALOG.get(aid, {}).get("name", f"Game_{aid}")
        common_game_list.append({
            "name": name[:22],
            "my_h": round(my_pt.get(aid, 0) / 60, 1),
            "f_h":  round(f_pt.get(aid, 0) / 60, 1),
        })

    left, right = st.columns([1, 1])
    with left:
        st.markdown(f'<h3 style="font-size:1rem;color:#ccc;margin-bottom:8px;">🎯 장르 취향 비교</h3>', unsafe_allow_html=True)
        st.plotly_chart(fig_radar, use_container_width=True)

    with right:
        st.markdown(f'<h3 style="font-size:1rem;color:#ccc;margin-bottom:8px;">🎮 공통 게임 플레이타임 비교 (상위 10개)</h3>', unsafe_allow_html=True)
        if common_game_list:
            names  = [g["name"] for g in common_game_list]
            my_hrs = [g["my_h"] for g in common_game_list]
            f_hrs  = [g["f_h"]  for g in common_game_list]
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                name=f"👤 {username}", y=names, x=my_hrs, orientation="h",
                marker=dict(color="#E50914"), offsetgroup=0,
                hovertemplate="<b>%{y}</b><br>" + username + ": %{x}h<extra></extra>",
            ))
            fig_bar.add_trace(go.Bar(
                name=fname, y=names, x=f_hrs, orientation="h",
                marker=dict(color="#64A0FF"), offsetgroup=1,
                hovertemplate="<b>%{y}</b><br>" + fname + ": %{x}h<extra></extra>",
            ))
            fig_bar.update_layout(
                barmode="group",
                paper_bgcolor="#141414", plot_bgcolor="#141414",
                font_color="#b3b3b3", height=380,
                margin=dict(l=10, r=20, t=10, b=10),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="플레이타임 (h)"),
                yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                legend=dict(bgcolor="rgba(20,20,20,0.9)", bordercolor="#333",
                            borderwidth=1, font=dict(size=11),
                            orientation="h", yanchor="bottom", y=1.02, x=0),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.markdown('<p style="color:#737373;padding-top:60px;text-align:center;">공통 보유 게임이 없습니다.</p>', unsafe_allow_html=True)

    # ── 공통 게임 목록 (썸네일)
    if common_ids:
        st.markdown(f'<h3 style="font-size:1rem;color:#ccc;margin:12px 0 10px;">🔗 공통 보유 게임 ({len(common_ids)}개)</h3>', unsafe_allow_html=True)
        cols = st.columns(6)
        for i, aid in enumerate(sorted(common_ids)[:12]):
            info = GAME_CATALOG.get(aid, {})
            name = info.get("name", f"Game_{aid}")
            img  = info.get("header_image", f"https://cdn.akamai.steamstatic.com/steam/apps/{aid}/header.jpg")
            url  = info.get("store_url", f"https://store.steampowered.com/app/{aid}")
            with cols[i % 6]:
                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none;">
                    <div style="border-radius:6px;overflow:hidden;margin-bottom:8px;
                                border:1px solid #2f2f2f;transition:border-color 0.2s;"
                         onmouseover="this.style.borderColor='#E50914'"
                         onmouseout="this.style.borderColor='#2f2f2f'">
                        <img src="{img}" style="width:100%;display:block;">
                        <div style="padding:4px 6px;background:#1a1a1a;font-size:0.7rem;
                                    color:#b3b3b3;white-space:nowrap;overflow:hidden;
                                    text-overflow:ellipsis;">{name}</div>
                    </div>
                </a>""", unsafe_allow_html=True)


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

    # 코사인 유사도 계산 후 상위 5명
    my_vec = _genre_vector(owned_games, GAME_CATALOG)
    ranked = sorted(
        friends_games.items(),
        key=lambda kv: -_cosine_sim(my_vec, _genre_vector(kv[1], GAME_CATALOG))
    )[:5]

    # ── 장르 레이더 차트 (나 + 친구들)
    all_genres = sorted(
        {g for kv in ranked for game in kv[1]
         for g in GAME_CATALOG.get(game.get("app_id"), {}).get("genres", [])}
        | set(my_genre_hrs),
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
        margin=dict(l=50, r=60, t=40, b=10),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        yaxis=dict(
            title=dict(text="공통 게임 수", font=dict(color="#46d369")),
            tickfont=dict(color="#46d369"),
            gridcolor="rgba(255,255,255,0.05)",
        ),
        yaxis2=dict(
            title=dict(text="플레이타임 (h)", font=dict(color="#64A0FF")),
            tickfont=dict(color="#64A0FF"),
            overlaying="y", side="right",
            gridcolor="rgba(0,0,0,0)",
        ),
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

        my_vec_sb = _genre_vector(owned_games, GAME_CATALOG)

        for fid, f_games in sorted(
            friends_games.items(),
            key=lambda kv: -_cosine_sim(my_vec_sb, _genre_vector(kv[1], GAME_CATALOG)),
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

            # 코사인 유사도 (플레이타임 가중)
            f_vec_sb = _genre_vector(f_games, GAME_CATALOG)
            sim      = int(_cosine_sim(my_vec_sb, f_vec_sb) * 100)

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

            is_selected = st.session_state.get("selected_friend") == fid
            card_bg     = "#252525" if is_selected else "#1a1a1a"
            arrow_clr   = "#64A0FF" if is_selected else "#555"

            # 이름 행: 아바타+이름(좌) / →버튼(우)
            name_col, arrow_col = st.columns([5, 1])
            with name_col:
                st.markdown(f"""
                <div style="padding:10px 10px 0 10px;background:{card_bg};
                            border-radius:8px 8px 0 0;border-left:3px solid {clr};
                            display:flex;align-items:center;">
                    {av_html}<span style="font-weight:bold;font-size:0.86rem;color:#fff;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100px;">{username}</span>
                </div>
                """, unsafe_allow_html=True)
            with arrow_col:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                if st.button("→" if not is_selected else "✕", key=f"stat_btn_{fid}",
                             help="통계 비교 보기"):
                    st.session_state.selected_friend = None if is_selected else fid
                    st.rerun()

            # 나머지 카드 본문
            st.markdown(f"""
            <div style="margin-bottom:10px;padding:6px 12px 10px 12px;background:{card_bg};
                        border-radius:0 0 8px 8px;border-left:3px solid {clr};">
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

    # ── 친구 1:1 비교 패널 (사이드바에서 친구 선택 시 표시)
    selected_fid = st.session_state.get("selected_friend")
    friends_games = st.session_state.get("friends_games", {})
    if selected_fid and selected_fid in friends_games:
        fname = st.session_state.get("friends_profiles", {}).get(
            selected_fid, {}
        ).get("username", f"User_{selected_fid[-4:]}")
        st.markdown("---")
        st.markdown(
            f'<h2 style="font-size:1.4rem;padding-left:10px;border-left:4px solid #64A0FF;margin-bottom:16px;">'
            f'📊 나 vs {fname} 비교</h2>',
            unsafe_allow_html=True,
        )
        _render_friend_comparison(selected_fid)

    # ── 나 & 친구 통계 (로그인 직후 바로 노출)
    st.markdown("---")
    st.markdown('<h2 style="font-size:1.4rem;padding-left:10px;border-left:4px solid #E50914;margin-bottom:16px;">📊 나 & 친구 통계</h2>', unsafe_allow_html=True)
    _render_stats_tab()

    st.markdown("<br>", unsafe_allow_html=True)
    _, btn_col, _ = st.columns([1, 1, 1])
    with btn_col:
        if st.button("맞춤 추천작 보기 ➔", key="go_recs", use_container_width=True):
            st.session_state.page = "recommendations"
            st.rerun()


# ── 페이지: 추천 ──────────────────────────────────────────────────────────────
def page_recommendations():
    _render_friends_sidebar()

    recs     = st.session_state.recs or {}
    username = (st.session_state.user or {}).get("username", "Unknown")

    hc1, hc2 = st.columns([8, 1])
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎮 장르 기반 추천", "👥 유사 유저 기반 추천", "💎 숨겨진 명작", "🕸️ LightGCN", "🎯 장르별 탐색"])

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

        graph_games = _inject_price(recs.get("graph_based", []))
        _render_carousel(graph_games)
        _show_reviews_panel(graph_games, "graph")

        st.markdown("---")
        with st.expander("🔬 그래프 시각화", expanded=False):
            viz_mode = st.radio(
                "시각화 방식",
                ["🕸️ 이분 그래프", "🧭 t-SNE 임베딩", "🗺️ UMAP 임베딩"],
                horizontal=True,
                key="lgcn_viz_mode",
                label_visibility="collapsed",
            )
            st.markdown("<br>", unsafe_allow_html=True)

            if viz_mode == "🕸️ 이분 그래프":
                st.markdown(
                    '<p style="color:#b3b3b3;font-size:0.85rem;margin-bottom:10px;">'
                    'Graph Neural Network (SIGIR 2020) &nbsp;·&nbsp; '
                    '<span style="color:#FF6666;">★ 빨간 별</span> = 추천 게임 &nbsp;|&nbsp; '
                    '<span style="color:#88AAFF;">■ 파란 사각형</span> = 내 보유 게임 &nbsp;|&nbsp; '
                    '<span style="color:#FFDD44;">— 노란선</span> = 타 유저 연결</p>',
                    unsafe_allow_html=True,
                )
                fig_graph = _build_lightgcn_graph(
                    st.session_state.steam_id,
                    st.session_state.owned_games or [],
                    graph_games,
                )
                st.plotly_chart(fig_graph, use_container_width=True)

            else:
                algo = "umap" if "UMAP" in viz_mode else "tsne"
                _render_embedding_viz(algo, {g["app_id"] for g in graph_games})

    with tab5:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">🎯 장르별 인기 게임 탐색</h2>', unsafe_allow_html=True)
        _render_genre_explorer_inline()




# ── 임베딩 시각화 (t-SNE / UMAP 공용) ───────────────────────────────────────
def _render_embedding_viz(algo: str, rec_ids: set):
    """
    algo: "tsne" | "umap"
    rec_ids: 현재 추천 게임 app_id 집합 — 강조 표시용
    """
    from data.dummy_data import DUMMY_OWNED_GAMES, GAME_CATALOG
    import numpy as np
    import pandas as pd

    GENRE_COLOR = {
        "Action": "#E50914", "RPG": "#46d369", "FPS": "#1db954",
        "Shooter": "#2ecc71", "Adventure": "#3498db", "Strategy": "#9b59b6",
        "Simulation": "#f39c12", "Sports": "#e67e22", "Horror": "#7f8c8d",
        "Indie": "#1abc9c", "MOBA": "#e74c3c", "Survival": "#d35400",
        "Puzzle": "#16a085", "Platformer": "#8e44ad", "Fighting": "#c0392b",
        "Racing": "#2980b9", "Sandbox": "#27ae60", "Souls-like": "#c0392b",
        "Open World": "#2471a3", "Multiplayer": "#1a5276",
    }

    owned_games = st.session_state.owned_games or []
    steam_id    = st.session_state.steam_id or "me"
    username    = (st.session_state.user or {}).get("username", "나")
    owned_ids   = {g["app_id"] for g in owned_games}

    algo_label = "UMAP" if algo == "umap" else "t-SNE"
    st.markdown(
        f'<p style="color:#b3b3b3;font-size:0.85rem;margin-bottom:10px;">'
        f'<b style="color:#fff;">{algo_label}</b>로 유저·게임 임베딩을 2D에 투영합니다. '
        f'취향이 비슷할수록 가까이 모이고, '
        f'<span style="color:#FF6666;">⭐ 빨간 별</span>은 현재 추천 게임입니다.</p>',
        unsafe_allow_html=True,
    )

    # ── 장르 목록 & 인덱스 ────────────────────────────────────────────────────
    all_genres = sorted({g for info in GAME_CATALOG.values() for g in info.get("genres", [])})
    g_idx = {g: i for i, g in enumerate(all_genres)}
    dim = len(all_genres)

    # ── 유저 임베딩 ───────────────────────────────────────────────────────────
    dummy_names = {
        "76561198000000001": "GameMaster_KR",
        "76561198000000002": "ProGamer_Seoul",
        "76561198000000003": "IndieHunter",
        "76561198000000004": "RPGAddict_KR",
        "76561198000000005": "SurvivalKing",
    }
    all_users = {steam_id: owned_games, **DUMMY_OWNED_GAMES}
    user_names_map = {steam_id: f"⭐ {username}", **dummy_names}

    user_rows, user_labels, user_hovers = [], [], []
    for uid, games in all_users.items():
        vec = [0.0] * dim
        for g in games:
            hrs = g.get("playtime_minutes", 0) / 60
            for genre in GAME_CATALOG.get(g.get("app_id"), {}).get("genres", []):
                if genre in g_idx:
                    vec[g_idx[genre]] += hrs
        norm = (sum(v * v for v in vec) ** 0.5) or 1.0
        vec = [v / norm for v in vec]
        user_rows.append(vec)
        uname = user_names_map.get(uid, uid[-6:])
        user_labels.append(uname)
        total_hrs = round(sum(g.get("playtime_minutes", 0) for g in games) / 60)
        top3 = sorted(
            ((genre, sum(g.get("playtime_minutes", 0) / 60 for g in games
                         if genre in GAME_CATALOG.get(g.get("app_id"), {}).get("genres", [])))
             for genre in all_genres),
            key=lambda x: -x[1],
        )[:3]
        g_str = " · ".join(f"{gn}({round(gh)}h)" for gn, gh in top3 if gh > 0)
        user_hovers.append(f"<b>{uname}</b><br>총 {total_hrs}시간<br>{g_str}")

    # ── 게임 임베딩 ───────────────────────────────────────────────────────────
    game_ids, game_rows, game_labels, game_hovers = [], [], [], []
    game_colors, game_sizes, game_symbols = [], [], []

    for app_id, info in GAME_CATALOG.items():
        genres = info.get("genres", [])
        if not genres:
            continue
        vec = [0.0] * dim
        for genre in genres:
            if genre in g_idx:
                vec[g_idx[genre]] = 1.0
        mc = info.get("metacritic") or 0
        w = (mc / 100.0) if mc else 0.5
        vec = [v * w for v in vec]
        norm = (sum(v * v for v in vec) ** 0.5) or 1.0
        vec = [v / norm for v in vec]

        game_ids.append(app_id)
        game_rows.append(vec)
        game_labels.append(info["name"])
        mc_str   = f"MC {mc}" if mc else "MC -"
        price    = info.get("price", 0)
        p_str    = "무료" if price == 0 else f"₩{price:,}"
        is_rec   = app_id in rec_ids
        is_owned = app_id in owned_ids
        tag = " 🔴추천" if is_rec else (" 🔵보유" if is_owned else "")
        game_hovers.append(
            f"<b>{info['name']}</b>{tag}<br>{', '.join(genres[:3])}<br>{mc_str} · {p_str}"
        )
        if is_rec:
            game_colors.append("#FF4444")
            game_sizes.append(18)
            game_symbols.append("star")
        elif is_owned:
            game_colors.append("#5BA4FF")
            game_sizes.append(13)
            game_symbols.append("square")
        else:
            game_colors.append(GENRE_COLOR.get(genres[0], "#888"))
            game_sizes.append(8 + min(mc // 12, 6) if mc else 8)
            game_symbols.append("circle")

    # ── PCA → 차원 축소 ───────────────────────────────────────────────────────
    n_users  = len(user_rows)
    all_vecs = np.array(user_rows + game_rows, dtype=np.float32)
    cache_key = f"_embed_{algo}_cache"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = None

    if st.session_state[cache_key] is None:
        spinner_msg = "UMAP 임베딩 계산 중..." if algo == "umap" else "t-SNE 임베딩 계산 중..."
        with st.spinner(f"{spinner_msg} (최초 1회)"):
            try:
                from sklearn.decomposition import PCA
                n_comp  = min(15, all_vecs.shape[1], all_vecs.shape[0] - 1)
                reduced = PCA(n_components=n_comp).fit_transform(all_vecs)

                if algo == "umap":
                    import umap
                    coords = umap.UMAP(
                        n_components=2, n_neighbors=8, min_dist=0.3,
                        random_state=42, metric="cosine",
                    ).fit_transform(reduced)
                else:
                    from sklearn.manifold import TSNE
                    perp   = min(15, len(reduced) - 1)
                    coords = TSNE(
                        n_components=2, perplexity=perp,
                        random_state=42, max_iter=1000,
                    ).fit_transform(reduced)

                st.session_state[cache_key] = coords
            except ImportError as e:
                pkg = "umap-learn" if algo == "umap" else "scikit-learn"
                st.error(f"`{pkg}` 패키지가 필요합니다: {e}")
                return

    coords = st.session_state[cache_key]
    if coords is None:
        return

    # ── Plotly 시각화 ─────────────────────────────────────────────────────────
    fig = go.Figure()

    # 일반 게임 (추천·보유 아닌 것)
    norm_idx = [i for i, aid in enumerate(game_ids)
                if aid not in rec_ids and aid not in owned_ids]
    if norm_idx:
        fig.add_trace(go.Scatter(
            x=[coords[n_users + i, 0] for i in norm_idx],
            y=[coords[n_users + i, 1] for i in norm_idx],
            mode="markers",
            marker=dict(
                size=[game_sizes[i] for i in norm_idx],
                color=[game_colors[i] for i in norm_idx],
                opacity=0.6, line=dict(width=0.3, color="#111"),
            ),
            hovertext=[game_hovers[i] for i in norm_idx],
            hoverinfo="text", name="게임",
        ))

    # 내 보유 게임
    own_idx = [i for i, aid in enumerate(game_ids) if aid in owned_ids and aid not in rec_ids]
    if own_idx:
        fig.add_trace(go.Scatter(
            x=[coords[n_users + i, 0] for i in own_idx],
            y=[coords[n_users + i, 1] for i in own_idx],
            mode="markers+text",
            marker=dict(size=[game_sizes[i] for i in own_idx], symbol="square",
                        color="#5BA4FF", opacity=0.85,
                        line=dict(width=1, color="rgba(180,220,255,0.5)")),
            text=[game_labels[i][:12] for i in own_idx],
            textposition="top center",
            textfont=dict(size=8, color="#99BBFF"),
            hovertext=[game_hovers[i] for i in own_idx],
            hoverinfo="text", name="내 보유 게임",
        ))

    # 추천 게임 (글로우 + 별)
    rec_idx = [i for i, aid in enumerate(game_ids) if aid in rec_ids]
    if rec_idx:
        # 글로우
        fig.add_trace(go.Scatter(
            x=[coords[n_users + i, 0] for i in rec_idx],
            y=[coords[n_users + i, 1] for i in rec_idx],
            mode="markers",
            marker=dict(size=38, color="rgba(255,60,60,0.10)",
                        symbol="circle", line=dict(width=0)),
            hoverinfo="none", showlegend=False,
        ))
        # 별
        fig.add_trace(go.Scatter(
            x=[coords[n_users + i, 0] for i in rec_idx],
            y=[coords[n_users + i, 1] for i in rec_idx],
            mode="markers+text",
            marker=dict(size=20, symbol="star", color="#FF4444",
                        line=dict(width=2, color="#FFB0B0")),
            text=[f"  {game_labels[i][:16]}" for i in rec_idx],
            textposition="middle right",
            textfont=dict(size=10, color="#FF9090"),
            hovertext=[game_hovers[i] for i in rec_idx],
            hoverinfo="text", name="⭐ 추천 게임",
        ))

    # 다른 유저
    other_idx = [i for i, uid in enumerate(all_users) if uid != steam_id]
    if other_idx:
        fig.add_trace(go.Scatter(
            x=[coords[i, 0] for i in other_idx],
            y=[coords[i, 1] for i in other_idx],
            mode="markers+text",
            marker=dict(size=20, symbol="star", color="#f5c518",
                        line=dict(width=1.5, color="#fff")),
            text=[user_labels[i] for i in other_idx],
            textposition="top center",
            textfont=dict(size=10, color="#f5c518"),
            hovertext=[user_hovers[i] for i in other_idx],
            hoverinfo="text", name="다른 유저",
        ))

    # 나
    me_idx = [i for i, uid in enumerate(all_users) if uid == steam_id]
    if me_idx:
        mi = me_idx[0]
        fig.add_trace(go.Scatter(
            x=[coords[mi, 0]], y=[coords[mi, 1]], mode="markers",
            marker=dict(size=48, color="rgba(229,9,20,0.12)",
                        symbol="circle", line=dict(width=0)),
            hoverinfo="none", showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=[coords[mi, 0]], y=[coords[mi, 1]], mode="markers+text",
            marker=dict(size=30, symbol="star", color="#E50914",
                        line=dict(width=2.5, color="white")),
            text=[f"  {user_labels[mi]}"],
            textposition="middle right",
            textfont=dict(size=13, color="#FF6666", family="Arial Black"),
            hovertext=[user_hovers[mi]], hoverinfo="text", name="나",
        ))

    # 장르 범례
    shown: set = set()
    for i, aid in enumerate(game_ids):
        if aid in rec_ids or aid in owned_ids:
            continue
        g0 = GAME_CATALOG.get(aid, {}).get("genres", [""])[0]
        if g0 and g0 not in shown:
            shown.add(g0)
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=9, color=GENRE_COLOR.get(g0, "#888")),
                name=g0, showlegend=True,
            ))

    fig.update_layout(
        height=700,
        paper_bgcolor="#0e0e0e", plot_bgcolor="#111",
        font=dict(color="#ccc"),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        legend=dict(bgcolor="#1a1a1a", bordercolor="#333", borderwidth=1,
                    font=dict(size=10), itemsizing="constant", x=1.01, y=1),
        hoverlabel=dict(bgcolor="#1a1a2e", font_color="#fff", bordercolor="#555"),
        margin=dict(l=10, r=190, t=30, b=10),
        title=dict(
            text=f"{'🗺️ UMAP' if algo == 'umap' else '🧭 t-SNE'} — 가까울수록 취향이 비슷함",
            font=dict(size=14, color="#ccc"), x=0.01,
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 유저 유사도 테이블 ────────────────────────────────────────────────────
    st.markdown("##### 🎯 나와 취향이 비슷한 유저 순위")
    my_vec = _genre_vector(owned_games, GAME_CATALOG)
    rows = []
    for uid, games in DUMMY_OWNED_GAMES.items():
        fv  = _genre_vector(games, GAME_CATALOG)
        sim = round(_cosine_sim(my_vec, fv) * 100, 1)
        top3 = sorted(fv.items(), key=lambda x: -x[1])[:3]
        rows.append({
            "유저": dummy_names.get(uid, uid[-6:]),
            "유사도": f"{sim}%",
            "주요 장르": " · ".join(g for g, _ in top3),
            "보유 게임": len(games),
        })
    rows.sort(key=lambda r: -float(r["유사도"].replace("%", "")))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── 장르 탐색 공통 렌더러 (탭 내 인라인용) ─────────────────────────────────────
def _render_genre_explorer_inline():
    from data.popular_games import POPULAR_GAMES, ALL_GENRES

    selected = st.pills(
        "장르 선택 (복수 선택 가능 · 선택한 장르를 모두 포함한 게임만 표시)",
        ALL_GENRES,
        selection_mode="multi",
        key="genre_pills_inline",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    if not selected:
        st.markdown('<p style="color:#737373;font-size:0.9rem;">장르를 선택하면 해당 조건의 게임만 표시됩니다. 현재는 전체 인기작을 보여줍니다.</p>', unsafe_allow_html=True)
        matched = sorted(POPULAR_GAMES.values(), key=lambda g: g["rank"])[:24]
    else:
        selected_set = set(selected)
        matched = sorted(
            [g for g in POPULAR_GAMES.values() if selected_set.issubset(set(g["genres"]))],
            key=lambda g: g["rank"],
        )

    if selected and not matched:
        st.markdown(f"""
        <div style="background:#1a1a1a;border-radius:10px;padding:32px;text-align:center;">
            <div style="font-size:2rem;margin-bottom:12px;">🔍</div>
            <p style="color:#b3b3b3;">선택한 장르 <b style="color:#fff;">{'  +  '.join(selected)}</b>를 모두 포함하는 게임이 없습니다.<br>
            <span style="color:#737373;font-size:0.85rem;">장르 조합을 바꿔보세요.</span></p>
        </div>
        """, unsafe_allow_html=True)
        return

    tag_html = " ".join(
        f'<span style="background:#E50914;color:#fff;border-radius:4px;padding:2px 8px;font-size:0.8rem;font-weight:600;">{g}</span>'
        for g in (selected or ["전체"])
    )
    st.markdown(
        f'<div style="margin-bottom:16px;">{tag_html} '
        f'<span style="color:#737373;font-size:0.85rem;margin-left:6px;">— {len(matched[:24])}개 게임</span></div>',
        unsafe_allow_html=True,
    )

    # popular_games 데이터 → carousel 형식으로 변환
    price_key = "_genre_price_cache"
    if price_key not in st.session_state:
        st.session_state[price_key] = {}
    cached: dict = st.session_state[price_key]
    display_raw = matched[:24]
    uncached_ids = [
        int(g["store_url"].split("/app/")[1].split("/")[0])
        for g in display_raw
        if int(g["store_url"].split("/app/")[1].split("/")[0]) not in cached
    ]
    if uncached_ids:
        with st.spinner("Steam 가격 정보 확인 중..."):
            fetched = steam.get_price_info_batch(list(set(uncached_ids)))
            cached.update(fetched)
            for aid in uncached_ids:
                cached.setdefault(aid, None)
        st.session_state[price_key] = cached

    carousel_games = [
        {
            "app_id":       int(g["store_url"].split("/app/")[1].split("/")[0]),
            "name":         g["name"],
            "header_image": g["header_image"],
            "store_url":    g["store_url"],
            "genres":       g["genres"],
            "match_percent": 100 - g["rank"],   # 인기 순위를 역산해 일치도 표시
            "metacritic":   None,
            "reason":       f"인기 순위 #{g['rank']} · {', '.join(g['genres'][:2])}",
            "price_info":   cached.get(int(g["store_url"].split("/app/")[1].split("/")[0])),
        }
        for g in display_raw
    ]

    _render_carousel(carousel_games)
    st.markdown("---")
    _show_reviews_panel(carousel_games, "genre_explore")


# ── 페이지: 장르 탐색 ──────────────────────────────────────────────────────────
def page_genre_explorer():
    from data.popular_games import POPULAR_GAMES, ALL_GENRES

    # 헤더
    hc1, hc2 = st.columns([8, 1])
    with hc1:
        st.markdown("""
        <div style="border-bottom:2px solid #2f2f2f;padding-bottom:16px;margin-bottom:24px;">
            <h1 style="font-size:2rem;font-weight:800;">🎯 장르별 인기 게임 탐색</h1>
            <p style="color:#b3b3b3;">원하는 장르를 선택하면 조건에 맞는 Steam 인기작을 추천해드립니다.</p>
        </div>
        """, unsafe_allow_html=True)
    with hc2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← 홈", key="back_genre"):
            st.session_state.page = "dashboard"
            st.rerun()

    # 장르 다중 선택 (pills)
    selected = st.pills(
        "장르 선택 (복수 선택 가능 · 선택한 장르를 모두 포함한 게임만 표시)",
        ALL_GENRES,
        selection_mode="multi",
        key="genre_pills",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    if not selected:
        # 장르 미선택: 전체 인기 순 Top 12
        st.markdown('<p style="color:#737373;font-size:0.9rem;">장르를 선택하면 해당 조건의 게임만 표시됩니다. 현재는 전체 인기작을 보여줍니다.</p>', unsafe_allow_html=True)
        matched = sorted(POPULAR_GAMES.values(), key=lambda g: g["rank"])[:12]
    else:
        selected_set = set(selected)
        matched = sorted(
            [g for g in POPULAR_GAMES.values() if selected_set.issubset(set(g["genres"]))],
            key=lambda g: g["rank"],
        )

    if selected and not matched:
        st.markdown(f"""
        <div style="background:#1a1a1a;border-radius:10px;padding:32px;text-align:center;margin-top:8px;">
            <div style="font-size:2rem;margin-bottom:12px;">🔍</div>
            <p style="color:#b3b3b3;font-size:1rem;">
                선택한 장르 <b style="color:#fff;">{'  +  '.join(selected)}</b> 를 모두 포함하는 게임이 없습니다.<br>
                <span style="color:#737373;font-size:0.85rem;">장르 조합을 바꿔보세요.</span>
            </p>
        </div>
        """, unsafe_allow_html=True)
        return

    # 결과 헤더
    tag_html = " ".join(
        f'<span style="background:#E50914;color:#fff;border-radius:4px;padding:2px 8px;font-size:0.8rem;font-weight:600;">{g}</span>'
        for g in (selected or ["전체"])
    )
    st.markdown(
        f'<div style="margin-bottom:16px;">{tag_html} '
        f'<span style="color:#737373;font-size:0.85rem;margin-left:6px;">— {len(matched[:24])}개 게임</span></div>',
        unsafe_allow_html=True,
    )

    # 가격 캐시 (세션)
    price_key = "_genre_price_cache"
    if price_key not in st.session_state:
        st.session_state[price_key] = {}
    cached: dict = st.session_state[price_key]
    uncached = [g["store_url"].split("/app/")[1].split("/")[0]
                for g in matched[:24]
                if int(g["store_url"].split("/app/")[1].split("/")[0]) not in cached]
    uncached_ids = [int(x) for x in uncached]
    if uncached_ids:
        with st.spinner("Steam 가격 정보 확인 중..."):
            fetched = steam.get_price_info_batch(uncached_ids)
            cached.update(fetched)
            for aid in uncached_ids:
                cached.setdefault(aid, None)
        st.session_state[price_key] = cached

    # 4열 그리드 표시
    display = matched[:24]
    cols_per_row = 4
    for row_start in range(0, len(display), cols_per_row):
        row_games = display[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, game in zip(cols, row_games):
            app_id = int(game["store_url"].split("/app/")[1].split("/")[0])
            price_info = cached.get(app_id)

            if price_info:
                if price_info.get("is_free"):
                    price_str = "무료"
                    price_clr = "#46d369"
                elif price_info.get("discount_percent", 0) > 0:
                    price_str = f"<s style='color:#737373;font-size:0.75rem;'>{price_info['original']}</s> <b style='color:#46d369;'>{price_info['final']}</b> <span style='background:#4c6b22;color:#a4d007;border-radius:3px;padding:1px 5px;font-size:0.72rem;'>-{price_info['discount_percent']}%</span>"
                    price_clr = "#46d369"
                else:
                    price_str = price_info.get("final", "")
                    price_clr = "#b3b3b3"
            else:
                price_str = ""
                price_clr = "#555"

            genre_tags = " ".join(
                f'<span style="background:#2a2a2a;color:{"#E50914" if g in (selected or []) else "#666"};'
                f'border-radius:3px;padding:1px 5px;font-size:0.65rem;">{g}</span>'
                for g in game["genres"][:3]
            )
            rank_badge = f'<span style="background:#333;color:#b3b3b3;border-radius:3px;padding:1px 6px;font-size:0.68rem;">#{game["rank"]}</span>'

            with col:
                st.markdown(f"""
                <a href="{game['store_url']}" target="_blank" style="text-decoration:none;">
                    <div style="background:#1a1a1a;border-radius:10px;overflow:hidden;
                                margin-bottom:16px;border:1px solid #2a2a2a;
                                transition:border-color 0.2s;"
                         onmouseover="this.style.borderColor='#E50914'"
                         onmouseout="this.style.borderColor='#2a2a2a'">
                        <div style="position:relative;">
                            <img src="{game['header_image']}" style="width:100%;display:block;">
                            <div style="position:absolute;top:6px;left:6px;">{rank_badge}</div>
                        </div>
                        <div style="padding:10px 12px;">
                            <div style="font-weight:700;font-size:0.88rem;color:#fff;
                                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                                        margin-bottom:6px;">{game['name']}</div>
                            <div style="margin-bottom:6px;">{genre_tags}</div>
                            <div style="font-size:0.82rem;color:{price_clr};">{price_str}</div>
                        </div>
                    </div>
                </a>
                """, unsafe_allow_html=True)


# ── 라우터 ────────────────────────────────────────────────────────────────────
page = st.session_state.page
if page == "login":
    page_login()
elif page == "dashboard":
    page_dashboard()
elif page == "recommendations":
    page_recommendations()
elif page == "genre_explorer":
    page_genre_explorer()
