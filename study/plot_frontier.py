"""손실률별 도달률-재전송 수 파레토 그림."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
d = pd.read_csv("results/iter4.csv"); d = d[d.n_aff > 0]
fl = d[d.policy == "flooding"].set_index(["rho", "r", "loss", "tau", "seed"]).tx.rename("fl")
d = d.join(fl, on=["rho", "r", "loss", "tau", "seed"]); d["q"] = d.tx / d.fl
g = d.groupby(["loss", "policy"])[["q", "reach", "reach_near"]].mean().reset_index()
style = {"flooding": ("0.5", "o"), "threshold": ("#d62728", "x"), "MPR": ("#9467bd", "s"),
         "oracle": ("#8c564b", "D"), "dist-timer": ("#1f77b4", "^"),
         "V4-k1": ("#2ca02c", "v"), "V4": ("#2ca02c", "P"), "V5": ("#ff7f0e", "*")}
fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
for ax, (loss, gg) in zip(axes, g.groupby("loss")):
    for _, row in gg.iterrows():
        c, m = style[row.policy]
        ax.scatter(row.q * 100, row.reach * 100, c=c, marker=m, s=90, label=row.policy)
        ax.annotate(row.policy, (row.q * 100, row.reach * 100), xytext=(5, -10), textcoords="offset points", fontsize=8)
    ax.set_title(f"패킷 손실 {loss*100:.0f}%")
    ax.set_xlabel("재전송 수 (flooding 대비 %)")
    ax.grid(alpha=0.3); ax.set_xlim(0, 105)
axes[0].set_ylabel("영향 차량 도달률 (%)\n(도달 가능한 차량 기준)")
fig.suptitle("도달률–재전송 트레이드오프 (밀도 3 × 반경 3 × 30시드 평균, 왼쪽 위가 좋음)", fontsize=11)
fig.tight_layout(); fig.savefig("results/frontier_iter4.png", dpi=150)
print("saved")
