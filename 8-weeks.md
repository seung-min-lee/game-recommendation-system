# 8주차 개발 일지 (2026-05-13)

## 수정 및 추가 내용

---

### 1. 작품요약서 작성 (전시 패널용)

- **목적:** 작품전시회 패널 제출을 위한 공식 작품요약서 작성
- **구성 항목:** 작품개요 / 수행과정 / 상세내용 / 결과 및 기대효과 4개 섹션
- **분량 조정:** 1페이지 이내 제약 조건 하에 초안(6~7줄) 작성 후 피드백 반영하여 약 2배 분량으로 확장
- **작품개요**
  - Steam 플레이 이력·보유 게임·친구 네트워크를 분석하는 개인화 게임 추천 웹 서비스
  - LightGCN(그래프 신경망) + CBF(콘텐츠 기반 필터링) 하이브리드 추천 알고리즘 채택
  - Steam 계정 로그인만으로 즉시 사용 가능하며 친구 비교·장르 탐색·숨겨진 명작 발굴 등 다양한 탐색 경로 제공
- **수행과정**
  - ① Steam Web API로 보유 게임·플레이타임·리뷰·친구 목록 실시간 수집
  - ② Apache Airflow 수집 자동화 → dbt Bronze/Silver/Gold 3계층 변환 → Snowflake 적재
  - ③ LightGCN 유저-게임 이분 그래프 협업 필터링 모델 학습, CBF 장르·태그 유사도 모델 구현
  - ④ Streamlit 기반 UI 개발: 게임 카드 그리드, 캐러셀, LightGCN 그래프 시각화, 친구 비교 패널
  - ⑤ AWS EC2(백엔드 Flask API) + Streamlit Community Cloud(프론트엔드) 이중 배포
- **상세내용**
  - Steam OAuth 로그인, 보유 게임 자동 조회, DeepL API 리뷰 한국어 자동 번역
  - 4종 추천 탭: 장르 기반·유사 유저 기반·숨겨진 명작·LightGCN — 각 탭 일치도·할인율·Steam 스토어 이동 표시
  - LightGCN 이분 그래프 Plotly 시각화: 플레이타임 가중 엣지 두께, glow 효과, t-SNE/UMAP 임베딩 분포 전환 필터
  - 친구 비교 패널: 플레이타임 가중 코사인 유사도 기반 정렬, 장르 레이더 차트, 공통 게임 플레이타임 바 차트
  - 장르별 탐색: Steam 인기작 120개 다중 장르 AND 필터, 실시간 가격·할인 배치 조회
- **결과 및 기대효과**
  - 그래프 기반 협업 필터링(LightGCN) + CBF 융합 하이브리드 추천을 실서비스 수준으로 구현
  - 플레이타임·장르 취향 정밀 반영으로 기존 Steam 큐레이션 대비 개인화 만족도 향상 기대
  - 친구 네트워크 기반 소셜 추천으로 게임 발견의 다양성 증대
  - Steam 외 Epic Games·GOG 등 타 플랫폼 확장 및 게임 퍼블리셔 타겟 마케팅 도구로 활용 가능

---

### 2. AWS 아키텍처 설계도 PDF 검토 및 이미지 선정

- **배경:** 전시 패널 수행과정 섹션에 삽입할 아키텍처 이미지를 노션 저장 PDF 3개 중 1개로 선정
- **검토 대상 PDF**
  - `data_ingestion.pdf` — Steam API → Airflow 수집 → Snowflake Bronze 적재까지의 데이터 수집 파이프라인 세부 구조 (범위 좁음)
  - `전체_시스템_플로우_차트.pdf` — 수집 → 파이프라인 → 모델 학습 → Streamlit 서비스까지 전 흐름을 한 장으로 표현
  - `web_server.pdf` — EC2 Flask API 서버 + Streamlit Community Cloud 배포 구조 (배포 레이어만 표현)
