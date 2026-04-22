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

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .game-card {
        background: #1a1d2e;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 12px;
        border: 1px solid #2d3250;
        transition: transform 0.2s;
    }
    .game-card:hover { transform: translateY(-2px); border-color: #5865f2; }
    .match-badge {
        background: linear-gradient(135deg, #5865f2, #eb459e);
        color: white;
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 13px;
        font-weight: bold;
    }
    .meta-badge {
        background: #ffd700;
        color: #111;
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 12px;
        font-weight: bold;
    }
    .stat-card {
        background: #1a1d2e;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid #2d3250;
    }
    .genre-tag {
        background: #2d3250;
        border-radius: 10px;
        padding: 2px 10px;
        margin: 2px;
        font-size: 12px;
        display: inline-block;
    }
    h1, h2, h3 { color: #ffffff !important; }
    .stButton > button {
        background: linear-gradient(135deg, #5865f2, #eb459e);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 30px;
        font-size: 16px;
        font-weight: bold;
        width: 100%;
    }
    .stButton > button:hover { opacity: 0.9; }
    div[data-testid="stTextInput"] input {
        background: #1a1d2e;
        border: 1px solid #2d3250;
        border-radius: 8px;
        color: white;
        font-size: 16px;
        padding: 12px;
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
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
def _get_recs(steam_id: str, owned_games: list) -> dict:
    if _snowflake_ok:
        try:
            if snowflake_svc.has_recommendations(steam_id):
                import json as _json

                def _fmt(g):
                    genres = g.get("genres", [])
                    if isinstance(genres, str):
                        try:
                            genres = _json.loads(genres)
                        except Exception:
                            genres = [genres]
                    return {
                        "app_id": g.get("app_id"),
                        "name": g.get("game_name"),
                        "header_image": g.get("header_image"),
                        "store_url": g.get("store_url"),
                        "genres": genres,
                        "match_percent": g.get("metacritic") or min(int(float(g.get("score") or 0)), 100),
                        "metacritic": g.get("metacritic"),
                    }

                return {
                    "genre_based": [_fmt(g) for g in snowflake_svc.get_cbf_recommendations(steam_id)],
                    "collab_based": [_fmt(g) for g in snowflake_svc.get_cf_recommendations(steam_id)],
                    "hidden_gems": [_fmt(g) for g in snowflake_svc.get_genre_trend(steam_id)],
                    "source": "snowflake",
                }
        except Exception:
            pass
    return {**recommender.get_recommendations(steam_id, owned_games), "source": "local"}


def _game_card(game: dict):
    name = game.get("name") or "Unknown"
    img = game.get("header_image") or ""
    genres = game.get("genres") or []
    match_pct = game.get("match_percent", 0)
    metacritic = game.get("metacritic")
    store_url = game.get("store_url", "#")

    genre_tags = " ".join(f'<span class="genre-tag">{g}</span>' for g in genres[:3])
    meta_html = f'<span class="meta-badge">MC {metacritic}</span>' if metacritic else ""

    html = f"""
    <div class="game-card">
        <div style="display:flex; gap:14px; align-items:flex-start;">
            <img src="{img}" style="width:120px; height:56px; object-fit:cover; border-radius:6px; flex-shrink:0;" onerror="this.style.display='none'">
            <div style="flex:1; min-width:0;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                    <span style="font-weight:bold; font-size:15px; color:#fff;">{name}</span>
                    <span class="match-badge">일치율 {match_pct}%</span>
                </div>
                <div style="margin-top:6px;">{genre_tags} {meta_html}</div>
                <a href="{store_url}" target="_blank" style="color:#5865f2; font-size:12px; text-decoration:none;">Steam에서 보기 →</a>
            </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ── LightGCN 그래프 시각화 ────────────────────────────────────────────────────
def _build_lightgcn_graph(steam_id: str, owned_games: list, rec_games: list) -> go.Figure:
    from dummy_data import DUMMY_OWNED_GAMES, GAME_CATALOG

    # 전체 인터랙션 수집 (더미 유저 + 현재 유저)
    all_interactions: dict = {}
    for uid, games in DUMMY_OWNED_GAMES.items():
        all_interactions[uid] = {g["app_id"]: g.get("playtime_minutes", 1) for g in games}
    all_interactions[steam_id] = {g["app_id"]: g.get("playtime_minutes", 1) for g in owned_games}

    users   = list(all_interactions.keys())
    game_ids = sorted({aid for games in all_interactions.values() for aid in games})

    owned_ids = {g["app_id"] for g in owned_games}
    rec_ids   = {g["app_id"] for g in rec_games}

    n_u = len(users)
    n_g = len(game_ids)

    # 이분 그래프 레이아웃: 유저 왼쪽(x=0), 게임 오른쪽(x=1)
    user_pos  = {u: (0.0, i / max(n_u - 1, 1)) for i, u in enumerate(users)}
    game_pos  = {g: (1.0, i / max(n_g - 1, 1)) for i, g in enumerate(game_ids)}

    import math
    fig = go.Figure()

    # ── 엣지 ──────────────────────────────────────────────────────────────────
    # 추천 엣지(초록)와 일반 엣지(회색) 분리
    for uid, games in all_interactions.items():
        ux, uy = user_pos[uid]
        for aid, playtime in games.items():
            gx, gy = game_pos[aid]
            is_current = uid == steam_id
            is_rec     = aid in rec_ids
            color  = "rgba(87,242,135,0.6)"  if (is_current and is_rec)  else \
                     "rgba(254,215,92,0.5)"  if is_current                else \
                     "rgba(88,101,242,0.2)"
            width  = 2.5 if is_current else 0.8
            fig.add_trace(go.Scatter(
                x=[ux, gx, None], y=[uy, gy, None],
                mode="lines",
                line=dict(width=width, color=color),
                hoverinfo="none",
                showlegend=False,
            ))

    # ── 유저 노드 ─────────────────────────────────────────────────────────────
    for uid in users:
        ux, uy = user_pos[uid]
        is_me   = uid == steam_id
        label   = "👤 나 (현재 유저)" if is_me else f"User_{uid[-4:]}"
        color   = "#eb459e" if is_me else "#5865f2"
        size    = 22 if is_me else 14
        fig.add_trace(go.Scatter(
            x=[ux], y=[uy],
            mode="markers+text",
            marker=dict(size=size, color=color, line=dict(width=2, color="white")),
            text=[label],
            textposition="middle left",
            textfont=dict(size=12 if is_me else 10, color="white"),
            hovertemplate=f"<b>{label}</b><br>게임 수: {len(all_interactions[uid])}<extra></extra>",
            showlegend=False,
        ))

    # ── 게임 노드 ─────────────────────────────────────────────────────────────
    for aid in game_ids:
        gx, gy = game_pos[aid]
        info   = GAME_CATALOG.get(aid, {})
        name   = info.get("name", f"Game_{aid}")
        genres = ", ".join(info.get("genres", [])[:2])

        if aid in rec_ids:
            color, symbol, size = "#57f287", "star", 16
            label = f"⭐ {name[:16]}"
        elif aid in owned_ids:
            color, symbol, size = "#fee75c", "square", 13
            label = f"🎮 {name[:16]}"
        else:
            color, symbol, size = "#6b7280", "circle", 10
            label = name[:16]

        fig.add_trace(go.Scatter(
            x=[gx], y=[gy],
            mode="markers+text",
            marker=dict(size=size, color=color, symbol=symbol,
                        line=dict(width=1, color="white")),
            text=[label],
            textposition="middle right",
            textfont=dict(size=9, color="white"),
            hovertemplate=f"<b>{name}</b><br>장르: {genres}<extra></extra>",
            showlegend=False,
        ))

    # ── 범례 (더미 trace) ─────────────────────────────────────────────────────
    for label, color, symbol in [
        ("현재 유저",    "#eb459e", "circle"),
        ("다른 유저",    "#5865f2", "circle"),
        ("추천 게임 ⭐", "#57f287", "star"),
        ("보유 게임",    "#fee75c", "square"),
        ("기타 게임",    "#6b7280", "circle"),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color, symbol=symbol),
            name=label, showlegend=True,
        ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,17,23,1)",
        font_color="white",
        height=520,
        margin=dict(l=160, r=200, t=10, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-0.3, 1.3]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        legend=dict(
            bgcolor="rgba(26,29,46,0.9)",
            bordercolor="#2d3250",
            borderwidth=1,
            font=dict(color="white", size=11),
        ),
        annotations=[
            dict(x=0.0, y=1.05, xref="paper", yref="paper",
                 text="<b>유저</b>", showarrow=False,
                 font=dict(size=13, color="#8b8fa8")),
            dict(x=1.0, y=1.05, xref="paper", yref="paper",
                 text="<b>게임</b>", showarrow=False,
                 font=dict(size=13, color="#8b8fa8")),
        ],
    )
    return fig


# ── 페이지: 로그인 ────────────────────────────────────────────────────────────
def page_login():
    st.markdown("<br>" * 2, unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]

    with col:
        st.markdown("""
        <div style="text-align:center; padding: 40px 0 20px;">
            <span style="font-size:64px;">🎮</span>
            <h1 style="font-size:42px; margin:10px 0 4px;">Game Finder</h1>
            <p style="color:#8b8fa8; font-size:16px;">Steam 플레이 기록 기반 AI 게임 추천</p>
        </div>
        """, unsafe_allow_html=True)

        steam_id = st.text_input(
            "Steam ID",
            placeholder="Steam ID를 입력하세요 (예: 76561198000000001)",
            label_visibility="collapsed",
        )

        demo_ids = ["76561198000000001", "76561198000000002", "76561198000000003"]
        st.markdown("<p style='color:#8b8fa8; font-size:13px; text-align:center;'>데모 계정</p>", unsafe_allow_html=True)
        dcols = st.columns(3)
        for i, did in enumerate(demo_ids):
            if dcols[i].button(f"Demo {i+1}", key=f"demo_{i}"):
                steam_id = did

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("시작하기", key="login_btn"):
            if not steam_id.strip():
                st.error("Steam ID를 입력해주세요.")
                return
            with st.spinner("데이터 불러오는 중..."):
                user = steam.get_user_summary(steam_id.strip())
                owned = steam.get_owned_games(steam_id.strip())
                if not owned:
                    st.error("게임 데이터를 찾을 수 없습니다.")
                    return
                stats = recommender.compute_stats(owned)
                recs = _get_recs(steam_id.strip(), owned)
                st.session_state.update(
                    steam_id=steam_id.strip(),
                    user=user,
                    stats=stats,
                    recs=recs,
                    owned_games=owned,
                    page="dashboard",
                )
                st.rerun()


# ── 페이지: 대시보드 ──────────────────────────────────────────────────────────
def page_dashboard():
    user = st.session_state.user or {}
    stats = st.session_state.stats or {}

    # 상단 헤더
    hcol1, hcol2 = st.columns([6, 1])
    with hcol1:
        avatar = user.get("avatar_url", "")
        username = user.get("username", "Unknown")
        if avatar:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:16px;">'
                f'<img src="{avatar}" style="width:60px;height:60px;border-radius:50%;">'
                f'<div><h2 style="margin:0;">{username}</h2>'
                f'<p style="color:#8b8fa8;margin:0;">{st.session_state.steam_id}</p></div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"## {username}")
    with hcol2:
        if st.button("로그아웃"):
            for k in ["steam_id", "user", "stats", "recs"]:
                st.session_state[k] = None
            st.session_state.page = "login"
            st.rerun()

    st.markdown("---")

    # 통계 카드
    total_hours = stats.get("total_playtime_hours", 0)
    total_games = stats.get("total_games", 0)
    genre_dist = stats.get("genre_distribution", {})
    top_genre = max(genre_dist, key=lambda g: genre_dist[g]["minutes"]) if genre_dist else "-"

    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="stat-card"><h1 style="color:#5865f2;">{total_hours:,}</h1><p style="color:#8b8fa8;">총 플레이타임 (시간)</p></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="stat-card"><h1 style="color:#eb459e;">{total_games}</h1><p style="color:#8b8fa8;">보유 게임 수</p></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="stat-card"><h1 style="color:#57f287; font-size:28px;">{top_genre}</h1><p style="color:#8b8fa8;">최다 플레이 장르</p></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 차트
    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown("#### 장르별 플레이타임")
        if genre_dist:
            df_genre = pd.DataFrame([
                {"장르": g, "시간": round(v["minutes"] / 60, 1)}
                for g, v in list(genre_dist.items())[:8]
            ])
            fig = px.pie(
                df_genre, names="장르", values="시간",
                color_discrete_sequence=px.colors.sequential.Plasma_r,
                hole=0.4,
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", margin=dict(t=20, b=20),
                legend=dict(font=dict(color="white")),
            )
            st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown("#### Top 5 게임")
        top5 = stats.get("top5_games", [])
        if top5:
            df_top5 = pd.DataFrame([
                {"게임": g["name"][:20], "시간": g["playtime_hours"]}
                for g in top5
            ])
            fig2 = px.bar(
                df_top5, x="시간", y="게임", orientation="h",
                color="시간", color_continuous_scale="Plasma",
            )
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", margin=dict(t=20, b=20),
                coloraxis_showscale=False, yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🎮 내 추천 게임 보기", key="go_recs"):
        st.session_state.page = "recommendations"
        st.rerun()


# ── 페이지: 추천 ──────────────────────────────────────────────────────────────
def page_recommendations():
    recs = st.session_state.recs or {}
    user = st.session_state.user or {}
    username = user.get("username", "Unknown")

    hcol1, hcol2 = st.columns([6, 1])
    with hcol1:
        st.markdown(f"## 🎮 {username}님을 위한 추천")
        source = recs.get("source", "local")
        badge_color = "#57f287" if source == "snowflake" else "#fee75c"
        st.markdown(
            f'<span style="background:{badge_color};color:#111;border-radius:6px;padding:2px 10px;font-size:12px;font-weight:bold;">'
            f'{"Snowflake" if source == "snowflake" else "로컬"} 데이터</span>',
            unsafe_allow_html=True,
        )
    with hcol2:
        if st.button("← 대시보드"):
            st.session_state.page = "dashboard"
            st.rerun()

    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(["🎯 장르 기반 추천", "👥 협업 필터링", "💎 Hidden Gems", "🕸️ LightGCN (Graph)"])

    with tab1:
        st.markdown("**플레이타임이 많은 장르와 유사한 게임**")
        games = recs.get("genre_based", [])
        if games:
            cols = st.columns(2)
            for i, g in enumerate(games):
                with cols[i % 2]:
                    _game_card(g)
        else:
            st.info("추천 결과가 없습니다.")

    with tab2:
        st.markdown("**비슷한 취향의 유저들이 즐긴 게임**")
        games = recs.get("collab_based", [])
        if games:
            cols = st.columns(2)
            for i, g in enumerate(games):
                with cols[i % 2]:
                    _game_card(g)
        else:
            st.info("추천 결과가 없습니다.")

    with tab3:
        st.markdown("**숨겨진 명작 — Metacritic 87점+ 고평점 미소유 게임**")
        games = recs.get("hidden_gems", [])
        if games:
            cols = st.columns(2)
            for i, g in enumerate(games):
                with cols[i % 2]:
                    _game_card(g)
        else:
            st.info("추천 결과가 없습니다.")

    with tab4:
        st.markdown("**LightGCN — 유저-게임 그래프 컨볼루션 딥러닝 추천**")
        st.markdown(
            '<span style="background:#5865f2;color:white;border-radius:6px;padding:2px 10px;font-size:12px;">'
            'Graph Neural Network · SIGIR 2020</span>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        games = recs.get("graph_based", [])

        # 유저-게임 이분 그래프 시각화
        st.markdown("#### 유저-게임 상호작용 그래프")
        st.markdown(
            '<p style="color:#8b8fa8;font-size:13px;">'
            '⭐ 초록 별 = LightGCN 추천 게임 &nbsp;|&nbsp; '
            '🟡 노랑 = 현재 보유 게임 &nbsp;|&nbsp; '
            '엣지 굵기 = 플레이타임 강도</p>',
            unsafe_allow_html=True,
        )
        fig_graph = _build_lightgcn_graph(
            st.session_state.steam_id,
            st.session_state.owned_games,
            games,
        )
        st.plotly_chart(fig_graph, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 추천 결과")
        if games:
            cols = st.columns(2)
            for i, g in enumerate(games):
                with cols[i % 2]:
                    _game_card(g)
        else:
            st.info("추천 결과가 없습니다. (LightGCN 학습 중이거나 데이터 부족)")


# ── 라우터 ────────────────────────────────────────────────────────────────────
page = st.session_state.page
if page == "login":
    page_login()
elif page == "dashboard":
    page_dashboard()
elif page == "recommendations":
    page_recommendations()
