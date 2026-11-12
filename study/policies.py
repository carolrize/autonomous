"""전달 정책. 모두 같은 인터페이스: policy(i, sender, ctx) -> (재전송?, 대기[s])."""

from collections import deque

import numpy as np

from core import AREA, TMAX, T


class Flooding:
    name = "flooding"
    def __call__(self, i, s, ctx):
        return True, 0.0


class PPersist:
    """p-persistence (Wisitpongphan 2007의 확률 재전송 기본형)."""
    def __init__(self, p=0.5, rng=None):
        self.p, self.rng, self.name = p, rng, f"p-persist({p})"
    def __call__(self, i, s, ctx):
        return self.rng.random() < self.p, 0.0


class Threshold:
    """선행 탐구: 자기 위험도 R >= T 일 때만 재전송."""
    name = "threshold"
    def __call__(self, i, s, ctx):
        return ctx["R"][i] >= T, 0.0


class DistTimer:
    """거리 기반 타이머 + 억제 (slotted 1-persistence 계열, Wisitpongphan 2007).
    송신자에게서 뒤로 멀수록 빨리 재전송, 자기보다 뒤에 있는 차량의 재전송을 들으면 취소."""
    name = "dist-timer"
    def __call__(self, i, s, ctx):
        prog = max(0.0, ctx["x"][s] - ctx["x"][i])
        return True, TMAX * (1 - min(prog, ctx["r"]) / ctx["r"])
    def cancelled(self, i, heard, ctx):
        x = ctx["x"]
        return any(x[h] < x[i] for h in heard)


class MPR:
    """OLSR 방식 MPR flooding: 처음 받은 송신자의 MPR로 뽑힌 차량만 재전송 (2홉 지역 정보)."""
    name = "MPR"
    def prepare(self, ctx):
        A = ctx["A"]; n = ctx["n"]
        self.mpr = {}
        for u in range(n):
            n1 = set(np.where(A[u])[0])
            n2 = set()
            for w in n1:
                n2 |= set(np.where(A[w])[0])
            n2 -= n1 | {u}
            sel = set()
            # 2홉 이웃 중 연결이 하나뿐인 것부터
            cover = {w: set(np.where(A[w])[0]) & n2 for w in n1}
            left = set(n2)
            for z in list(left):
                c = [w for w in n1 if z in cover[w]]
                if len(c) == 1:
                    sel.add(c[0])
            for w in sel:
                left -= cover[w]
            while left:
                w = max(n1 - sel, key=lambda k: len(cover[k] & left))
                if not cover[w] & left:
                    break
                sel.add(w); left -= cover[w]
            self.mpr[u] = sel
    def __call__(self, i, s, ctx):
        return i in self.mpr[s], 0.0


class Oracle:
    """정답 라벨(중앙 계산 상한): 발신원→영향 차량 BFS 최단 경로 중간 차량 + 단절점."""
    name = "oracle(BFS+AP)"
    def prepare(self, ctx):
        A, back = ctx["A"], ctx["back"]
        n = ctx["n"]
        inside = back <= AREA
        par = {0: None}; q = deque([0])
        while q:
            u = q.popleft()
            for w in np.where(A[u] & inside)[0]:
                if w not in par:
                    par[w] = u; q.append(w)
        relay = set()
        aff = np.where((back > 0) & (back <= AREA))[0]
        for t in aff:
            u = par.get(t)
            while u is not None and u != 0:
                relay.add(u); u = par[u]
        self.relay = relay | (articulation(A, inside) & set(par))
    def __call__(self, i, s, ctx):
        return i in self.relay, 0.0


def articulation(A, inside):
    n = len(A); idx = [i for i in range(n) if inside[i]]
    disc, low, ap = {}, {}, set(); t = [0]
    import sys; sys.setrecursionlimit(10000)
    def dfs(u, p):
        disc[u] = low[u] = t[0]; t[0] += 1; ch = 0
        for w in np.where(A[u])[0]:
            if not inside[w]:
                continue
            if w not in disc:
                ch += 1; dfs(w, u); low[u] = min(low[u], low[w])
                if p is not None and low[w] >= disc[u]:
                    ap.add(u)
            elif w != p:
                low[u] = min(low[u], disc[w])
        if p is None and ch > 1:
            ap.add(u)
    for i in idx:
        if i not in disc:
            dfs(i, None)
    return ap


