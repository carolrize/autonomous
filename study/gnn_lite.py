"""SIGN 방식 그래프 모델 (2홉 이웃 집계 특징 + MLP)로 '결정적 릴레이 확률'을 학습.

라벨: 손실 p에서 flooding을 MC 반복, 차량 i의 송신이 어떤 영향 차량의 유일한 수신원이었던 비율.
학습 시드 100~399 (검증 0~29, 테스트 500~529와 분리).
python gnn_lite.py  → models/sign.pkl 저장
"""
import itertools
import os
import pickle

import numpy as np
from sklearn.neural_network import MLPRegressor

from core import AREA, adjacency, risk, snapshot


def node_features(x, y, v, r, loss, A):
    back = x[0] - x
    inside = back <= AREA
    behind = A & (x[None, :] < x[:, None]) & inside[None, :]
    nb_b = behind.sum(1)
    far = np.where(behind, x[:, None] - x[None, :], 0).max(1)
    f = np.stack([
        back / AREA, v / 30, y / 8, risk(x, v), nb_b / 10, A.sum(1) / 20,
        far / r, np.full(len(x), loss), np.full(len(x), r / 300),
        (nb_b == 0).astype(float),
    ], 1)
    deg = np.maximum(A.sum(1, keepdims=True), 1)
    A2 = ((A.astype(int) @ A.astype(int)) > 0) & ~np.eye(len(x), dtype=bool)
    deg2 = np.maximum(A2.sum(1, keepdims=True), 1)
    m1 = (A @ f) / deg
    m2 = (A2 @ f) / deg2
    return np.hstack([f, m1, m2])


v_glob = []


def v_stop(x, v):
    return v * 1.5 + v * v / 12.0


def critical_label(x, y, r, loss, A, rng, runs=10):
    """손실 실현 그래프에서 i를 제거하면 못 닿게 되는 영향 차량 비율의 기대값."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order
    back = x[0] - x
    inside = back <= AREA
    aff = (back > 0) & inside
    wgt = np.where(back <= v_stop(x, v_glob[0]), 3.0, 1.0) if v_glob else np.ones(len(x))
    n = len(x); crit = np.zeros(n)
    for _ in range(runs):
        keep = np.triu(rng.random((n, n)) >= loss, 1); keep = keep | keep.T
        G = A & keep & inside[None, :] & inside[:, None]
        base = set(breadth_first_order(csr_matrix(G), 0, return_predecessors=False))
        tot = max(sum(wgt[j] for j in base if aff[j]), 1)
        for i in base:
            if i == 0:
                continue
            Gi = G.copy(); Gi[i, :] = False; Gi[:, i] = False
            rr = set(breadth_first_order(csr_matrix(Gi), 0, return_predecessors=False))
            lost = sum(wgt[j] for j in base if aff[j] and j not in rr and j != i)
            crit[i] += lost / tot
    return crit / runs


def build(seeds, rng_cond):
    X, Y = [], []
    for s in seeds:
        rho = rng_cond.choice([5, 10, 17]); r = rng_cond.choice([100, 150, 300]); loss = rng_cond.choice([0, 0.1, 0.3])
        g = np.random.default_rng(1000 * s + 7)
        x, y, v = snapshot(g, rho)
        A, _ = adjacency(x, y, r)
        F = node_features(x, y, v, r, loss, A)
        v_glob[:] = [v]
        lab = critical_label(x, y, r, loss, A, np.random.default_rng(s + 99))
        keep = (x[0] - x) <= AREA
        X.append(F[keep]); Y.append(lab[keep])
    return np.vstack(X), np.concatenate(Y)


if __name__ == "__main__":
    X, Y = build(range(100, 400), np.random.default_rng(0))
    Xv, Yv = build(range(400, 450), np.random.default_rng(1))
    print("train", X.shape, "label mean", Y.mean().round(3), "| val", Xv.shape)
    m = MLPRegressor(hidden_layer_sizes=(64, 64), learning_rate_init=1e-3, max_iter=300, early_stopping=True, random_state=0)
    m.fit(X, Y)
    pv = m.predict(Xv)
    corr = np.corrcoef(pv, Yv)[0, 1]
    base = np.corrcoef(Xv[:, 4], Yv)[0, 1]
    print(f"val MSE {np.mean((pv - Yv) ** 2):.4f}  상관 {corr:.3f}  (참고: 후방 이웃 수 단독 상관 {base:.3f})")
    os.makedirs("models", exist_ok=True)
    pickle.dump(m, open(os.environ.get("SIGN_OUT", "models/sign.pkl"), "wb"))
