"""RAC 파라미터 격자 탐색 (검증 시드 0~29). 기준선 대비 지배 여부 출력."""
import itertools, sys
import numpy as np, pandas as pd
import policies as P
from core import simulate, snapshot

def evaluate(make, seeds=range(30), rhos=(5, 10, 17), rs=(100, 150, 300), losses=(0, 0.1, 0.3), tau=0.0):
    rows = []
    for rho, r, loss, s in itertools.product(rhos, rs, losses, seeds):
        g = np.random.default_rng(1000 * s + 7)
        x, y, v = snapshot(g, rho, tau=tau)
        pr = np.random.default_rng(s)
        out = simulate(x, y, v, r, loss, make(pr), pr)
        if out["n_aff"] > 0:
            rows.append(dict(loss=loss, rho=rho, r=r, seed=s, **out))
    return pd.DataFrame(rows)

def summary(df):
    return df.groupby("loss").agg(reach=("reach", "mean"), near=("reach_near", "mean"), hr=("reach_hr", "mean"), tx=("tx", "mean"))

if __name__ == "__main__":
    base = {"dist-timer": lambda pr: P.DistTimer(), "counter3": lambda pr: P.CounterBased(3, pr)}
    ref = {k: summary(evaluate(f)) for k, f in base.items()}
    grid = list(itertools.product([0, 0.5, 1], [1, 2], [0, 1], [0, 0.5], [0, 1]))
    res = []
    for a, kb, kn, g, kl in grid:
        sm = summary(evaluate(lambda pr: P.RAC(a, kb, kn, g, kl)))
        res.append(dict(alpha=a, k_base=kb, k_near=kn, g=g, k_loss=kl,
                        **{f"reach{l}": sm.reach[l] for l in sm.index}, **{f"tx{l}": sm.tx[l] for l in sm.index},
                        **{f"near{l}": sm.near[l] for l in sm.index}))
    R = pd.DataFrame(res)
    for k, sm in ref.items():
        R[f"dom_{k}"] = np.all([(R[f"reach{l}"] >= sm.reach[l] - 1e-9) & (R[f"tx{l}"] <= sm.tx[l]) for l in sm.index], axis=0)
    R.to_csv("results/c2_grid.csv", index=False)
    for k, sm in ref.items():
        print(k, "reach", sm.reach.round(3).tolist(), "tx", sm.tx.round(2).tolist())
    print("dist-timer 지배:", R.dom_dist_timer.sum() if "dom_dist_timer" in R else R["dom_dist-timer"].sum(), " counter3 지배:", R.dom_counter3.sum())
    cols = ["alpha", "k_base", "k_near", "g", "k_loss", "reach0.0", "reach0.1", "reach0.3", "tx0.0", "tx0.1", "tx0.3"]
    print(R.sort_values("tx0.3")[cols].round(3).to_string(index=False))
