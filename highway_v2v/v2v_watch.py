"""highway-env V2V 경고 전파를 눈으로 보는 뷰어 (LunarLander처럼 창으로 재생).

맨 앞 차량이 급정거하면 1초마다 경고를 보내고, 선택한 정책으로 다중 홉 전파한다.
  빨강 = 급정거 차량, 파랑 = 경고 받음, 주황 = 방금 재전송, 회색 = 아직 못 받음
  주황 선 = 이번 경고가 실제로 지나간 링크, 빨간 원 = 급정거 차량의 통신 반경

사용 예 (본인 PC, 창 띄우기):
  python v2v_watch.py --policy threshold
  python v2v_watch.py --policy flooding --seed 3 --radius 150
GIF로 저장 (창 없이):
  python v2v_watch.py --policy threshold --save out/threshold.gif

창 조작: L/K 확대·축소, 방향키는 무시, 창 닫으면 종료.
"""

import argparse
import os

import gymnasium as gym
import highway_env  # noqa: F401
import numpy as np
import pygame
from highway_env.vehicle.behavior import IDMVehicle

from v2v_test import AFFECT_RANGE, T, W, make_brake, propagate, risk

RED, BLUE, ORANGE, GRAY = (220, 50, 50), (60, 120, 220), (255, 150, 0), (175, 175, 175)
POLICY_DESC = {
    "flooding": "flooding (받으면 모두 재전송)",
    "threshold": f"역치 방식 (R ≥ {T}일 때만 재전송)",
}


class V2VView:
    """전파 상태를 들고 있다가 뷰어 콜백에서 그린다."""

    def __init__(self, args):
        self.args = args
        self.hazard = None
        self.warned = set()      # 한 번이라도 경고 받은 차량 (id)
        self.links = []          # 가장 최근 경고의 (보낸 차량, 받은 차량)
        self.last_relays = set()
        self.tx_total = 0
        self.t = 0.0
        self.first = None        # 급정거 직후 첫 경고 결과
        self.affected = []
        self.font = None

    # --- 시뮬레이션 쪽 ---
    def beacon(self, vehicles):
        parent = {}
        rec, relays, _ = propagate(vehicles, self.hazard, self.hazard,
                                   self.args.radius, self.args.policy, parent)
        self.links = [(vehicles[p], vehicles[c]) for c, p in parent.items()]
        self.last_relays = {id(vehicles[i]) for i in relays}
        self.warned |= {id(vehicles[i]) for i in rec}
        self.tx_total += len(relays)
        self.affected = [v for v in vehicles if v is not self.hazard
                         and 0 < self.hazard.position[0] - v.position[0] <= AFFECT_RANGE]
        if self.first is None:
            got = sum(id(v) in self.warned for v in self.affected)
            self.first = (got, len(self.affected), len(relays))

    def recolor(self, vehicles):
        for v in vehicles:
            if v is self.hazard:
                v.color = RED
            elif id(v) in self.last_relays:
                v.color = ORANGE
            elif id(v) in self.warned:
                v.color = BLUE
            else:
                v.color = GRAY

    # --- 그리기 쪽 (highway-env 뷰어 콜백) ---
    def draw(self, panel, sim):
        if self.hazard is not None:
            c = sim.vec2pix(self.hazard.position)
            pygame.draw.circle(sim, RED, c, sim.pix(self.args.radius), 1)
            for a, b in self.links:
                pygame.draw.line(sim, ORANGE, sim.vec2pix(a.position), sim.vec2pix(b.position), 2)
        self.draw_panel(panel)

    def draw_panel(self, panel):
        if self.font is None:
            pygame.font.init()
            names = "malgungothic,applegothic,nanumgothic,notosanscjkkr"
            self.font = pygame.font.SysFont(names, 18)
            self.small = pygame.font.SysFont(names, 15)
        panel.fill((255, 255, 255))
        a = self.args
        since = f"급정거 후 {self.t - a.brake_at:4.1f} s" if self.hazard else f"급정거까지 {a.brake_at - self.t:4.1f} s"
        lines = [
            f"정책: {POLICY_DESC[a.policy]}   |   t = {self.t:4.1f} s ({since})   |   반경 {a.radius:.0f} m",
        ]
        if self.hazard is not None:
            n = len(self.affected)
            got = sum(id(v) in self.warned for v in self.affected)
            lines.append(f"영향 차량(후방 {AFFECT_RANGE} m) 경고 수신: {got}/{n} ({got / max(n, 1) * 100:.0f}%)"
                         f"   |   누적 재전송 {self.tx_total}회")
            g, n0, tx0 = self.first
            lines.append(f"첫 경고 결과: 도달 {g}/{n0}, 재전송 {tx0}회")
            bar_w = panel.get_width() - 40
            pygame.draw.rect(panel, (230, 230, 230), (20, 105, bar_w, 14))
            pygame.draw.rect(panel, BLUE, (20, 105, int(bar_w * got / max(n, 1)), 14))
        for k, s in enumerate(lines):
            panel.blit(self.font.render(s, True, (20, 20, 20)), (20, 12 + 28 * k))
        x = 20
        for col, name in [(RED, "급정거 차량"), (ORANGE, "방금 재전송"), (BLUE, "경고 받음"), (GRAY, "못 받음")]:
            pygame.draw.rect(panel, col, (x, 140, 16, 10))
            panel.blit(self.small.render(name, True, (60, 60, 60)), (x + 22, 136))
            x += 140
        w = ", ".join(f"{v:.2f}" for v in W)
        panel.blit(self.small.render(f"R 가중치(거리, 접근속도, TTC) = [{w}]", True, (90, 90, 90)), (x + 20, 136))


