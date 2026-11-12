"""손대지 않은 테스트 시드로 전체 비교 + 같은 시드 대응 Wilcoxon (RAC* vs 각 방법)."""
import sys
import numpy as np, pandas as pd
from scipy.stats import wilcoxon
import policies as P
from tune import evaluate

S0 = int(sys.argv[1]) if len(sys.argv) > 1 else 500
M = {
    "flooding": lambda pr: P.Flooding(), "p-persist": lambda pr: P.PPersist(0.5, pr),
    "threshold": lambda pr: P.Threshold(), "counter3": lambda pr: P.CounterBased(3, pr),
    "ni-dist": lambda pr: P.NiDistance(0.5, pr), "MPR": lambda pr: P.MPR(),
    "dist-timer": lambda pr: P.DistTimer(), "RAC-noRisk": lambda pr: P.RAC(0.5, 1, 0, 0.5, 0),
    "RAC*": lambda pr: P.RAC(0.5, 1, 1, 0.5, 0, "stop"),
}
M.update(getattr(P, "FINAL_EXTRA", {}))
dfs = []
for k, f in M.items():
    d = evaluate(f, seeds=range(S0, S0 + 30)); d["policy"] = k; dfs.append(d)
D = pd.concat(dfs); D.to_csv(f"results/final_{S0}.csv", index=False)
fl = D[D.policy == "flooding"].set_index(["loss", "rho", "r", "seed"]).tx
D = D.join(fl.rename("fl"), on=["loss", "rho", "r", "seed"]); D["q"] = D.tx / D.fl
T = D.pivot_table(index="policy", columns="loss", values=["reach", "reach_hr", "q"]).round(3)
print(T.to_string())
key = ["loss", "rho", "r", "seed"]
a = D[D.policy == "RAC*"].set_index(key)
for k in ["dist-timer", "counter3", "MPR"]:
    b = D[D.policy == k].set_index(key)
    j = a.join(b, rsuffix="_b", how="inner")
    for m in ["reach_hr", "tx"]:
        x, y = j[m].values, j[m + "_b"].values
        ok = ~(np.isnan(x) | np.isnan(y))
        diff = x[ok] - y[ok]
        p = wilcoxon(diff).pvalue if np.any(diff != 0) else 1.0
        print(f"RAC* vs {k:10s} {m:8s} 평균차 {diff.mean():+.3f}  p={p:.2g}")