- **선정 결과:** `전체_시스템_플로우_차트.pdf`
  - 선정 근거: 수행과정 전체 흐름(수집 → 처리 → 추천 → 배포)을 단일 이미지로 커버
  - 심사위원·관람객이 프로젝트 구조를 가장 직관적으로 파악할 수 있는 다이어그램

---

### 3. 노션 프로젝트 페이지 업데이트

#### 3-1. 주요 기능 테이블 신규 항목 4개 추가

- **나 & 친구 통계**
  - 총 플레이타임·보유 게임 수·최다 장르 요약 카드 (4개 지표)
  - 장르 분포 도넛 파이차트 (상위 8개 장르)
  - 최다 플레이 게임 Top 5 가로 바 차트
  - 친구 장르 레이더 차트 (나 + 유사도 상위 5명 오버레이)
  - 친구별 공통 게임 수 & 총 플레이타임 이중 y축 바 차트
- **친구 1:1 비교 패널**
  - 플레이타임 가중 코사인 유사도 기반 장르 유사도 % 헤더 (색상 3단계 표시)
  - 내 플레이타임 / 친구 플레이타임 / 내 보유 수 / 공통 게임 수 요약 카드 4개
  - 장르 레이더 차트 (나=빨강, 친구=파랑 오버레이)
  - 공통 보유 게임 플레이타임 비교 바 차트 (상위 10개)
  - 공통 게임 썸네일 그리드 (최대 12개, 클릭 시 Steam 스토어 이동)
- **LightGCN 그래프 시각화**
  - 유저-게임 이분 그래프 Plotly 렌더링 (유저 노드 x=0, 보유 게임 x=1, 추천 게임 x=2 컬럼 배치)
  - 플레이타임 `log1p` 정규화 기반 엣지 두께 차등 표현
  - 추천 게임 엣지 glow 이중 레이어 (반투명 두꺼운 선 + 불투명 얇은 선 중첩)
  - t-SNE / UMAP 임베딩 분포 시각화 전환 라디오 필터 탑재
- **장르별 탐색**
  - `data/popular_games.py` 에 정의된 Steam 인기작 120개 대상
  - `st.pills` 다중 선택 AND 필터 — 선택 장르 모두 포함한 게임만 표시
  - 실시간 Steam 가격·할인 정보 `get_price_info_batch` 배치 조회

#### 3-2. 기술 스택 Data/ML 항목 추가

- **`scikit-learn`**
  - PCA로 게임 임베딩 벡터를 15차원으로 선압축
  - t-SNE 직접 고차원 입력 시 계산량 폭증 문제를 PCA 전처리로 해결
- **`umap-learn`**
  - UMAP 알고리즘으로 15차원 → 2차원 임베딩 시각화
  - t-SNE 대비 대규모 데이터 처리 속도 우수, 전역 구조 보존

#### 3-3. 기타 개선 기록 UI/프론트엔드 항목 추가

- **게임 카드 4열 wrap 그리드 전환**
  - 기존: `display:flex; overflow-x:auto` 가로 스크롤 방식
  - 변경: `flex-wrap:wrap; width:calc(25% - 12px)` 4열 고정 그리드
  - 행 수 기반 동적 높이 계산: `rows = max(1, (len(games)+3)//4)`, `height = rows * 330 + 40`
- **친구 유사도 정렬 방식 변경 (Jaccard → 코사인)**
  - `_genre_vector()`: 플레이타임 가중 장르 벡터 생성 공통 함수 신설
  - `_cosine_sim()`: 두 벡터 간 코사인 유사도 계산 공통 함수 신설
  - 적용 범위: 사이드바 정렬, 사이드바 유사도 %, 통계 탭 랭킹, 친구 비교 패널
- **LightGCN 그래프 렌더링 개선**
  - 기존: 노드·엣지 각각 개별 trace → 수백 개 trace 생성으로 렌더링 지연
  - 변경: 타입별 batch trace 묶음 (~10개 trace) → 렌더링 속도 대폭 개선
  - 엣지 색상: 타 유저 연결(노란 `rgba(255,220,50,0.35)`) / 보유 게임(파란 `rgba(120,180,255,0.70)`) / 추천 게임(빨간 `rgba(255,80,80,0.90)`)
  - 배경색 `#0e0e0e` 적용으로 glow 효과 대비 강화, 그래프 높이 700px
