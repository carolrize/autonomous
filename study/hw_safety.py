"""highway-env 안전 결과 평가: 경고 → 반응 → 충돌.

가정 (결과 해석 시 반드시 명시)
- 맨 앞 차량이 t=2 s에 -6 m/s^2 급정거. 1초마다 경고 반복, 반경 r, 링크 손실 p
- 경고 못 받은 차량: IDM(센서로 앞차만 봄), 제동 한계 B_UNWARNED (기본 4 m/s^2, 운전자/센서 반응 한계 가정)
- 경고 받은 차량: 뉴런 역치 반응 규칙 — R>=T면 선제 감속(-3 m/s^2 이상), 제동 한계 6 m/s^2
- 차량 배치: highway-env 기본 배치에서 30% 무작위 제거 + 위치 잡음 N(0, 5 m) (등간격 완화)
- 모든 차량 충돌 판정 켬, 충돌 차량 수 집계
python hw_safety.py [seed0] [B_UNWARNED]
"""
import sys, itertools, types
import numpy as np, pandas as pd
import gymnasium as gym
import highway_env  # noqa
from highway_env.vehicle.behavior import IDMVehicle
from highway_env.vehicle.kinematics import Vehicle
sys.path.insert(0, "../highway_v2v")
import core, policies as P

SEED0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
B_UNW = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
REACT = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0  # 미경고 차량의 반응 지연 [s]
AREA0 = 500.0
GROW = float(sys.argv[5]) if len(sys.argv) > 5 else 20.0  # 전달 범위 확장 속도 [m/s]
HEADWAY = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8  # IDM 차간 시간 [s] (기본 1.5 → 촘촘한 고속도로)
IDMVehicle.TIME_WANTED = HEADWAY
DT_POLICY = 0.2

def setup(seed):
    env = gym.make("highway-v0", config={"lanes_count": 3, "vehicles_count": 45, "vehicles_density": 1.3,
                                          "duration": 14, "simulation_frequency": 15, "policy_frequency": 5})
    env.reset(seed=seed)
    b = env.unwrapped
    old = b.vehicle; new = IDMVehicle.create_from(old)
    b.road.vehicles[b.road.vehicles.index(old)] = new; b.controlled_vehicles = [new]
    rng = np.random.default_rng(seed)
    keep = [v for v in b.road.vehicles if v is new or rng.random() > 0.3]
    b.road.vehicles[:] = keep
    for v in keep:
        if v is not new:
            v.position[0] += rng.normal(0, 5)
    keep.sort(key=lambda v: v.position[0])
    last = {}; kept = []
    for v in keep:  # 같은 차선 간격 10 m 미만이면 제거 (초기 겹침 방지)
        ln = v.lane_index[2]
        if ln in last and v.position[0] - last[ln] < 10 and v is not new:
            continue
        last[ln] = v.position[0]; kept.append(v)
    b.road.vehicles[:] = kept
    for v in kept:
        v.check_collisions = True
        v.warned = False
    return env, b, rng

def patch(v, hazard_ref):
    def act(self, action=None):
        if self.crashed:
            return
        IDMVehicle.act(self)
        a = self.action["acceleration"]
        h = hazard_ref[0]
        if h is not None and self.warned and self is not h:
            d = h.position[0] - self.position[0]
            xs = np.array([h.position[0], self.position[0]]); vs = np.array([h.speed, self.speed])
            R = core.risk(xs, vs)[1] if d > 0 else 0
            if R >= core.T and self.speed > h.speed + 2:
                a = min(a, -3.0)
            a = max(a, -6.0)
        else:
            fv, _ = self.road.neighbour_vehicles(self, self.lane_index)
            braking = fv is not None and getattr(fv, "action", {}).get("acceleration", 0) < -2
            self.react_t = (getattr(self, "react_t", 0.0) + 1 / 15) if braking else 0.0
            if braking and self.react_t < REACT:
                a = max(a, 0.0) if a > -B_UNW else max(getattr(self, "a_prev", 0.0), -1.0)
            a = max(a, -B_UNW)
        self.a_prev = a
        self.action["acceleration"] = a
    v.act = types.MethodType(act, v)

def run(seed, make, r, loss):
    env, b, rng = setup(seed)
    hazard = [None]
    for v in b.road.vehicles:
        patch(v, hazard)
    lead = max(b.road.vehicles, key=lambda v: v.position[0])
    pr = np.random.default_rng(seed)
    tx = 0; min_ttc = np.inf; pre_crash = 0; expo = 0.0
    for k in range(int(14 / DT_POLICY)):
        t = k * DT_POLICY
        if hazard[0] is None and t >= 2.0:
            hazard[0] = lead; P_brake(lead)
            pre_crash = sum(v.crashed for v in b.road.vehicles)
        if hazard[0] is not None and make is not None and abs((t - 2.0) % 1.0) < 1e-9:
            vs = [lead] + [v for v in b.road.vehicles if v is not lead]
            x = np.array([v.position[0] for v in vs]); y = np.array([v.position[1] for v in vs]); sp = np.array([v.speed for v in vs])
            out = core.simulate(x, y, sp, r, loss, make(pr), pr, return_rx=True, area=AREA0 + GROW * (t - 2.0))
            tx += out["tx"]
            for v, g in zip(vs, out["got"]):
                v.warned = v.warned or bool(g)
        env.step(0)
        for v in b.road.vehicles:  # 같은 차선 앞차와 TTC
            if v is lead or (v.crashed and getattr(v, 'was_crashed', False)):
                continue
            v.was_crashed = v.crashed
            fv, _ = b.road.neighbour_vehicles(v, v.lane_index)
            if fv is not None and v.speed > fv.speed:
                ttc = (fv.position[0] - v.position[0] - 5) / (v.speed - fv.speed)
                min_ttc = min(min_ttc, ttc)
                if hazard[0] is not None and ttc < 1.5:
                    expo += DT_POLICY  # TTC<1.5 s 노출 (차량·초)
    crashed = sum(v.crashed for v in b.road.vehicles) - pre_crash
    env.close()
    return dict(crashed=crashed, any_crash=int(crashed > 0), min_ttc=min_ttc, expo=expo, tx=tx)

def P_brake(v):
    def act(self, action=None):
        acc = -min(6.0, self.speed * 15)
        Vehicle.act(self, {"steering": self.steering_control(self.target_lane_index), "acceleration": acc})
    v.act = types.MethodType(act, v)

if __name__ == "__main__":
    M = {"no V2V": None, "threshold": lambda pr: P.Threshold(), "flooding": lambda pr: P.Flooding(),
         "dist-timer": lambda pr: P.DistTimer(), "RAC-U": lambda pr: P.UrgencyRAC4(1.0, 0.05)}
    rows = []
    for (k, f), loss, s in itertools.product(M.items(), (0.0, 0.3), range(SEED0, SEED0 + 40)):
        if f is None and loss > 0:
            continue
        rows.append(dict(policy=k, loss=loss, seed=s, **run(s, f, 100.0, loss)))
    D = pd.DataFrame(rows); D.to_csv(f"results/hw_safety_{SEED0}_B{B_UNW}_R{REACT}_H{HEADWAY}_G{GROW}.csv", index=False)
    print(D.groupby(["policy", "loss"]).agg(crash_rate=("any_crash", "mean"), crashed=("crashed", "mean"),
                                           min_ttc=("min_ttc", "median"), expo=("expo", "mean"), tx=("tx", "mean")).round(3).to_string())
