"""구성요소 제거 실험 (테스트 시드 500~529). 선행 기법 부분(base)에 새 요소를 하나씩 더함."""
import numpy as np, pandas as pd
from scipy.stats import wilcoxon
import policies as P
from tune import evaluate

def lrac_norisk(pr):
    p = P.LearnedRAC(0.05, 0.3); p.k_near = 0; return p

M = {
    "flooding": lambda pr: P.Flooding(),
    "dist-timer": lambda pr: P.DistTimer(),
    "base(선행: 거리+커버리지 타이머)": lambda pr: P.RAC(0.5, 1, 0, 0.5, 0),
    "+학습 결정성": lrac_norisk,
    "+긴급도 예산": lambda pr: P.UrgencyRAC(0.01, 0.1, 2.0, learned=False),
    "full(RAC-U)": lambda pr: P.UrgencyRAC(0.01, 0.1, 2.0, learned=True),
}
dfs = []
for k, f in M.items():
    d = evaluate(f, seeds=range(500, 530)); d["policy"] = k; dfs.append(d)
D = pd.concat(dfs); D.to_csv("results/ablation_test.csv", index=False)
key = ["loss", "rho", "r", "seed"]
fl = D[D.policy == "flooding"].set_index(key).tx
D = D.join(fl.rename("fl"), on=key); D["q"] = D.tx / D.fl
print(D.pivot_table(index="policy", columns="loss", values=["reach", "reach_hr", "q"], sort=False).round(3).to_string())
base = D[D.policy.str.startswith("base")].set_index(key)
for k in ["+학습 결정성", "+긴급도 예산", "full(RAC-U)", "dist-timer"]:
    j = D[D.policy == k].set_index(key).join(base, rsuffix="_b")
    for m in ["reach", "reach_hr", "tx"]:
        d = (j[m] - j[m + "_b"]).dropna()
        print(f"{k:14s} − base  {m:8s} {d.mean():+.3f}  p={wilcoxon(d).pvalue if (d != 0).any() else 1:.2g}")
full = D[D.policy == "full(RAC-U)"].set_index(key)
j = full.join(D[D.policy == "dist-timer"].set_index(key), rsuffix="_b")
for lo in (0, 0.1, 0.3):
    jj = j[j.index.get_level_values("loss") == lo]
    for m in ["reach", "reach_hr", "tx"]:
        d = (jj[m] - jj[m + "_b"]).dropna()
        print(f"full − dist-timer (손실 {lo}) {m:8s} {d.mean():+.3f}  p={wilcoxon(d).pvalue if (d != 0).any() else 1:.2g}")
