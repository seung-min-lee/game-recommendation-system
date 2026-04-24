# 🎮 Game Finder — 사용자 맞춤 게임 추천 시스템

> 캡스톤 디자인 프로젝트 | Steam 플레이 기록 기반 AI 게임 추천

## 아키텍처

```
[React/HTML 프론트엔드]
        ↓ HTTPS
[AWS ALB → Nginx → EC2 Flask API]
        ↓              ↓              ↓
[ElastiCache Redis]  [RDS MySQL]  [Airflow DAG 트리거]
                                        ↓
                              [Steam API 데이터 수집]
                                        ↓
                              [Snowflake Bronze → Silver → Gold]
                                        ↓
                              [Flask API → 프론트엔드 추천 결과]
```

## 기술 스택

| 영역 | 기술 |
|------|------|
| 프론트엔드 | Streamlit 1.35.0 (Python 3.8.10), HTML/CSS/JS |
| 백엔드 API | Python 3.11 + Flask + Gunicorn, Docker (python:3.11-slim) |
| ML 모델 | LightGCN (협업 필터링 CF), Content-Based Filtering (CBF) |
| 데이터 분석 | plotly, pandas, scipy, numpy |
| 번역 | deep-translator (GoogleTranslator) — 비한국어 리뷰 자동 번역 |
| 외부 API | Steam Web API (유저 정보, 게임 목록, 리뷰) |
| 데이터 웨어하우스 | Snowflake GAME_DW (Bronze / Silver / Gold 3-tier) |
| 데이터 변환 | dbt (Silver/Gold 레이어 SQL 모델링) |
| 파이프라인 | Apache Airflow (AWS EKS) — game_pipeline DAG |
| 인프라 | AWS EC2 t3.medium (ap-northeast-2), ElastiCache Redis, RDS MySQL |
| 컨테이너 | Docker + Docker Hub (gamefinder-api:latest) |
| CI/CD | GitHub Actions → Docker Hub → EC2 SSH 자동 배포 |
| 배포 | Streamlit Community Cloud (프론트) + AWS EC2 (API) |

## 추천 알고리즘

### 1. CBF — 콘텐츠 기반 필터링
- 유저의 장르별 플레이타임을 가중치로 사용
- `LATERAL FLATTEN(genres)`으로 게임별 장르 분해 → 장르별 total_hours 합산
- 선호 장르와 일치하는 미소유 게임 similarity 점수 합산 → Top 10
- Snowflake `GOLD.RECOMMEND_CBF` 테이블

### 2. CF — 협업 필터링 (Jaccard Similarity)
- 같은 게임을 플레이한 유저 간 Jaccard 유사도 계산
- `jaccard_sim = 공통 게임 수 / 내 전체 게임 수`
- 유사 유저의 게임 중 미소유 게임을 score 합산 → Top 10
- Snowflake `GOLD.RECOMMEND_CF` 테이블

### 3. Hidden Gems — 숨겨진 명작
- 플레이타임 기준 선호 장르 Top 3 추출
- Metacritic 87점 이상 + 선호 장르 + 미소유 게임 필터링
- `score = 장르 매칭 수 × (metacritic / 100.0)` → Top 10
- Snowflake `GOLD.HIDDEN_GEMS` 테이블

### 4. LightGCN — 그래프 기반 협업 필터링
- 유저-게임 이분 그래프에서 Graph Convolutional Network 학습
- 유저와 게임의 임베딩을 여러 레이어에 걸쳐 전파·집계
- 플레이 기록이 적은 유저에게도 효과적인 추천 제공
- Snowflake Gold Layer를 통해 추천 결과 서빙

## 데이터 파이프라인 (Airflow DAG)

```
ingest_game_metadata → ingest_user_games → transform_silver → build_gold_recommendations
```

1. **ingest_game_metadata** — Steam/RAWG API로 게임 메타데이터 수집 → Bronze
2. **ingest_user_games** — Steam API로 유저 플레이 기록 수집 → Bronze
3. **transform_silver** — Bronze 정제 → Silver (USER_GAME_STATS, GAME_FEATURES)
4. **build_gold_recommendations** — CF / CBF / Hidden Gems 추천 생성 → Gold

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/health` | 헬스체크 |
| GET | `/api/user/<steam_id>` | 유저 프로필 조회 |
| GET | `/api/stats/<steam_id>` | 플레이 통계 |
| GET | `/api/recommend/<steam_id>` | 추천 결과 (Redis → Snowflake → 로컬 폴백) |
| GET | `/api/recommend/<steam_id>/status` | DAG 실행 상태 폴링 |

## 추천 요청 처리 흐름

```
GET /api/recommend/<steam_id>
  1. Redis 캐시 확인 → hit: 즉시 반환
  2. Snowflake Gold Layer 쿼리 → 결과 있으면 Redis 저장 후 반환
  3. Airflow DAG 트리거 → dag_run_id 반환 (프론트가 /status 폴링)
  4. 로컬 추천 폴백 (개발/테스트용)
```

## 프로젝트 구조

```
├── streamlit_app.py            # Streamlit 프론트엔드 메인
├── requirements.txt
├── frontend/                   # 화면 HTML
│   ├── login.html
│   ├── dashboard.html
│   └── recommendations.html
├── services/                   # 외부 서비스 연동
│   ├── steam_service.py        # Steam API
│   ├── snowflake_service.py    # Snowflake Gold Layer 쿼리
│   ├── cache_service.py        # ElastiCache Redis
│   └── airflow_service.py      # Airflow REST API 트리거
├── ml/                         # ML 모델
│   ├── lightgcn.py             # LightGCN 그래프 추천
│   └── recommender.py          # 로컬 추천 로직 (폴백)
├── config/
│   └── config.py               # 환경변수 설정
├── data/
│   └── dummy_data.py
├── infra/                      # 배포 인프라
│   ├── app.py                  # Flask API 진입점
│   ├── Dockerfile
│   ├── requirements-flask.txt
│   └── aws_setup.sh            # EC2 환경 세팅 스크립트
├── gamefinder_dbt/             # dbt 모델 (Bronze→Silver→Gold)
│   └── models/
│       ├── sources.yml
│       ├── silver/             # user_game_stats, game_features
│       └── gold/               # recommend_cf, recommend_cbf, hidden_gems
├── docs/                       # 아키텍처 다이어그램 PDF
├── screenshots/                # 앱 UI 스크린샷
├── scripts/
│   └── notion_update.py        # Notion 문서 자동화
└── .github/workflows/
    └── deploy.yml              # GitHub Actions CI/CD
```
