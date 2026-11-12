"""시간 축 평가: 1초마다 경고 반복, 차량은 등속 이동(반응 없음), 급정거 차량은 6 m/s^2로 정지.
지표: 고위험 시점(정지거리 안에 들어오는 순간) 이전에 경고를 받은 비율 = 제때 경고율, 총 재전송 수."""
import itertools, sys
import numpy as np, pandas as pd
import policies as P
from core import simulate, snapshot, adjacency, AREA
import core

def run(make, seed, rho, r, loss, T_end=6):
    g = np.random.default_rng(1000 * seed + 7)
    x0, y, v0 = snapshot(g, rho)
    n = len(x0)
    warned = np.full(n, np.inf); due = np.full(n, np.inf); tx = 0
    pr = np.random.default_rng(seed)
    for t in range(T_end + 1):
        vh = max(v0[0] - 6 * t, 0); xh = x0[0] + (v0[0] * t - 3 * t * t if v0[0] - 6 * t > 0 else v0[0] ** 2 / 12)
        x = np.minimum(x0 + v0 * t, xh - 5); x[0] = xh
        v = v0.copy(); v[0] = vh; v[x >= xh - 5] = np.minimum(v[x >= xh - 5], vh); v[0] = vh
        back = xh - x
        stop = v * 1.5 + v * v / 12
        newly = (due == np.inf) & (back > 0) & (back <= stop) & (x0[0] - x0 <= AREA + 200)
        due[newly] = t
        # 한 번 경고 전파 (warned 기록용 시뮬레이션)
        rec = sim_once(make(pr), x, y, v, r, loss, pr)
        tx += rec["tx"]
        warned[(warned == np.inf) & rec["got"]] = t
    hit = np.isfinite(due); hit[0] = False
    timely = (warned[hit] <= due[hit]).mean() if hit.any() else np.nan
    return dict(timely=timely, n_due=int(hit.sum()), tx=tx)

def sim_once(pol, x, y, v, r, loss, pr):
    # core.simulate을 그대로 쓰되 수신 여부 배열을 얻기 위해 t_rx를 노출
    out = core.simulate(x, y, v, r, loss, pol, pr, return_rx=True)
    return out

if __name__ == "__main__":
    M = {"flooding": lambda pr: P.Flooding(), "threshold": lambda pr: P.Threshold(),
         "MPR": lambda pr: P.MPR(), "counter3": lambda pr: P.CounterBased(3, pr),
         "dist-timer": lambda pr: P.DistTimer(), "RAC*": lambda pr: P.RAC(0.5, 1, 1, 0.5, 0, "stop"),
         "LRAC": lambda pr: P.LearnedRAC(0.05, 0.3)}
    seeds = range(int(sys.argv[1]) if len(sys.argv) > 1 else 0, (int(sys.argv[1]) if len(sys.argv) > 1 else 0) + 30)
    rows = []
    for (k, f), rho, r, loss, s in itertools.product(M.items(), (5, 10, 17), (100, 150), (0, 0.3), seeds):
        rows.append(dict(policy=k, rho=rho, r=r, loss=loss, seed=s, **run(f, s, rho, r, loss)))
    D = pd.DataFrame(rows); D.to_csv(f"results/timeaxis_{seeds[0]}.csv", index=False)
    print(D.pivot_table(index="policy", columns="loss", values=["timely", "tx"]).round(3).to_string())