- **LightGCN expander 접기/펼치기**
  - `st.expander("🕸️ LightGCN 그래프 & 임베딩 시각화")` 로 감싸 캐러셀 아래 배치
  - 기본 접힌 상태로 페이지 스크롤 UX 개선
- **t-SNE/UMAP 임베딩 분포 시각화**
  - `_render_embedding_viz(algo, rec_ids)` 함수로 두 알고리즘 통합 처리
  - 노드 유형별 구분: 추천 게임(빨간 별+glow) / 보유 게임(파란 사각형) / 일반 게임(장르색 원)
  - 세션 캐시 키 분리: `_embed_tsne_cache`, `_embed_umap_cache` 독립 저장
  - 그래프 하단에 유사 유저 유사도 순위 테이블 병기
- **스트리머 하드코딩 fallback 추가**
  - 문제: shroud·Ninja 등 유명 스트리머 Steam 프로필 비공개 → `get_owned_games()` 빈 배열 반환 → 그래프 유저 3명 미만으로 표시 불가
  - 해결: `data/public_users.py` 신규 생성
    - `KNOWN_PUBLIC_USERS`: 10명 스트리머 Steam ID → 표시 이름 매핑
    - `KNOWN_PUBLIC_GAMES`: 스트리머별 플레이타임 추정 기반 게임 목록 하드코딩
  - 우선순위: 하드코딩 데이터를 기본값으로 사용, API 성공 시 덮어쓰기
  - "🔄 유저 새로고침" 버튼 추가로 `_graph_users_cache` 수동 초기화 지원
- **장르별 탐색 탭 신설**
  - `data/popular_games.py`: `_g(app_id, name, genres, rank)` 헬퍼로 120개 게임 정의, 중복 app_id 제거(최저 rank 우선), `ALL_GENRES` 20개 장르 리스트
  - `st.pills` 다중 선택 UI — 미선택 시 전체 상위 24개 표시, 조건 불일치 시 안내 메시지
  - 기존 대시보드 장르 탐색 섹션 제거 후 추천 페이지 탭으로 이전

---

### 4. KubernetesPodOperator 고도화 가능성 검토

- **배경:** 멘토님 피드백 — EKS 환경에서 PythonOperator는 잘 사용하지 않음
- **문제 정의**
  - PythonOperator: 모든 태스크가 Airflow Worker 동일 Python 환경 실행
  - 의존성 충돌 위험, 태스크 간 리소스 격리 불가, 장애 격리 어려움
- **KubernetesPodOperator 전환 시 이점**
  - 태스크마다 독립 Kubernetes Pod 실행 → 완전한 환경 격리
  - Docker 이미지·CPU·메모리 리소스를 태스크별로 개별 지정 가능
  - Pod 장애가 다른 태스크에 영향 없음
- **진행 보류 근거**
  - EKS 클러스터 현재 운영 여부 불확실 (비용 문제로 중단 가능성)
  - 태스크별 Docker 이미지 빌드·푸시·유지 관리 오버헤드 발생
  - K8s 환경 없이 로컬 테스트·디버깅 극히 어려움
  - 배포 완료 상태에서 인프라 레이어 변경 시 전체 파이프라인 영향 리스크
- **결론:** 기술적으로 가능하나 현 캡스톤 일정·비용 제약상 보류, 보고서·면접에서 고도화 과제로 서술
  - 서술 예시: *"EKS 환경에서는 KubernetesPodOperator 적용이 권장되나, 프로젝트 일정 및 비용 제약으로 PythonOperator로 구현하였으며 향후 고도화 과제로 남겨둠"*

---

### 5. 알고리즘 수정 및 추가

---

