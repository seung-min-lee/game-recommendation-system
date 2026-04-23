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


def _render_carousel(games: list):
    html = _carousel_html(games)
    components.html(html, height=360, scrolling=False)


def _review_card_html(r: dict) -> str:
    """리뷰 하나를 완전한 HTML 카드로 변환 (unclosed tag 없음)."""
    icon  = "👍" if r["voted_up"] else "👎"
    color = "#46d369" if r["voted_up"] else "#E50914"
    pt    = r.get("playtime_hours", 0)
    text  = (r.get("text") or "(리뷰 내용 없음)").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<div style="background:#202020;border-radius:8px;padding:14px;'
        f'border-top:2px solid {color};min-height:100px;">'
        f'<div style="color:{color};font-weight:bold;margin-bottom:8px;font-size:0.82rem;">'
        f'{icon} &nbsp;플레이 {pt}시간</div>'
        f'<p style="color:#d0d0d0;font-size:0.81rem;line-height:1.55;margin:0;">{text}</p>'
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
        st.markdown('<p style="color:#737373;font-size:0.85rem;margin-top:8px;">리뷰 데이터를 가져올 수 없습니다.</p>',
                    unsafe_allow_html=True)
        return

    # ── 페이지네이션 ──────────────────────────────────────────────────────────
    total_pages = max(1, (len(all_reviews) + PER_PAGE - 1) // PER_PAGE)
    page_key    = f"_rv_pg_{key_prefix}_{app_id}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    cur_page    = min(st.session_state[page_key], total_pages - 1)
    page_reviews = all_reviews[cur_page * PER_PAGE:(cur_page + 1) * PER_PAGE]

    # ── 리뷰 카드 그리드 (3열) — 각 카드는 완전한 HTML ──────────────────────
    st.markdown("<div style='margin-top:12px;'>", unsafe_allow_html=True)
    for row_start in range(0, len(page_reviews), 3):
        row = page_reviews[row_start:row_start + 3]
        cols = st.columns(3)
        for i, r in enumerate(row):
            with cols[i]:
                st.markdown(_review_card_html(r), unsafe_allow_html=True)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── 페이지 네비게이션 (st.radio — 버튼보다 1.4배 작음) ──────────────────
    if total_pages > 1:
        st.markdown(
            f'<p style="color:#737373;font-size:0.75rem;margin:10px 0 2px;">'
            f'총 {len(all_reviews)}개 리뷰 · 페이지당 {PER_PAGE}개</p>',
            unsafe_allow_html=True,
        )
        # radio는 버튼 대비 자연스럽게 소형 렌더링
        chosen = st.radio(
            "",
            options=list(range(1, min(total_pages, 10) + 1)),
            index=cur_page,
            horizontal=True,
            key=f"rv_radio_{key_prefix}_{app_id}",
            label_visibility="collapsed",
            format_func=lambda p: f"{p}",
        )
        if chosen - 1 != cur_page:
            st.session_state[page_key] = chosen - 1
            st.rerun()


def _carousel_html(games: list) -> str:
    if not games:
        return '<p style="color:#b3b3b3;padding:20px 0;">추천 결과가 없습니다.</p>'
    cards = ""
    for g in games:
        name       = (g.get("name") or "Unknown").replace("'", "&#39;")
        img        = g.get("header_image") or "https://via.placeholder.com/280x150/181818/555?text=No+Image"
        match_pct  = g.get("match_percent", 0)
        store_url  = g.get("store_url", "#")
        metacritic = g.get("metacritic")
        reason     = g.get("reason", "")
        mc_html    = f'<span style="background:#E50914;color:#fff;border-radius:3px;padding:1px 6px;font-size:0.72rem;font-weight:bold;">MC {metacritic}</span>' if metacritic else ""
        reason_html = (
            f'<p style="color:#a0a0b0;font-size:0.72rem;margin:5px 0 0;'
            f'line-height:1.35;border-top:1px solid #2a2a2a;padding-top:5px;">'
            f'🤖 {reason}</p>'
        ) if reason else ""
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
    from data.dummy_data import DUMMY_OWNED_GAMES, GAME_CATALOG

    all_interactions = {}
    for uid, games in DUMMY_OWNED_GAMES.items():
        all_interactions[uid] = {g["app_id"]: g.get("playtime_minutes", 1) for g in games}
    all_interactions[steam_id] = {g["app_id"]: g.get("playtime_minutes", 1) for g in owned_games}

    users    = list(all_interactions.keys())
    game_ids = sorted({aid for gs in all_interactions.values() for aid in gs})
    owned_ids = {g["app_id"] for g in owned_games}
    rec_ids   = {g["app_id"] for g in rec_games}

    n_u, n_g = len(users), len(game_ids)
    user_pos = {u: (0.0, i / max(n_u - 1, 1)) for i, u in enumerate(users)}
    game_pos = {g: (1.0, i / max(n_g - 1, 1)) for i, g in enumerate(game_ids)}

    fig = go.Figure()

    for uid, games in all_interactions.items():
        ux, uy = user_pos[uid]
        for aid in games:
            gx, gy = game_pos[aid]
            is_me  = uid == steam_id
            is_rec = aid in rec_ids
            color  = "rgba(229,9,20,0.7)"   if (is_me and is_rec)  else \
                     "rgba(229,9,20,0.3)"   if is_me               else \
                     "rgba(255,255,255,0.08)"
            width  = 2.5 if is_me else 0.6
            fig.add_trace(go.Scatter(
                x=[ux, gx, None], y=[uy, gy, None],
                mode="lines", line=dict(width=width, color=color),
                hoverinfo="none", showlegend=False,
            ))

    for uid in users:
        ux, uy = user_pos[uid]
        is_me  = uid == steam_id
        label  = "👤 나" if is_me else f"User_{uid[-4:]}"
        fig.add_trace(go.Scatter(
            x=[ux], y=[uy], mode="markers+text",
            marker=dict(size=22 if is_me else 14,
                        color="#E50914" if is_me else "#555555",
                        line=dict(width=2, color="white")),
            text=[label], textposition="middle left",
            textfont=dict(size=12 if is_me else 10, color="white"),
            hovertemplate=f"<b>{label}</b><br>게임 수: {len(all_interactions[uid])}<extra></extra>",
            showlegend=False,
        ))

    for aid in game_ids:
        gx, gy = game_pos[aid]
        name   = GAME_CATALOG.get(aid, {}).get("name", f"Game_{aid}")
        genres = ", ".join(GAME_CATALOG.get(aid, {}).get("genres", [])[:2])
        if aid in rec_ids:
            color, symbol, size, label = "#E50914", "star", 16, f"⭐ {name[:15]}"
        elif aid in owned_ids:
            color, symbol, size, label = "#ffffff", "square", 13, f"🎮 {name[:15]}"
        else:
            color, symbol, size, label = "#444444", "circle", 9, name[:15]
        fig.add_trace(go.Scatter(
            x=[gx], y=[gy], mode="markers+text",
            marker=dict(size=size, color=color, symbol=symbol,
                        line=dict(width=1, color="#333")),
            text=[label], textposition="middle right",
            textfont=dict(size=9, color="#b3b3b3"),
            hovertemplate=f"<b>{name}</b><br>{genres}<extra></extra>",
            showlegend=False,
        ))

    for label, color, symbol in [
        ("현재 유저",    "#E50914", "circle"),
        ("다른 유저",    "#555555", "circle"),
        ("추천 게임 ⭐", "#E50914", "star"),
        ("보유 게임",    "#ffffff", "square"),
        ("기타 게임",    "#444444", "circle"),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color, symbol=symbol),
            name=label, showlegend=True,
        ))

    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#181818",
        font_color="#e5e5e5", height=500,
        margin=dict(l=160, r=200, t=20, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.35, 1.35]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        legend=dict(bgcolor="#181818", bordercolor="#2f2f2f", borderwidth=1,
                    font=dict(color="white", size=11)),
        annotations=[
            dict(x=0.0, y=1.04, xref="paper", yref="paper",
                 text="<b>유저</b>", showarrow=False, font=dict(size=13, color="#b3b3b3")),
            dict(x=1.0, y=1.04, xref="paper", yref="paper",
                 text="<b>게임</b>", showarrow=False, font=dict(size=13, color="#b3b3b3")),
        ],
    )
    return fig


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

        for fid, f_games in sorted(
            friends_games.items(),
            key=lambda kv: -len(kv[1]),
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
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
        <div style="background:rgba(0,0,0,0.75);border-radius:8px;padding:50px 40px;margin-top:60px;text-align:center;">
            <h1 style="color:#E50914;font-size:3rem;font-weight:900;letter-spacing:2px;
                       text-transform:uppercase;margin-bottom:10px;">Game Finder</h1>
            <p style="color:#b3b3b3;font-size:1rem;margin-bottom:40px;line-height:1.6;">
                당신의 플레이 기록을 분석하여<br>최고의 게임을 추천합니다.
            </p>
        </div>
        """, unsafe_allow_html=True)

        steam_id = st.text_input("", placeholder="스팀 ID 입력 (예: 76561198000000001)",
                                  label_visibility="collapsed")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        login_clicked = st.button("시작하기", key="login_btn")

        st.markdown("""
        <div style="display:flex;align-items:center;color:#737373;font-size:0.9rem;margin:20px 0;">
            <div style="flex:1;border-bottom:1px solid #333;"></div>
            <span style="padding:0 15px;">또는 데모 계정</span>
            <div style="flex:1;border-bottom:1px solid #333;"></div>
        </div>
        """, unsafe_allow_html=True)

        demo_ids = ["76561198000000001", "76561198000000002", "76561198000000003"]
        dcols = st.columns(3)
        for i, did in enumerate(demo_ids):
            if dcols[i].button(f"Demo {i+1}", key=f"demo_{i}"):
                steam_id = did
                login_clicked = True

        if login_clicked:
            if not steam_id or not steam_id.strip():
                st.error("스팀 ID를 입력해주세요.")
                return
            sid = steam_id.strip()
            with st.spinner("게임 데이터 불러오는 중..."):
                user  = steam.get_user_summary(sid)
                owned = steam.get_owned_games(sid)
                if not owned:
                    st.error("게임 데이터를 찾을 수 없습니다.")
                    return
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
    <div style="text-align:center;color:#737373;font-size:0.8rem;margin-top:40px;">
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
            for k in ["steam_id", "user", "stats", "recs", "owned_games",
                      "friends_games", "friends_profiles", "friends_count"]:
                st.session_state[k] = None if k not in ("friends_games", "friends_profiles") else {}
            st.session_state.page = "login"
            st.rerun()

    # 차트 — 독립적인 st.markdown 호출만 사용 (div 분할 없음)
    genre_dist = stats.get("genre_distribution", {})
    top5       = stats.get("top5_games", [])

    ch1, ch2 = st.columns(2)

    # 색상환 전체를 고르게 분산한 26가지 완전히 구별되는 색상
    GENRE_COLORS = {
        "Action":         "#FF2D2D",  # 선명한 빨강
        "FPS":            "#FF6A00",  # 진한 주황
        "Adventure":      "#FFB300",  # 황금 노랑
        "Simulation":     "#CCDD00",  # 라임 옐로
        "Platformer":     "#7ED321",  # 연두
        "Open World":     "#00C853",  # 초록
        "Survival":       "#00BFA5",  # 민트 그린
        "Roguelike":      "#00E5FF",  # 청록 시안
        "MOBA":           "#00B0FF",  # 하늘파랑
        "Co-op":          "#2979FF",  # 파랑
        "RPG":            "#651FFF",  # 보라파랑
        "Strategy":       "#D500F9",  # 진보라
        "Horror":         "#AA00FF",  # 네온 보라
        "Metroidvania":   "#C51162",  # 진분홍
        "Indie":          "#FF4081",  # 핫핑크
        "Story Rich":     "#F06292",  # 연분홍
        "Hack and Slash": "#FF3D00",  # 빨간 주황
        "Shooter":        "#FF6D00",  # 주황
        "Souls-like":     "#8D6E63",  # 브라운
        "Battle Royale":  "#F57F17",  # 다크 앰버
        "Tactical":       "#546E7A",  # 슬레이트 블루그레이
        "Turn-Based":     "#43A047",  # 미디엄 그린
        "Sci-fi":         "#0097A7",  # 딥 시안
        "Sandbox":        "#FB8C00",  # 오렌지
        "MMORPG":         "#5E35B1",  # 딥 인디고
        "Racing":         "#E53935",  # 레드
    }
    # GENRE_COLORS에 없는 장르를 위한 폴백 — 위 26색과 겹치지 않는 색들
    FALLBACK_PALETTE = [
        "#26C6DA","#9CCC65","#FFA726","#AB47BC","#EC407A",
        "#29B6F6","#66BB6A","#FFCA28","#8D6E63","#78909C",
    ]

    # 장르 → 색상 매핑 함수 (pie와 bar 공유)
    def get_genre_color(genre: str, idx: int = 0) -> str:
        return GENRE_COLORS.get(genre, FALLBACK_PALETTE[idx % len(FALLBACK_PALETTE)])

    with ch1:
        st.markdown('<h3 style="text-align:center;margin-bottom:10px;color:#fff;">선호하는 장르</h3>',
                    unsafe_allow_html=True)
        if genre_dist:
            items = list(genre_dist.items())[:8]
            labels = [g for g, _ in items]
            values = [round(v["minutes"] / 60, 1) for _, v in items]
            pcts   = [v["percentage"] for _, v in items]
            colors = [get_genre_color(g, i) for i, g in enumerate(labels)]
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
                legend=dict(
                    font=dict(color="#b3b3b3", size=11),
                    bgcolor="rgba(0,0,0,0)",
                    orientation="v",
                ),
            )
            st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown('<h3 style="text-align:center;margin-bottom:10px;color:#fff;">가장 많이 플레이한 게임</h3>',
                    unsafe_allow_html=True)
        if top5:
            # 각 게임의 주 장르 색상을 pie chart와 동일하게 매핑
            bar_colors = []
            for i, g in enumerate(top5):
                primary_genre = (g.get("genres") or [""])[0]
                bar_colors.append(get_genre_color(primary_genre, i))

            names  = [g["name"][:22] for g in top5]
            hours  = [g["playtime_hours"] for g in top5]
            genres = [(g.get("genres") or ["기타"])[0] for g in top5]

            fig2 = go.Figure(go.Bar(
                x=hours,
                y=names,
                orientation="h",
                marker=dict(color=bar_colors, cornerradius=4),
                customdata=genres,
                hovertemplate="<b>%{y}</b><br>%{x}시간<br>장르: %{customdata}<extra></extra>",
            ))
            fig2.update_layout(
                paper_bgcolor="#181818", plot_bgcolor="#181818",
                font_color="#b3b3b3", margin=dict(t=10, b=10, l=10, r=10),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="플레이 시간 (h)"),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", autorange="reversed"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    _, btn_col, _ = st.columns([2, 3, 2])
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

    tab1, tab2, tab3, tab4 = st.tabs(["🎮 장르 기반 추천", "👥 유사 유저 기반 추천", "💎 숨겨진 명작", "🕸️ LightGCN"])

    with tab1:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">🎮 장르 기반 추천</h2>', unsafe_allow_html=True)
        genre_games = recs.get("genre_based", [])
        _render_carousel(genre_games)
        _show_reviews_panel(genre_games, "genre")

    with tab2:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">👥 유사 유저 기반 추천</h2>', unsafe_allow_html=True)
        collab_games = recs.get("collab_based", [])
        _render_carousel(collab_games)
        _show_reviews_panel(collab_games, "collab")

    with tab3:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">💎 숨겨진 명작</h2>', unsafe_allow_html=True)
        hidden_games = recs.get("hidden_gems", [])
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
        graph_games = recs.get("graph_based", [])
        fig_graph = _build_lightgcn_graph(
            st.session_state.steam_id,
            st.session_state.owned_games or [],
            graph_games,
        )
        st.plotly_chart(fig_graph, use_container_width=True)
        st.markdown("---")
        _render_carousel(graph_games)
        _show_reviews_panel(graph_games, "graph")


# ── 라우터 ────────────────────────────────────────────────────────────────────
page = st.session_state.page
if page == "login":
    page_login()
elif page == "dashboard":
    page_dashboard()
elif page == "recommendations":
    page_recommendations()
