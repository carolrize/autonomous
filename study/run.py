"""조건 × 정책 × 시드 일괄 실행 → CSV + 요약 표.

python run.py --tag iter1 --seeds 30
"""

import argparse
import os
import time

import numpy as np
import pandas as pd

import policies as P
from core import simulate, snapshot


def make_policies(rng, names):
    allp = {
        "flooding": lambda: P.Flooding(),
        "p-persist": lambda: P.PPersist(0.5, rng),
        "threshold": lambda: P.Threshold(),
        "dist-timer": lambda: P.DistTimer(),
        "MPR": lambda: P.MPR(),
        "oracle": lambda: P.Oracle(),
    }
    extra = getattr(P, "EXTRA", {})
    allp.update({k: (lambda f=f: f(rng)) for k, f in extra.items()})
    return {k: allp[k]() for k in names}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="iter1")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--rho", default="5,10,17")       # 대/km/차선 (x3차선 = 15/30/50대/km)
    ap.add_argument("--r", default="100,150,300")
    ap.add_argument("--loss", default="0,0.1,0.3")
    ap.add_argument("--tau", default="0")
    ap.add_argument("--policies", default="flooding,p-persist,threshold,dist-timer,MPR,oracle")
    a = ap.parse_args()
    rows = []; t0 = time.time()
    names = a.policies.split(",")
    for rho in map(float, a.rho.split(",")):
        for r in map(float, a.r.split(",")):
            for loss in map(float, a.loss.split(",")):
                for tau in map(float, a.tau.split(",")):
                    for s in range(a.seeds):
                        g = np.random.default_rng(1000 * s + 7)
                        x, y, v = snapshot(g, rho, tau=tau)
                        for name in names:
                            pr = np.random.default_rng(s)  # 같은 시드 = 같은 손실 난수
                            pol = make_policies(pr, [name])[name]
                            out = simulate(x, y, v, r, loss, pol, pr)
                            rows.append(dict(rho=rho, r=r, loss=loss, tau=tau, seed=s, policy=name, **out))
    df = pd.DataFrame(rows)
    os.makedirs("results", exist_ok=True)
    df.to_csv(f"results/{a.tag}.csv", index=False)
    d = df[df.n_aff > 0]
    summ = d.groupby("policy").agg(reach=("reach", "mean"), reach_near=("reach_near", "mean"),
                                   tx=("tx", "mean"), dup=("dup", "mean"), lat_ms=("lat", "mean"))
    fl = d[d.policy == "flooding"].set_index(["rho", "r", "loss", "tau", "seed"]).tx
    d = d.join(fl.rename("tx_fl"), on=["rho", "r", "loss", "tau", "seed"])
    summ["tx_vs_flood"] = d.assign(q=d.tx / d.tx_fl).groupby("policy").q.mean()
    print(f"[{a.tag}] {len(df)} runs, 영향 차량 전부 연결된 시나리오 {df.connected.mean()*100:.0f}%, {time.time()-t0:.0f}s")
    print(summ.round(3).sort_values("tx").to_string())


if __name__ == "__main__":
    main()