def make_ego_idm(base):
    """자차도 IDM으로 달리게 바꾼다 (그대로 두면 정지 차량에 그대로 박음)."""
    old = base.vehicle
    new = IDMVehicle.create_from(old)
    base.road.vehicles[base.road.vehicles.index(old)] = new
    base.controlled_vehicles = [new]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["flooding", "threshold"], default="threshold")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--vehicles", type=int, default=20)
    ap.add_argument("--radius", type=float, default=100.0)
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--brake-at", type=float, default=3.0)
    ap.add_argument("--scaling", type=float, default=3.0, help="픽셀/m (작을수록 넓게 보임)")
    ap.add_argument("--save", default=None, help="GIF 경로. 주면 창 없이 저장만")
    args = ap.parse_args()

    width, height = 1400, 170
    env = gym.make("highway-v0", render_mode="rgb_array" if args.save else "human", config={
        "lanes_count": 3,
        "vehicles_count": args.vehicles,
        "duration": args.duration,
        "simulation_frequency": 15,
        "policy_frequency": 5,
        "screen_width": width,
        "screen_height": height,
        "scaling": args.scaling,
        "centering_position": [0.88, 0.5],
        "real_time_rendering": True,
        "offscreen_rendering": bool(args.save),
    })
    env.reset(seed=args.seed)
    base = env.unwrapped
    make_ego_idm(base)

    view = V2VView(args)
    lead = max(base.road.vehicles, key=lambda v: v.position[0])
    view.recolor(base.road.vehicles)
    env.render()
    base.viewer.set_agent_display(view.draw)
    base.viewer.observer_vehicle = lead  # 카메라는 급정거할 차량을 따라감

    frames = []
    for k in range(int(args.duration * 5)):
        view.t = k / 5
        if view.hazard is None and view.t >= args.brake_at:
            view.hazard = lead
            make_brake(lead)
        if view.hazard is not None and abs((view.t - args.brake_at) % 1.0) < 1e-9:
            view.beacon(list(base.road.vehicles))
        view.recolor(base.road.vehicles)
        try:
            _, _, term, trunc, _ = env.step(0)
        except pygame.error:  # 창을 닫음
            break
        if args.save:
            img = env.render()
            panel = np.moveaxis(pygame.surfarray.array3d(base.viewer.agent_surface), 0, 1)
            frames.append(np.vstack([img, panel]))
        if term or trunc:
            break

    if view.first:
        g, n, tx = view.first
        n_last = len(view.affected)
        got_last = sum(id(v) in view.warned for v in view.affected)
        print(f"[{args.policy}] 첫 경고 도달 {g}/{n}, 재전송 {tx}회 | 종료 시 누적 수신 {got_last}/{n_last}, 누적 재전송 {view.tx_total}회")
    env.close()

    if args.save:
        from PIL import Image
        os.makedirs(os.path.dirname(os.path.abspath(args.save)), exist_ok=True)
        ims = [Image.fromarray(f) for f in frames]
        ims[0].save(args.save, save_all=True, append_images=ims[1:], duration=100, loop=0)
        print("저장:", args.save, f"({len(frames)}프레임, 2배속)")


if __name__ == "__main__":
    main()
