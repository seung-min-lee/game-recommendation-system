import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from steam_service import SteamService
from recommender import GameRecommender

try:
    from snowflake_service import snowflake_svc
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
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
def _get_recs(steam_id, owned_games):
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
    return {**recommender.get_recommendations(steam_id, owned_games), "source": "local"}


def _carousel_html(games: list) -> str:
    if not games:
        return '<p style="color:#b3b3b3;padding:20px 0;">추천 결과가 없습니다.</p>'
    cards = ""
    for g in games:
        name        = (g.get("name") or "Unknown").replace("'", "&#39;")
        img         = g.get("header_image") or "https://via.placeholder.com/280x150/181818/555?text=No+Image"
        match_pct   = g.get("match_percent", 0)
        store_url   = g.get("store_url", "#")
        metacritic  = g.get("metacritic")
        mc_html     = f'<span style="background:#E50914;color:#fff;border-radius:3px;padding:1px 6px;font-size:0.75rem;font-weight:bold;">MC {metacritic}</span>' if metacritic else ""
        cards += f"""
        <div onclick="window.open('{store_url}','_blank')" style="
            background:#181818; border-radius:8px; overflow:hidden;
            cursor:pointer; width:240px; flex:0 0 auto; scroll-snap-align:start;
            transition:transform 0.3s,box-shadow 0.3s;
            " onmouseover="this.style.transform='scale(1.08)';this.style.boxShadow='0 15px 30px rgba(0,0,0,0.7)';this.style.zIndex='10'"
               onmouseout="this.style.transform='scale(1)';this.style.boxShadow='none';this.style.zIndex='1'">
            <img src="{img}" style="width:100%;height:135px;object-fit:cover;"
                 onerror="this.src='https://via.placeholder.com/240x135/181818/555?text=No+Image'">
            <div style="padding:12px;">
                <p style="color:#fff;font-size:0.95rem;font-weight:bold;margin-bottom:8px;
                           white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</p>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="color:#46d369;font-weight:bold;font-size:0.9rem;">{match_pct}% 일치</span>
                    {mc_html}
                </div>
                <p style="color:#E50914;font-size:0.8rem;margin-top:6px;font-weight:bold;">스토어 이동 ➔</p>
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
    from dummy_data import DUMMY_OWNED_GAMES, GAME_CATALOG

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
            with st.spinner("분석 중..."):
                user   = steam.get_user_summary(steam_id.strip())
                owned  = steam.get_owned_games(steam_id.strip())
                if not owned:
                    st.error("게임 데이터를 찾을 수 없습니다.")
                    return
                stats  = recommender.compute_stats(owned)
                recs   = _get_recs(steam_id.strip(), owned)
                st.session_state.update(
                    steam_id=steam_id.strip(), user=user,
                    stats=stats, recs=recs, owned_games=owned, page="dashboard",
                )
                st.rerun()

    st.markdown("""
    <div style="text-align:center;color:#737373;font-size:0.8rem;margin-top:40px;">
        Powered by Steam API &nbsp;·&nbsp; Not affiliated with Valve Corporation.
    </div>
    """, unsafe_allow_html=True)


# ── 페이지: 대시보드 ──────────────────────────────────────────────────────────
def page_dashboard():
    user  = st.session_state.user or {}
    stats = st.session_state.stats or {}

    avatar   = user.get("avatar_url", "")
    username = user.get("username", "Unknown")
    total_h  = stats.get("total_playtime_hours", 0)
    total_g  = stats.get("total_games", 0)

    # 프로필 헤더
    avatar_html = f'<img src="{avatar}" style="width:80px;height:80px;border-radius:4px;border:2px solid #E50914;margin-right:20px;">' if avatar else ""
    st.markdown(f"""
    <div style="display:flex;align-items:center;background:#181818;padding:25px 30px;
                border-radius:8px;margin-bottom:30px;">
        {avatar_html}
        <div>
            <h2 style="color:#fff;font-size:1.8rem;margin-bottom:5px;">{username} 님의 플레이 기록</h2>
            <p style="color:#b3b3b3;font-size:1rem;">
                총 플레이타임: {total_h:,} 시간 &nbsp;·&nbsp; 보유 게임: {total_g}개
            </p>
        </div>
        <div style="margin-left:auto;">
    """, unsafe_allow_html=True)

    logout_col = st.columns([8, 1])[1]
    with logout_col:
        if st.button("로그아웃", key="logout_btn"):
            for k in ["steam_id", "user", "stats", "recs", "owned_games"]:
                st.session_state[k] = None
            st.session_state.page = "login"
            st.rerun()

    # 차트
    genre_dist = stats.get("genre_distribution", {})
    top5       = stats.get("top5_games", [])

    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown('<div style="background:#181818;padding:25px;border-radius:8px;">', unsafe_allow_html=True)
        st.markdown('<h3 style="text-align:center;margin-bottom:20px;">선호하는 장르</h3>', unsafe_allow_html=True)
        if genre_dist:
            df = pd.DataFrame([{"장르": g, "시간": round(v["minutes"]/60, 1)}
                                for g, v in list(genre_dist.items())[:6]])
            colors = ["#E50914", "#B20710", "#831010", "#5A0A0A", "#4A4A4A", "#2B2B2B"]
            fig = go.Figure(go.Pie(
                labels=df["장르"], values=df["시간"],
                hole=0.45,
                marker=dict(colors=colors[:len(df)], line=dict(color="#141414", width=2)),
            ))
            fig.update_layout(
                paper_bgcolor="#181818", plot_bgcolor="#181818",
                font_color="#b3b3b3", margin=dict(t=10, b=10),
                legend=dict(font=dict(color="#b3b3b3")),
                showlegend=True,
            )
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with ch2:
        st.markdown('<div style="background:#181818;padding:25px;border-radius:8px;">', unsafe_allow_html=True)
        st.markdown('<h3 style="text-align:center;margin-bottom:20px;">가장 많이 플레이한 게임</h3>', unsafe_allow_html=True)
        if top5:
            df2 = pd.DataFrame([{"게임": g["name"][:22], "시간": g["playtime_hours"]} for g in top5])
            fig2 = go.Figure(go.Bar(
                x=df2["시간"], y=df2["게임"], orientation="h",
                marker=dict(color="#E50914", cornerradius=4),
            ))
            fig2.update_layout(
                paper_bgcolor="#181818", plot_bgcolor="#181818",
                font_color="#b3b3b3", margin=dict(t=10, b=10, l=10),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", autorange="reversed"),
            )
            st.plotly_chart(fig2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    _, btn_col, _ = st.columns([2, 3, 2])
    with btn_col:
        if st.button("맞춤 추천작 보기 ➔", key="go_recs"):
            st.session_state.page = "recommendations"
            st.rerun()


# ── 페이지: 추천 ──────────────────────────────────────────────────────────────
def page_recommendations():
    recs     = st.session_state.recs or {}
    username = (st.session_state.user or {}).get("username", "Unknown")

    # 헤더
    hc1, hc2 = st.columns([7, 1])
    with hc1:
        st.markdown(f"""
        <div style="border-bottom:2px solid #2f2f2f;padding-bottom:20px;margin-bottom:40px;">
            <h1 style="font-size:2.2rem;font-weight:800;">AI 맞춤 추천 게임</h1>
            <p style="color:#b3b3b3;">{username}님을 위한 게임 추천</p>
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
        st.markdown(_carousel_html(recs.get("genre_based", [])), unsafe_allow_html=True)

    with tab2:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">👥 유사 유저 기반 추천</h2>', unsafe_allow_html=True)
        st.markdown(_carousel_html(recs.get("collab_based", [])), unsafe_allow_html=True)

    with tab3:
        st.markdown('<h2 style="font-size:1.5rem;padding-left:10px;border-left:4px solid #E50914;">💎 숨겨진 명작</h2>', unsafe_allow_html=True)
        st.markdown(_carousel_html(recs.get("hidden_gems", [])), unsafe_allow_html=True)

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
        st.markdown(_carousel_html(graph_games), unsafe_allow_html=True)


# ── 라우터 ────────────────────────────────────────────────────────────────────
page = st.session_state.page
if page == "login":
    page_login()
elif page == "dashboard":
    page_dashboard()
elif page == "recommendations":
    page_recommendations()
