# 8주차 개발 일지 (2026-05-13)

## 오늘 수정 및 추가 내용

---

### 1. 작품요약서 작성 (전시 패널용)

- 작품전시회 패널 제출용 **작품요약서** 초안 작성
- 구성 항목: 작품개요 / 수행과정 / 상세내용 / 결과 및 기대효과
- 1페이지 이내 제약으로 초안 6~7줄 → 피드백 반영 후 **약 2배 분량 확장**

#### 최종 작품요약서 내용 요약

| 항목 | 내용 |
|---|---|
| 작품개요 | Steam 플레이 이력·친구 네트워크 분석 기반 개인화 게임 추천 웹 서비스. LightGCN + CBF 하이브리드 추천 |
| 수행과정 | Steam API 수집 → Airflow·dbt Bronze/Silver/Gold 파이프라인 → 모델 학습 → Streamlit UI → AWS EC2 + Streamlit Cloud 배포 |
| 상세내용 | Steam 로그인 연동, 4종 추천 탭, LightGCN 이분 그래프 시각화, t-SNE/UMAP 임베딩, 친구 유사도 비교 패널, 장르별 탐색, 통계 대시보드 |
| 결과 및 기대효과 | 그래프 기반 협업 필터링 + CBF 융합 하이브리드 추천 구현, 친구 네트워크 활용 소셜 추천으로 게임 발견 다양성 증대, 타 플랫폼 확장 가능성 |

---

### 2. AWS 아키텍처 설계도 PDF 검토

- 노션에 저장된 PDF 3개 검토 및 수행과정 이미지 선정
  - `data_ingestion.pdf` — Steam API → Airflow → Snowflake 파이프라인 세부
  - `전체_시스템_플로우_차트.pdf` — 전체 시스템 흐름 (수집 → 파이프라인 → 모델 → 서비스)
  - `web_server.pdf` — EC2 / Streamlit 배포 구조
- **선정:** `전체_시스템_플로우_차트.pdf` — 수행과정 전 흐름을 한 장으로 커버하여 전시 패널 이미지로 최적

---

### 3. 노션 프로젝트 페이지 업데이트

#### 3-1. 주요 기능 테이블 신규 항목 추가

| 추가 기능 | 내용 |
|---|---|
| 나 & 친구 통계 | 총 플레이타임·보유 게임 수·최다 장르 요약 카드, 도넛 파이차트, Top 5 바 차트, 친구 장르 레이더 차트, 이중 y축 바 차트 |
| 친구 1:1 비교 패널 | 플레이타임 가중 코사인 유사도, 장르 레이더 차트, 공통 게임 플레이타임 바 차트, 썸네일 그리드 (Steam 스토어 이동) |
| LightGCN 그래프 시각화 | 유저-게임 이분 그래프, 플레이타임 가중 엣지, glow 효과, t-SNE/UMAP 임베딩 분포 전환 필터 |
| 장르별 탐색 | 120개 인기작 다중 장르 AND 필터, 실시간 Steam 가격·할인 정보 |

#### 3-2. 기술 스택 Data/ML 항목 추가

- `scikit-learn` — PCA 차원 축소 (t-SNE 전처리)
- `umap-learn` — UMAP 임베딩 시각화

#### 3-3. 기타 개선 기록 UI/프론트엔드 항목 추가

- 게임 카드 4열 wrap 그리드 전환 (`flex-wrap: wrap`, `width: calc(25% - 12px)`)
- 친구 유사도 정렬 Jaccard → 플레이타임 가중 코사인 유사도
- LightGCN batch trace 렌더링 + glow 이중 레이어 + 플레이타임 가중 엣지 두께
- `st.expander` 접기/펼치기 + 캐러셀 아래 배치
- t-SNE/UMAP 임베딩 분포 시각화 (`_render_embedding_viz`)
- 스트리머 하드코딩 fallback (`data/public_users.py`, `KNOWN_PUBLIC_GAMES`)
- 장르별 탐색 탭 (`data/popular_games.py` 120개 인기작)

---

### 4. KubernetesPodOperator 고도화 가능성 검토

- 멘토님 피드백 항목: EKS 환경에서 PythonOperator → KubernetesPodOperator 전환
- 검토 결과: **기술적으로 가능하나 현 일정·비용 상황에서 진행 보류**

| 검토 항목 | 판단 |
|---|---|
| EKS 실제 운영 여부 | 비용 문제로 중단 가능성 — 테스트 환경 불확실 |
| Docker 이미지 관리 | 태스크별 이미지 빌드·푸시 오버헤드 증가 |
| 로컬 테스트 | K8s 없이 KubernetesPodOperator 검증 매우 어려움 |
| 캡스톤 리스크 | 배포 완료 상태에서 인프라 레이어 변경 → 전체 파이프라인 영향 |

- **결론:** 보고서·면접에서 고도화 과제로 서술하는 방향으로 대체
  > "EKS 환경에서는 KubernetesPodOperator 적용이 권장되나, 일정 및 비용 제약으로 PythonOperator로 구현하였으며 향후 고도화 과제로 남겨둠"

---

### 5. 버그 수정 (7주차 이월)

| 커밋 | 내용 |
|---|---|
| `1d0ee22` | 그래프 유저 fallback: 스트리머 하드코딩 게임 데이터 추가, 새로고침 버튼 추가 |
| `3ff1e64` | 더미 유저 → 실제 Steam 친구 + 공개 유저 혼합 |
| `d31980b` | LightGCN expander 내 UMAP/t-SNE 라디오 필터 추가 |
| `6d8941a` | LightGCN 그래프 캐러셀 아래로 이동, collapsible expander 적용 |
| `975dc01` | LightGCN 그래프 재설계: batch trace, glow 효과, 플레이타임 가중 엣지 |