#### 5-1. 유사도 계산 알고리즘 변경 (Jaccard → 플레이타임 가중 코사인 유사도)

- **변경 배경**
  - 기존 Jaccard 유사도: 장르 보유 여부(0/1)만 반영 → 플레이 1시간과 1,000시간을 동일하게 처리하는 문제
  - 플레이타임 비중이 클수록 해당 장르 선호도가 높다는 점을 반영하지 못함
- **변경 내용**
  - `_genre_vector(games)` 함수 신설
    - 입력: 유저 보유 게임 리스트 (app_id, playtime_minutes, genres 포함)
    - 처리: 각 게임의 장르별로 플레이타임을 누적 합산하여 장르 벡터 생성
    - 출력: `{장르명: 누적 플레이타임}` 형태의 딕셔너리
  - `_cosine_sim(v1, v2)` 함수 신설
    - 입력: 두 유저의 장르 벡터
    - 처리: 공통 장르 키 기준 내적 계산 → L2 노름으로 나눠 코사인 유사도 산출
    - 출력: 0.0 ~ 1.0 사이의 유사도 값 (1에 가까울수록 취향 유사)
  - 예시: 내가 FPS 장르에 500시간, 친구가 FPS 장르에 480시간 플레이 시 → 높은 코사인 유사도 산출
- **적용 범위**
  - 사이드바 친구 목록 정렬 기준 (유사도 내림차순)
  - 사이드바 친구 카드 유사도 % 표시
  - 나 & 친구 통계 탭 친구 랭킹
  - 친구 1:1 비교 패널 장르 유사도 헤더

---

#### 5-2. LightGCN 그래프 알고리즘 — 플레이타임 가중 엣지 및 시각화 개선

- **LightGCN 개요**
  - Light Graph Convolutional Network (SIGIR 2020) 기반 협업 필터링
  - 유저-게임 이분 그래프(Bipartite Graph) 구조: 유저 노드와 게임 노드를 엣지로 연결
  - 그래프 상에서 메시지 전파(Message Passing)를 통해 유저·게임 임베딩 학습
  - 학습된 임베딩 내적으로 미소유 게임 추천 점수 산출

- **플레이타임 가중 엣지 (`log1p` 정규화)**
  - 변경 전: 유저-게임 연결 엣지 두께 모두 동일 → 캐주얼 플레이어와 헤비 플레이어 구분 불가
  - 변경 후: 플레이타임에 `log1p` 함수 적용 후 최대값으로 정규화 → 엣지 두께를 0.5 ~ 4.0 범위로 차등 표현
  - `log1p` 사용 이유: 플레이타임 분포가 극단적으로 치우쳐 있어 로그 스케일로 완화 (예: 1시간과 10,000시간 차이를 선형 그대로 쓰면 시각적 구분 불가)
  - 수식: `edge_width = 0.5 + 3.5 * (log1p(playtime) / log1p(max_playtime))`

- **Batch Trace 렌더링 최적화**
  - 변경 전: 엣지·노드 각각 개별 Plotly trace 생성 → 유저 10명 × 게임 50개 = 수백 개 trace → 렌더링 지연 심각
  - 변경 후: 엣지를 연결 유형별 3개 batch trace로 통합
    - 타 유저 연결 엣지: `rgba(255,220,50,0.35)` 노란색 반투명
    - 내 보유 게임 연결 엣지: `rgba(120,180,255,0.70)` 파란색
    - 내 추천 게임 연결 엣지: `rgba(255,80,80,0.90)` 빨간색 강조
  - 노드도 유형별 batch scatter trace로 통합 (유저·보유 게임·추천 게임·기타 게임 4종)

- **Glow 이중 레이어 효과**
  - 추천 게임 엣지에 반투명 두꺼운 선(width=8, opacity=0.3) + 불투명 얇은 선(width=2, opacity=0.9) 중첩
  - 배경색 `#0e0e0e` 적용으로 glow 대비 극대화
  - 추천 게임 노드: 빨간 별(⭐) 라벨로 일반 게임과 시각적 구분