# ---------------- 2회차: 보완 후보 ----------------
from core import NEAR  # noqa: E402


class HybridTimer(DistTimer):
    """V1: 거리 타이머 ∪ 역치 안전장치 (R>=T면 억제 없이 즉시 재전송)."""
    name = "V1 timer+R"
    def __call__(self, i, s, ctx):
        if ctx["R"][i] >= T:
            return True, 0.0
        return super().__call__(i, s, ctx)
    def cancelled(self, i, heard, ctx):
        return ctx["R"][i] < T and super().cancelled(i, heard, ctx)


class CoverageTimer(DistTimer):
    """V2: 2홉 정보로 '내가 새로 덮는 후방 이웃 비율'이 클수록 빨리 재전송."""
    name = "V2 coverage-timer"
    def __call__(self, i, s, ctx):
        A, x = ctx["A"], ctx["x"]
        mine = A[i] & (x < x[i])
        new = mine & ~A[s]
        u = new.sum() / max(mine.sum(), 1)
        return True, TMAX * (1 - u)


class RiskRedundant(DistTimer):
    """V3: 고위험 구간(후방 NEAR m)에서는 뒤쪽 재전송을 2번 들어야 취소 (위험 비례 중복)."""
    name = "V3 risk-redundant"
    def __init__(self, k=2):
        self.k = k
    def cancelled(self, i, heard, ctx):
        x = ctx["x"]
        c = sum(x[h] < x[i] for h in heard)
        need = self.k if ctx["back"][i] <= NEAR else 1
        return c >= need


EXTRA = {
    "V1": lambda rng: HybridTimer(),
    "V2": lambda rng: CoverageTimer(),
    "V3": lambda rng: RiskRedundant(2),
}


# ---------------- 3회차 ----------------
from core import AREA as _AREA  # noqa: E402


class RiskCoverage(DistTimer):
    """V4: 2홉 커버리지 타이머 + 범위 안 새 커버리지 0이면 재전송 안 함 + 고위험 구간 2중 억제."""
    name = "V4 risk-coverage"
    def __init__(self, k=2):
        self.k = k
    def __call__(self, i, s, ctx):
        A, x, back = ctx["A"], ctx["x"], ctx["back"]
        mine = A[i] & (x < x[i]) & (back <= _AREA)
        new = mine & ~A[s]
        if new.sum() == 0:
            return False, 0.0
        return True, TMAX * (1 - new.sum() / max(mine.sum(), 1))
    def cancelled(self, i, heard, ctx):
        x = ctx["x"]
        c = sum(x[h] < x[i] for h in heard)
        need = self.k if ctx["back"][i] <= NEAR else 1
        return c >= need


EXTRA["V4"] = lambda rng: RiskCoverage(2)
EXTRA["V4-k1"] = lambda rng: RiskCoverage(1)


# ---------------- 4회차 ----------------
class ExpectedCoverage(DistTimer):
    """V5: 손실 p를 반영한 '기대 새 커버리지'로 타이머·재전송 여부 결정 + 고위험 구간 위험 비례 중복.
    p는 비콘 수신률로 각 차량이 추정한다고 가정 (여기선 실제 손실률 사용)."""
    name = "V5 expected-coverage"
    def __init__(self, k_near=2, min_gain=0.5):
        self.k_near, self.min_gain = k_near, min_gain
    def __call__(self, i, s, ctx):
        A, x, back, p = ctx["A"], ctx["x"], ctx["back"], ctx["loss"]
        mine = A[i] & (x < x[i]) & (back <= _AREA)
        new = (mine & ~A[s]).sum() + p * (mine & A[s]).sum()  # 송신자 이웃도 p 확률로 못 받았을 수 있음
        if new < self.min_gain:
            return False, 0.0
        return True, TMAX * (1 - new / max(mine.sum(), 1))
    def cancelled(self, i, heard, ctx):
        x = ctx["x"]
        c = sum(x[h] < x[i] for h in heard)
        k = self.k_near if ctx["back"][i] <= NEAR else 1
        if ctx["loss"] >= 0.2:
            k += 1
        return c >= k


EXTRA["V5"] = lambda rng: ExpectedCoverage()
