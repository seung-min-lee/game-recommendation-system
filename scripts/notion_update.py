# -*- coding: utf-8 -*-
import os
import requests

TOKEN = os.environ.get("NOTION_TOKEN", "")
PAGE_ID = "34b7e0a5-4809-8163-9f73-f65b56c989b6"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def txt(content, bold=False):
    t = {"type": "text", "text": {"content": content}}
    if bold:
        t["annotations"] = {"bold": True}
    return t

def heading2(content):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [txt(content)]}}

def quote(content):
    return {"object": "block", "type": "quote", "quote": {"rich_text": [txt(content)]}}

def bullet(content):
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [txt(content)]}}

def toggle(title, children):
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {"rich_text": [txt(title)], "children": children},
    }

def table(width, header, rows):
    def row(cells):
        return {"type": "table_row", "table_row": {"cells": [[txt(c)] for c in cells]}}
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": [row(header)] + [row(r) for r in rows],
        },
    }

# 기존 블록 삭제
res = requests.get(f"https://api.notion.com/v1/blocks/{PAGE_ID}/children", headers=HEADERS)
blocks = res.json().get("results", [])
for b in blocks:
    requests.delete(f"https://api.notion.com/v1/blocks/{b['id']}", headers=HEADERS)
print(f"삭제된 블록: {len(blocks)}개")