- **3열 컬럼 레이아웃**
  - `x=0`: 유저 노드 (세로 균등 배치)
  - `x=1`: 보유 게임 및 기타 게임 노드
  - `x=2`: 추천 게임 노드 (우측 분리, 세로 균등 배치)
  - 컬럼 구분선(`shapes`) 추가로 이분 그래프 구조 시각적 명확화

---

#### 5-3. t-SNE / UMAP 임베딩 분포 시각화 알고리즘

- **목적**
  - LightGCN이 학습한 게임 임베딩 벡터를 2차원으로 투영하여 게임 간 유사도 분포를 직관적으로 시각화
  - 추천 게임이 취향 군집 내에 위치하는지 확인 → 추천 결과의 신뢰성 시각적 검증

- **처리 파이프라인**
  - ① 게임별 임베딩 벡터 수집 (장르·태그 기반 원-핫 인코딩 또는 LightGCN 학습 임베딩)
  - ② `sklearn.decomposition.PCA`: 고차원 벡터 → 15차원으로 선압축
    - 이유: t-SNE·UMAP에 고차원 직접 입력 시 계산량 폭증 및 노이즈 증가 방지
  - ③-A `sklearn.manifold.TSNE`: 15차원 → 2차원 (perplexity=30, n_iter=300)
    - t-SNE 특성: 국소 구조(가까운 점들의 군집) 보존에 강점, 전역 구조는 상대적으로 약함
  - ③-B `umap.UMAP`: 15차원 → 2차원 (n_neighbors=15, min_dist=0.1)
    - UMAP 특성: 전역·국소 구조 동시 보존, 대규모 데이터 처리 속도 t-SNE 대비 우수

- **시각화 구현 (`_render_embedding_viz`)**
  - 노드 유형별 시각적 구분
    - 추천 게임: 빨간 별 마커 + glow 원형 후광 오버레이
    - 보유 게임: 파란 사각형 마커
    - 일반 게임: 장르별 색상 원형 마커 (20개 장르 색상 팔레트)
  - 호버 툴팁: 게임명·장르·플레이타임 표시
  - 하단에 유사 유저 유사도 순위 테이블 병기

- **세션 캐시 분리**
  - `st.session_state["_embed_tsne_cache"]`: t-SNE 결과 저장
  - `st.session_state["_embed_umap_cache"]`: UMAP 결과 저장
  - 알고리즘 전환 시 기존 캐시 재사용으로 재계산 방지

- **UI 전환 구조**
  - LightGCN expander 내 라디오 버튼: `🕸️ LightGCN | 🧭 t-SNE | 🗺️ UMAP`
  - 선택에 따라 `_build_lightgcn_graph()` 또는 `_render_embedding_viz(algo)` 분기 호출

---

#### 5-4. 추천 알고리즘 4종 구조 및 일치도 표시 통일

- **장르 기반 추천 (CBF)**
  - 유저 플레이타임 기반 상위 선호 장르 추출
  - Snowflake Gold 레이어 `recommend_cbf` 모델 결과 활용
  - 장르 가중치 = 해당 장르 총 플레이타임 / 전체 플레이타임
  - 미소유 게임 중 선호 장르 일치 점수 합산 Top 10 반환

- **유사 유저 기반 추천 (협업 필터링)**
  - Snowflake Gold 레이어 `recommend_cf` 모델 결과 활용
  - Jaccard 유사도로 유사 유저 선별 → 해당 유저들의 보유 게임 중 내 미소유 게임 score 합산
  - `QUALIFY ROW_NUMBER() OVER (PARTITION BY steam_id ORDER BY score DESC) <= 10`

- **숨겨진 명작 (Hidden Gems)**
  - 조건 ①: 내 선호 장르 Top 3에 포함
  - 조건 ②: Metacritic 점수 ≥ 87
  - 조건 ③: 미소유 게임
  - score = 장르 매칭 수 × (metacritic / 100.0) → Top 10 반환

