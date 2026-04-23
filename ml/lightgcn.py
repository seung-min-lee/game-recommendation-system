"""
LightGCN (Light Graph Convolutional Network) 추천 모델
논문: He et al., "LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation" (SIGIR 2020)

핵심 아이디어:
  1. 유저-아이템 이분 그래프 구성
  2. 정규화된 인접행렬로 K층 그래프 컨볼루션 수행
  3. 전 레이어 임베딩 평균 → 최종 임베딩
  4. BPR Loss로 임베딩 학습
  5. 유저·아이템 임베딩 내적 → 추천 점수
"""

from __future__ import annotations
import numpy as np
from collections import defaultdict

try:
    from scipy import sparse as sp
    _SCIPY = True
except ImportError:
    _SCIPY = False


class LightGCN:
    def __init__(self, n_layers: int = 3, emb_dim: int = 64,
                 lr: float = 0.01, n_epochs: int = 300, reg: float = 1e-4):
        self.n_layers = n_layers
        self.emb_dim  = emb_dim
        self.lr       = lr
        self.n_epochs = n_epochs
        self.reg      = reg

        self.user_ids   : list = []
        self.item_ids   : list = []
        self.user_index : dict = {}
        self.item_index : dict = {}

        # 학습 완료 후 최종 임베딩
        self._u_final : np.ndarray | None = None
        self._i_final : np.ndarray | None = None
        self._A_hat   = None   # 정규화 인접행렬

    # ──────────────────────────────────────────────────────
    # 학습
    # ──────────────────────────────────────────────────────
    def fit(self, interactions: list[tuple]) -> None:
        """
        interactions: [(user_id, item_id, weight), ...]
          weight = 플레이타임(분) 등 상호작용 강도
        """
        user_set = sorted({u for u, _, _ in interactions})
        item_set = sorted({i for _, i, _ in interactions})
        self.user_ids   = user_set
        self.item_ids   = item_set
        self.user_index = {u: idx for idx, u in enumerate(user_set)}
        self.item_index = {it: idx for idx, it in enumerate(item_set)}

        n_u = len(user_set)
        n_i = len(item_set)

        self._A_hat = self._build_adjacency(interactions, n_u, n_i)

        # Xavier 초기화
        np.random.seed(42)
        scale = np.sqrt(2.0 / (n_u + n_i + 2 * self.emb_dim))
        self.user_emb = np.random.normal(0, scale, (n_u, self.emb_dim))
        self.item_emb = np.random.normal(0, scale, (n_i, self.emb_dim))

        # 유저별 보유 아이템 집합
        user_pos: dict[int, set] = defaultdict(set)
        for u, it, _ in interactions:
            user_pos[self.user_index[u]].add(self.item_index[it])
        all_items = set(range(n_i))

        pos_pairs = [(self.user_index[u], self.item_index[it]) for u, it, _ in interactions]

        for epoch in range(self.n_epochs):
            E_final = self._propagate(np.vstack([self.user_emb, self.item_emb]))
            u_emb = E_final[:n_u]
            i_emb = E_final[n_u:]

            grad_u  = np.zeros_like(self.user_emb)
            grad_ip = np.zeros_like(self.item_emb)
            grad_in = np.zeros_like(self.item_emb)

            for ui, ii_pos in pos_pairs:
                neg_pool = list(all_items - user_pos[ui])
                if not neg_pool:
                    continue
                ii_neg = int(np.random.choice(neg_pool))

                u_vec     = u_emb[ui]
                i_pos_vec = i_emb[ii_pos]
                i_neg_vec = i_emb[ii_neg]

                # BPR gradient: σ(-(r_pos - r_neg))
                diff    = float(u_vec @ i_pos_vec) - float(u_vec @ i_neg_vec)
                sigmoid = 1.0 / (1.0 + np.exp(min(diff, 30)))   # 수치 안정

                grad_u[ui]     += sigmoid * (i_neg_vec - i_pos_vec)
                grad_ip[ii_pos] += sigmoid * (-u_vec)
                grad_in[ii_neg] += sigmoid * u_vec

            self.user_emb -= self.lr * (grad_u  + self.reg * self.user_emb)
            self.item_emb -= self.lr * (grad_ip + grad_in + self.reg * self.item_emb)

        # 추론용 최종 임베딩 저장
        E_final = self._propagate(np.vstack([self.user_emb, self.item_emb]))
        self._u_final = E_final[:n_u]
        self._i_final = E_final[n_u:]

    # ──────────────────────────────────────────────────────
    # 추천
    # ──────────────────────────────────────────────────────
    def recommend(self, user_id: str, owned_ids: set, top_k: int = 10) -> list[tuple]:
        """학습 데이터에 있는 유저 → 저장된 임베딩 사용"""
        if user_id in self.user_index:
            u_vec = self._u_final[self.user_index[user_id]]
        else:
            u_vec = self._u_final.mean(axis=0)
        return self._score_items(u_vec, owned_ids, top_k)

    def recommend_new_user(self, owned_games: list, owned_ids: set, top_k: int = 10) -> list[tuple]:
        """
        학습에 없는 신규 유저:
        소유 게임의 아이템 임베딩을 플레이타임 가중 평균 → 유저 임베딩 근사
        """
        total = sum(g.get("playtime_minutes", 1) for g in owned_games) or 1
        u_vec = np.zeros(self.emb_dim)
        for g in owned_games:
            aid = g["app_id"]
            if aid in self.item_index:
                w = g.get("playtime_minutes", 1) / total
                u_vec += w * self._i_final[self.item_index[aid]]

        if np.linalg.norm(u_vec) < 1e-8:
            u_vec = self._u_final.mean(axis=0)

        return self._score_items(u_vec, owned_ids, top_k)

    # ──────────────────────────────────────────────────────
    # 내부 유틸
    # ──────────────────────────────────────────────────────
    def _build_adjacency(self, interactions, n_u: int, n_i: int):
        """
        A = [[0, R], [R^T, 0]]
        A_hat = D^(-1/2) A D^(-1/2)   (대칭 정규화)
        """
        rows, cols, vals = [], [], []
        for u, it, w in interactions:
            rows.append(self.user_index[u])
            cols.append(self.item_index[it])
            vals.append(float(w))

        n = n_u + n_i
        if _SCIPY:
            R = sp.csr_matrix((vals, (rows, cols)), shape=(n_u, n_i))
            A = sp.bmat(
                [[sp.csr_matrix((n_u, n_u)), R],
                 [R.T, sp.csr_matrix((n_i, n_i))]],
                format="csr",
            )
            d = np.asarray(A.sum(axis=1)).flatten()
            d_inv = np.where(d > 0, d ** -0.5, 0.0)
            D = sp.diags(d_inv)
            return D @ A @ D        # scipy sparse
        else:
            # scipy 없을 때 numpy dense fallback (소규모 데이터용)
            A = np.zeros((n, n))
            for r, c, v in zip(rows, cols, vals):
                A[r, n_u + c] = v
                A[n_u + c, r] = v
            d = A.sum(axis=1)
            d_inv = np.where(d > 0, d ** -0.5, 0.0)
            return np.diag(d_inv) @ A @ np.diag(d_inv)

    def _propagate(self, E: np.ndarray) -> np.ndarray:
        """K층 그래프 컨볼루션 후 레이어 평균 반환"""
        layers = [E]
        cur = E
        for _ in range(self.n_layers):
            if _SCIPY:
                cur = self._A_hat @ cur
            else:
                cur = self._A_hat @ cur
            layers.append(cur)
        return np.mean(layers, axis=0)

    def _score_items(self, u_vec: np.ndarray, owned_ids: set, top_k: int) -> list[tuple]:
        scores = [
            (it_id, float(u_vec @ self._i_final[ii]))
            for it_id, ii in self.item_index.items()
            if it_id not in owned_ids
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
