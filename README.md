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
| 백엔드 | Python + Flask, Gunicorn, Docker |
| 인프라 | AWS EC2 (t3.medium), ALB, Nginx |
| 데이터 웨어하우스 | Snowflake (Bronze / Silver / Gold) |
| 파이프라인 | Apache Airflow (Docker Compose on EC2) |
| 캐시 | ElastiCache Redis |
| DB | RDS MySQL 8.0 |
| CI/CD | GitHub Actions → Docker Hub → EC2 |

## 추천 알고리즘

### 1. CBF — 콘텐츠 기반 필터링
- 유저의 장르별 플레이타임을 가중치로 사용
- Snowflake `GOLD.RECOMMEND_CBF` 테이블

### 2. CF — 협업 필터링
- 공통 게임 수 기반 Jaccard 유사도로 유사 유저 탐색
- Snowflake `GOLD.RECOMMEND_CF` 테이블

### 3. Hidden Gems — 숨겨진 명작
- Metacritic 87점 이상 + 선호 장르 + 미소유 게임
- Snowflake `GOLD.HIDDEN_GEMS` 테이블

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
├── app.py                  # Flask 앱 진입점
├── config.py               # 환경변수 설정
├── steam_service.py        # Steam API 연동
├── snowflake_service.py    # Snowflake Gold Layer 쿼리
├── cache_service.py        # ElastiCache Redis
├── airflow_service.py      # Airflow REST API 트리거
├── recommender.py          # 로컬 추천 로직 (폴백)
├── Dockerfile
├── requirements.txt
├── gamefinder_dbt/         # dbt 모델 (Bronze→Silver→Gold SQL)
│   └── models/
│       ├── sources.yml
│       ├── silver/
│       └── gold/
└── .github/workflows/
    └── deploy.yml          # GitHub Actions CI/CD
```