# 새 블록 추가
children = [
    quote("Steam ID로 로그인해 보유 게임 분석, 리뷰 탐색, 친구 게임 비교, 맞춤 게임 추천까지 한 번에 제공하는 대시보드"),
    heading2("📌 프로젝트 개요"),
    table(2,
        ["항목", "내용"],
        [
            ["프로젝트명", "Game Finder"],
            ["개발 기간", "2026.03 ~ 2026.04"],
            ["개발 인원", "1인"],
            ["개발 환경", "Python 3.11, Streamlit 1.x, Windows 11"],
            ["주요 API", "Steam Web API, Google Translate (deep_translator)"],
            ["배포 환경", "Streamlit Community Cloud"],
        ],
    ),
    heading2("🛠 기술 스택"),
    toggle("Frontend", [
        bullet("Streamlit — 페이지 레이아웃, 컴포넌트 구성"),
        bullet("HTML/CSS/JS (components.html) — 리뷰 카드 그리드, 접기/펼치기 인터랙션"),
    ]),
    toggle("Backend / Data", [
        bullet("Python — 전체 로직"),
        bullet("Steam Web API — 유저 정보, 보유 게임, 친구 목록, 리뷰"),
        bullet("deep_translator (GoogleTranslator) — 비한국어 리뷰 자동 번역"),
    ]),
    toggle("배포", [
        bullet("Streamlit Cloud — secrets.toml로 API 키 관리"),
    ]),
    heading2("📱 주요 기능"),
    table(3,
        ["기능", "설명", "상태"],
        [
            ["Steam 로그인", "Steam ID 입력으로 실제 유저 검증", "✅"],
            ["보유 게임 목록", "플레이타임 순 정렬, 장르 태그, 스토어 링크", "✅"],
            ["리뷰 분석", "최대 160개 리뷰 수집, 정렬(👍/👎/⏱), 16페이지, 자동 번역", "✅"],
            ["친구 게임 비교", "공개 친구 목록 기준 보유 게임 교집합 시각화", "✅"],
            ["게임 추천", "장르 기반 필터, 가격 정보, 할인율 표시", "✅"],
        ],
    ),
    heading2("🔥 핵심 구현 포인트"),
    toggle("리뷰 카드 그리드 (equal height + 접기/펼치기)", [
        bullet("문제: Streamlit의 st.markdown은 HTML을 샌드박싱해 JS 동작 불가"),
        bullet("해결: st.components.v1.html()로 iframe 내에서 CSS Grid + JS 구현"),
        bullet("grid-auto-rows로 동일 행 높이 강제"),
        bullet("flex: 1 1 0 + min-height: 0 → overflow 정상 작동"),
        bullet("JS classList.toggle('expanded') → 카드 높이 transition"),
    ]),
    toggle("다국어 리뷰 자동 번역", [
        bullet("문제: 중국어·일본어 리뷰가 한국어로 인식되어 번역 생략"),
        bullet("해결: _is_korean()에 유니코드 범위 명시 (중국어: 一~鿿, 일본어: ぀~ヿ)"),
        bullet("CJK 비율 ≥ 5%면 무조건 번역 대상으로 처리"),
        bullet("번역 방식: concurrent.futures, workers=5, 3회 retry, 60초 timeout"),
    ]),
    toggle("160개 리뷰 수집 (16페이지)", [
        bullet("문제: Steam 리뷰 API cursor 방식 페이지네이션이 불안정"),
        bullet("해결: helpful 100개 + recent 100개 병렬 수집 후 recommendationid 기준 중복 제거"),
        bullet("결과: 최대 160개 고유 리뷰 확보"),
    ]),
    toggle("실제 Steam ID 검증", [
        bullet("문제: 존재하지 않는 ID도 더미 데이터로 로그인 허용"),
        bullet("해결: get_user_summary() API 응답 players[] 비어있으면 None 반환"),
        bullet("get_owned_games() 더미 폴백 완전 제거"),
    ]),
    toggle("세션 캐시 관리", [
        bullet("문제: 로그아웃 후 다른 계정 로그인 시 이전 리뷰 캐시(_rv_{app_id}) 잔존"),
        bullet("해결: 로그아웃 시 st.session_state 전체 키 삭제"),
    ]),
    heading2("🐛 트러블슈팅 로그"),
    table(4,
        ["날짜", "문제", "원인", "해결"],
        [
            ["04/10", "리뷰 카드 높이 불일치", "CSS float 레이아웃 한계", "CSS Grid + grid-auto-rows"],
            ["04/12", "JS expand/collapse 미동작", "st.markdown HTML 샌드박싱", "components.html iframe"],
            ["04/15", "중국어 리뷰 번역 안 됨", "CJK 유니코드 범위 누락", "명시적 범위 체크 추가"],
            ["04/18", "리뷰 10개 이상 안 불러와짐", "cursor 페이지네이션 불안정", "parallel helpful+recent 수집"],
            ["04/20", "로그아웃 후 캐시 잔존", "명시적 키만 삭제하던 방식", "전체 세션 스테이트 초기화"],
            ["04/22", "가짜 Steam ID 로그인 허용", "더미 데이터 폴백 존재", "API 검증만 사용, 폴백 제거"],
        ],
    ),
    heading2("💬 회고"),
    toggle("잘한 점", [
        bullet("Streamlit의 한계(HTML 샌드박싱)를 iframe으로 우회하는 방법을 직접 찾아냄"),
        bullet("API 응답 속도 개선을 위해 concurrent.futures로 병렬 처리 구현"),
        bullet("번역 실패 시 원문 유지하는 방어적 처리로 UX 안정성 확보"),
    ]),
    toggle("아쉬운 점", [
        bullet("Steam API의 private 계정 제한으로 친구 기능 테스트에 한계"),
        bullet("리뷰 cursor 페이지네이션 미지원으로 160개가 실질적 상한선"),
    ]),
    toggle("다음에 하고 싶은 것", [
        bullet("장르 기반 ML 추천 모델 연동"),
        bullet("리뷰 감성 분석 시각화 (긍/부정 워드클라우드)"),
        bullet("다중 유저 비교 기능"),
    ]),
    heading2("📎 링크 모음"),
    bullet("Steam Web API 공식 문서: https://steamcommunity.com/dev"),
    bullet("deep_translator PyPI: https://pypi.org/project/deep-translator/"),
    bullet("Streamlit 공식 문서: https://docs.streamlit.io"),
    bullet("GitHub 레포: (여기에 링크 추가)"),
    bullet("배포 앱 (Streamlit Cloud): (여기에 링크 추가)"),
]

res = requests.patch(
    f"https://api.notion.com/v1/blocks/{PAGE_ID}/children",
    headers=HEADERS,
    json={"children": children},
)
data = res.json()
if data.get("object") == "error":
    print("ERROR:", data.get("message"))
else:
    print(f"완료! {len(data.get('results', []))}개 블록 추가됨")
