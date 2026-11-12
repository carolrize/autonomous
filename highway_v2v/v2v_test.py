"""highway-env 위 간단한 V2V 테스트.

맨 앞 차량이 급정거하면 경고(DENM)를 1초마다 보내고,
통신 반경 r 안의 차량끼리 다중 홉으로 전달한다. 두 가지 릴레이 정책을 비교한다.
  - flooding  : 받은 차량은 모두 한 번씩 재전송
  - threshold : 자기 위험도 R >= T 인 차량만 재전송 (선행 탐구 방식)

통신은 이상적(손실·지연 없음)이고, 한 번의 경고는 그 순간의 그래프에서 즉시 퍼진다고 가정한다.

사용 예:
  python v2v_test.py                 # 10시드 평균 + 시드 0 그림 저장
  python v2v_test.py --seeds 30 --radius 150
"""

import argparse
import os
import types

import gymnasium as gym
import highway_env  # noqa: F401  (환경 등록)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from highway_env.vehicle.kinematics import Vehicle

# 선행 탐구 상수·GA 결과 (정규화 가중치)
D_MAX, V_MAX, TTC_MAX = 45.0, 15.0, 8.0
W = np.array([0.645, 3.226, 1.098])
W = W / W.sum()  # 0.13 / 0.65 / 0.22
T = 0.163

BRAKE_DECEL = 6.0   # m/s^2
AFFECT_RANGE = 500  # 급정거 차량 후방 이 거리 안의 차량 = 영향 차량
SIM_FREQ = 15


def risk(v, hazard):
    """차량 v가 급정거 차량 hazard에 대해 느끼는 위험도 R (0~1)."""
    d = hazard.position[0] - v.position[0]
    if d <= 0:
        return 0.0
    closing = v.speed - hazard.speed
    ttc = d / closing if closing > 1e-6 else np.inf
    f_d = np.clip(1 - d / D_MAX, 0, 1)
    f_v = np.clip(closing / V_MAX, 0, 1)
    f_t = np.clip(1 - ttc / TTC_MAX, 0, 1)
    return float(W @ [f_d, f_v, f_t])


def propagate(vehicles, src, hazard, radius, policy):
    """src에서 시작한 경고 1회의 전파. (수신 집합, 재전송 차량, 전송 수, 홉 수)"""
    pos = np.array([v.position for v in vehicles])
    idx = {id(v): i for i, v in enumerate(vehicles)}
    dist = np.linalg.norm(pos[:, None] - pos[None], axis=-1)

    s = idx[id(src)]
    received, hop = {s}, {s: 0}
    relays, frontier = [], [s]
    while frontier:
        nxt = []
        for i in frontier:
            relays.append(i)  # i가 한 번 방송
            for j in np.where(dist[i] <= radius)[0]:
                if j in received:
                    continue
                received.add(j)
                hop[j] = hop[i] + 1
                if policy == "flooding" or risk(vehicles[j], hazard) >= T:
                    nxt.append(j)
        frontier = nxt
    return received, relays, hop


def make_brake(v):
    """v의 제어를 -6 m/s^2 급정거로 덮어쓴다 (정지하면 멈춤)."""
    def act(self, action=None):
        acc = -min(BRAKE_DECEL, self.speed * SIM_FREQ)
        Vehicle.act(self, {"steering": self.steering_control(self.target_lane_index),
                           "acceleration": acc})
    v.act = types.MethodType(act, v)