- **LightGCN 추천**
  - 유저-게임 이분 그래프에서 그래프 합성곱 레이어로 임베딩 전파
  - 최종 유저 임베딩과 미소유 게임 임베딩의 내적 → 추천 점수 산출

- **4종 탭 공통 UI 통일**
  - 모든 탭: `_render_carousel()` + `_show_reviews_panel()` 구조로 통일
  - 각 게임 카드: 일치도(match_percent) / 할인율 / Steam 스토어 이동 버튼 표시
  - 게임 카드 레이아웃: 4열 flex-wrap 그리드 (`width: calc(25% - 12px)`)

---

#### 5-5. 그래프 유저 선정 알고리즘 (Fallback 우선순위 로직)

- **문제**
  - shroud·Ninja·Pokimane 등 유명 스트리머 Steam 프로필 비공개 설정
  - `get_owned_games(steam_id)` API 호출 시 빈 배열 반환
  - 유효 유저 3명 미만 → LightGCN 그래프 렌더링 불가
  - 기존 더미 데이터(DUMMY_OWNED_GAMES)로 폴백 시 실제 유저처럼 보이지 않는 문제

- **해결 — `data/public_users.py` 신규 생성**
  - `KNOWN_PUBLIC_USERS`: 10명 스트리머 Steam ID → 표시 이름 딕셔너리
    - shroud, summit1g, Lirik, Sodapoppin, xQc, TimTheTatman, Pokimane, Ninja, GabeN, CohhCarnage
  - `KNOWN_PUBLIC_GAMES`: 스트리머별 실제 활동 기반 플레이타임 추정 하드코딩
    - 예) shroud: CS2(85,000분), PUBG(32,000분), Apex(18,000분), R6S(12,000분)
    - 예) Pokimane: Stardew Valley(15,000분), Hollow Knight(8,000분), Hades(6,000분)
    - 예) CohhCarnage: Witcher 3(30,000분), BG3(25,000분), Cyberpunk(20,000분)

- **`_fetch_graph_users(steam_id)` 우선순위 로직**
  - ① `result = {**KNOWN_PUBLIC_GAMES}` — 하드코딩 데이터를 기본값으로 먼저 적재
  - ② Steam API `get_owned_games(uid)` 호출 — 성공(비공개 아님) 시 `result[uid]` 덮어쓰기
  - ③ 로그인 유저 친구 목록 `get_friend_list()` 조회 → 친구 게임도 API 호출 후 병합
  - ④ 최종 유저 풀: 하드코딩 스트리머 10명 + API 성공 친구들 혼합
  - ⑤ 결과 `st.session_state["_graph_users_cache"]` 저장 → 재접근 시 재호출 방지

- **🔄 유저 새로고침 버튼**
  - `st.session_state["_graph_users_cache"]` 및 `st.session_state["_graph_user_names"]` 삭제
  - 버튼 클릭 시 즉시 `st.rerun()` 호출 → 최신 데이터로 그래프 재구성

---

### 6. 버그 수정 및 커밋 이력 (7주차 이월 포함)

| 커밋 | 내용 |
|---|---|
| `1d0ee22` | 그래프 유저 fallback 추가: `KNOWN_PUBLIC_GAMES` 하드코딩 기본값, 🔄 새로고침 버튼 신설 |
| `3ff1e64` | 더미 유저 완전 제거 → 실제 Steam 친구 목록 + 공개 유저(`KNOWN_PUBLIC_USERS`) 혼합 방식으로 교체 |
| `d31980b` | LightGCN expander 내 UMAP/t-SNE 라디오 필터 추가, `_render_embedding_viz` 함수 통합 |
| `6d8941a` | LightGCN 그래프 캐러셀 하단으로 이동, `st.expander` collapsible 적용 |
| `975dc01` | LightGCN 그래프 전면 재설계: batch trace, glow 이중 레이어, 플레이타임 가중 엣지, 배경 `#0e0e0e` |
