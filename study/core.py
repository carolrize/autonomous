"""경고 1건의 다중 홉 전파를 이벤트 기반으로 시뮬레이션하는 공통 코드.

스냅샷: 편도 3차선 L m, 차선별 밀도 rho(대/km/차선), 맨 앞 차량이 급정거(경과 tau초).
전파: 링크마다 독립 손실 p, 송신 1회는 반경 r 안 이웃 전부에게 방송.
지리 범위: 모든 정책은 급정거 지점 후방 AREA m 밖에서는 재전송하지 않음 (ETSI DENM relevance area와 같은 조건).
"""

import heapq
import itertools

import numpy as np

D_MAX, V_MAX, TTC_MAX = 45.0, 15.0, 8.0
W = np.array([0.645, 3.226, 1.098]); W = W / W.sum()
T = 0.163
AREA = 500.0      # 영향 범위 (후방)
NEAR = 150.0      # 고위험 범위 (후방)
JITTER = 0.002    # MAC 접근 지연 상한 [s]
TMAX = 0.010      # 거리 타이머 최대 대기 [s]


def snapshot(rng, rho, L=2000.0, lanes=3, tau=0.0, v_mean=25.0, v_std=3.0, min_gap=8.0):
    """무작위 배치 스냅샷. rho = 대/km/차선. 0번이 급정거 차량(맨 앞)."""
    xs, ys = [], []
    for k in range(lanes):
        n = rng.poisson(rho * L / 1000)
        x = np.sort(rng.uniform(0, L, n))
        if n > 1:  # 최소 차간 확보
            x = x[0] + np.concatenate([[0], np.cumsum(np.maximum(np.diff(x), min_gap))])
            x = x[x <= L]
        xs.append(x); ys.append(np.full(len(x), 4.0 * k))
    x = np.concatenate(xs); y = np.concatenate(ys)
    v = np.clip(rng.normal(v_mean, v_std, len(x)), 15, 35)
    h = int(np.argmax(x))
    order = [h] + [i for i in range(len(x)) if i != h]
    x, y, v = x[order], y[order], v[order]
    v = v.copy(); v[0] = max(v[0] - 6.0 * tau, 0.0)
    return x, y, v


def risk(x, v):
    """각 차량의 급정거 차량(0번) 대비 위험도 R."""
    d = x[0] - x
    clos = v - v[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        ttc = np.where(clos > 1e-6, d / clos, np.inf)
    f = np.stack([np.clip(1 - d / D_MAX, 0, 1), np.clip(clos / V_MAX, 0, 1), np.clip(1 - ttc / TTC_MAX, 0, 1)])
    R = W @ f
    R[d <= 0] = 0
    R[0] = 0
    return R


def adjacency(x, y, r):
    pos = np.stack([x, y], 1)
    D = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
    A = (D <= r) & ~np.eye(len(x), dtype=bool)
    return A, D


def simulate(x, y, v, r, loss, policy, rng):
    """policy(i, sender, ctx) -> (재전송 여부, 대기시간) ; ctx에 그래프 정보.
    거리 타이머 계열은 policy가 'cancel' 콜백을 갖는다."""
    n = len(x)
    A, D = adjacency(x, y, r)
    back = x[0] - x
    ctx = dict(loss=loss, x=x, y=y, v=v, r=r, A=A, D=D, back=back, R=risk(x, v), first_from={}, n=n)
    if hasattr(policy, "prepare"):
        policy.prepare(ctx)

    t_rx = np.full(n, np.inf); t_rx[0] = 0.0
    heard = [[] for _ in range(n)]  # 들은 송신자 목록
    tx = 0
    cnt = itertools.count()
    ev = [(0.0, next(cnt), 0)]      # (송신 시각, tie, 송신자)
    pending = {}
    while ev:
        t, _, s = heapq.heappop(ev)
        if s in pending and pending[s] != t:
            continue
        pending.pop(s, None)
        if hasattr(policy, "cancelled") and s != 0 and policy.cancelled(s, heard[s], ctx):
            continue
        tx += 1
        nb = np.where(A[s])[0]
        ok = nb[rng.random(len(nb)) >= loss]
        for j in ok:
            heard[j].append(s)
            if t_rx[j] < np.inf:
                continue
            t_rx[j] = t + 1e-4  # 전송 시간
            ctx["first_from"][j] = s
            if back[j] > AREA:
                continue  # 범위 밖: 재전송 안 함
            fwd, wait = policy(j, s, ctx)
            if fwd:
                tf = t_rx[j] + wait + rng.uniform(0, JITTER)
                pending[j] = tf
                heapq.heappush(ev, (tf, next(cnt), j))
    can = reach_set(A, back)  # 범위 안 경로로 닿을 수 있는 차량
    aff = (back > 0) & (back <= AREA) & can
    near = (back > 0) & (back <= NEAR) & can
    dup = sum(len(h) for h in heard) - int(np.isfinite(t_rx).sum() - 1)
    return dict(
        reach=float(np.isfinite(t_rx[aff]).mean()) if aff.any() else np.nan,
        reach_near=float(np.isfinite(t_rx[near]).mean()) if near.any() else np.nan,
        tx=tx, n_aff=int(aff.sum()), dup=dup,
        lat=float(np.max(t_rx[aff & np.isfinite(t_rx)], initial=0) * 1000),
        connected=bool(aff.sum() == ((back > 0) & (back <= AREA)).sum()),
    )


def reach_set(A, back):
    """급정거 차량에서 범위 안 차량만 거쳐 닿을 수 있는 차량 (bool 배열)."""
    seen = np.zeros(len(A), bool); seen[0] = True; st = [0]
    while st:
        i = st.pop()
        if back[i] > AREA:
            continue
        for j in np.where(A[i] & ~seen)[0]:
            seen[j] = True; st.append(j)
    return seen