def run(seed, args, keep_snapshot=False):
    env = gym.make("highway-v0", config={
        "lanes_count": 3,
        "vehicles_count": args.vehicles,
        "duration": args.duration,
        "simulation_frequency": SIM_FREQ,
        "policy_frequency": 5,
    })
    env.reset(seed=seed)
    base = env.unwrapped
    IDLE = base.action_type.actions_indexes["IDLE"]

    hazard, out, snapshot = None, {p: [] for p in ("flooding", "threshold")}, None
    steps = int(args.duration * 5)
    for k in range(steps):
        t = k / 5
        if hazard is None and t >= args.brake_at:
            hazard = max(base.road.vehicles, key=lambda v: v.position[0])
            make_brake(hazard)
        if hazard is not None and abs((t - args.brake_at) % 1.0) < 1e-9:
            vehicles = list(base.road.vehicles)
            affected = [i for i, v in enumerate(vehicles) if v is not hazard
                        and 0 < hazard.position[0] - v.position[0] <= AFFECT_RANGE]
            for p in out:
                rec, relays, hop = propagate(vehicles, hazard, hazard, args.radius, p)
                got = [i for i in affected if i in rec]
                out[p].append({
                    "t": t - args.brake_at,
                    "reach": len(got) / max(len(affected), 1),
                    "tx": len(relays),
                    "max_hop": max(hop[i] for i in got) if got else 0,
                })
                if keep_snapshot and len(out[p]) == 1:  # 급정거 직후 첫 경고만 그림으로
                    if snapshot is None:
                        snapshot = {"vehicles": [(v.position.copy(), v.speed) for v in vehicles],
                                    "hazard": vehicles.index(hazard),
                                    "R": [risk(v, hazard) for v in vehicles],
                                    "affected": affected}
                    snapshot[p] = (rec, relays)
        _, _, term, trunc, _ = env.step(IDLE)
        if term or trunc:
            break
    env.close()
    return out, snapshot


def plot_snapshot(snap, radius, path):
    pos = np.array([p for p, _ in snap["vehicles"]])
    h = snap["hazard"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 4.6), sharex=True)
    for ax, p in zip(axes, ("flooding", "threshold")):
        rec, relays = snap[p]
        relays = set(relays)
        dist = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                if dist[i, j] <= radius:
                    ax.plot(pos[[i, j], 0], pos[[i, j], 1], color="0.85", lw=0.6, zorder=1)
        for i, (x, y) in enumerate(pos):
            if i == h:
                c, m = "#d62728", "s"
            elif i in rec:
                c, m = "#1f77b4", "o"
            else:
                c, m = "0.6", "o"
            ax.scatter(x, y, c=c, marker=m, s=60, zorder=3,
                       edgecolors="k" if i in relays else "none", linewidths=1.5)
            if i in snap["affected"]:
                ax.annotate(f"{snap['R'][i]:.2f}", (x, y), xytext=(0, 7),
                            textcoords="offset points", ha="center", fontsize=7)
        n_aff = len(snap["affected"])
        n_got = sum(i in rec for i in snap["affected"])
        ax.set_title(f"{p}: 영향 차량 도달 {n_got}/{n_aff}, 재전송 {len(relays)}회", fontsize=10)
        ax.set_ylim(-4, 12)
        ax.invert_yaxis()
        ax.set_ylabel("y [m]")
    axes[-1].set_xlabel("x [m]  (빨강 ■ 급정거 차량 · 파랑 수신 · 회색 미수신 · 검은 테두리 재전송 · 숫자 R)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--vehicles", type=int, default=20)
    ap.add_argument("--radius", type=float, default=100.0)
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--brake-at", type=float, default=3.0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "out"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    onset = {p: [] for p in ("flooding", "threshold")}
    allb = {p: [] for p in ("flooding", "threshold")}
    for s in range(args.seeds):
        out, snap = run(s, args, keep_snapshot=(s == 0))
        if snap:
            plot_snapshot(snap, args.radius, os.path.join(args.out, "snapshot_seed0.png"))
        for p in out:
            if out[p]:
                onset[p].append(out[p][0])
                allb[p].extend(out[p])
        print(f"seed {s:2d} | " + " | ".join(
            f"{p}: 도달 {out[p][0]['reach']*100:5.1f}% 전송 {out[p][0]['tx']:2d}"
            for p in out if out[p]))

    print(f"\n=== {args.seeds}시드 평균 (r={args.radius:.0f} m, 차량 {args.vehicles}대, T={T}) ===")
    print("w(정규화) =", np.round(W, 3).tolist())
    print(f"{'정책':<10} {'급정거 직후 도달률':>16} {'전송 수':>8} {'전체 경고 평균 도달률':>20}")
    for p in onset:
        r0 = np.mean([o["reach"] for o in onset[p]]) * 100
        tx = np.mean([o["tx"] for o in onset[p]])
        ra = np.mean([o["reach"] for o in allb[p]]) * 100
        print(f"{p:<10} {r0:15.1f}% {tx:8.1f} {ra:19.1f}%")
    print(f"\n그림: {os.path.join(args.out, 'snapshot_seed0.png')}")


if __name__ == "__main__":
    main()
