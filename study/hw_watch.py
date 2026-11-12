"""같은 시드에서 여러 전달 방식을 나란히 재생하는 비교 GIF.

빨강 = 급정거 차량, 주황 = 이번 경고 때 재전송, 파랑 = 경고 받음, 회색 = 못 받음, 검정 = 충돌
python hw_watch.py --seed 1 --loss 0.3 --out results/watch_seed1.gif
(가정은 hw_safety.py와 동일: 차간 0.6 s, 미경고 반응 지연 1.0 s, 제동 한계 4 m/s^2)
"""
import argparse
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--loss", type=float, default=0.3)
ap.add_argument("--radius", type=float, default=100.0)
ap.add_argument("--out", default="results/watch.gif")
ap.add_argument("--scaling", type=float, default=2.2)
args = ap.parse_args()
sys.argv = ["hw_safety.py", "0", "4.0", "1.0", "0.6"]

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import core  # noqa: E402
import hw_safety as H  # noqa: E402
import policies as P  # noqa: E402

RED, BLUE, ORANGE, GRAY, BLACK = (220, 50, 50), (60, 120, 220), (255, 150, 0), (175, 175, 175), (20, 20, 20)
POL = {
    "경고 없음": None,
    "역치 방식 (선행 탐구)": lambda pr: P.Threshold(),
    "거리 타이머 (선행연구)": lambda pr: P.DistTimer(),
    "RAC-U (제안)": lambda pr: P.UrgencyRAC4(1.0, 0.05),
}
FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def episode(make, W=1300, Hh=150):
    env, b, rng = H.setup(args.seed)
    env.unwrapped.config.update({"screen_width": W, "screen_height": Hh, "scaling": args.scaling,
                                 "centering_position": [0.85, 0.5], "offscreen_rendering": True})
    env.unwrapped.render_mode = "rgb_array"
    hz = [None]
    for v in b.road.vehicles:
        H.patch(v, hz)
    lead = max(b.road.vehicles, key=lambda v: v.position[0])
    env.unwrapped.render()
    b.viewer.observer_vehicle = lead
    pr = np.random.default_rng(args.seed)
    relays, tx, frames, stats = set(), 0, [], []
    for k in range(int(14 / 0.2)):
        t = k * 0.2
        if hz[0] is None and t >= 2.0:
            hz[0] = lead; H.P_brake(lead)
            pre = sum(v.crashed for v in b.road.vehicles)
        if hz[0] is not None and make is not None and abs((t - 2.0) % 1.0) < 1e-9:
            vs = [lead] + [v for v in b.road.vehicles if v is not lead]
            x = np.array([v.position[0] for v in vs]); y = np.array([v.position[1] for v in vs])
            sp = np.array([v.speed for v in vs])
            out = core.simulate(x, y, sp, args.radius, args.loss, make(pr), pr, return_rx=True)
            tx += out["tx"]; relays = {id(vs[i]) for i in out["sent"]}
            for v, g in zip(vs, out["got"]):
                v.warned = v.warned or bool(g)
        elif k % 2 == 1:
            relays = set()
        for v in b.road.vehicles:
            v.color = (BLACK if v.crashed else RED if v is lead and hz[0] is not None else
                       ORANGE if id(v) in relays else BLUE if v.warned else GRAY)
        env.step(0)
        img = env.unwrapped.render()
        crashed = sum(v.crashed for v in b.road.vehicles) - (pre if hz[0] is not None else 0)
        warned = sum(v.warned for v in b.road.vehicles if v is not lead)
        frames.append(img); stats.append((t, crashed, warned, len(b.road.vehicles) - 1, tx))
    env.close()
    return frames, stats


def main():
    font = ImageFont.truetype(FONT, 17); small = ImageFont.truetype(FONT, 14)
    runs = {k: episode(f) for k, f in POL.items()}
    n = min(len(fr) for fr, _ in runs.values())
    out = []
    for i in range(n):
        rows = []
        for name, (fr, st) in runs.items():
            t, cr, w, tot, tx = st[i]
            im = Image.fromarray(fr[i]); h = im.height
            canvas = Image.new("RGB", (im.width, h + 30), "white"); canvas.paste(im, (0, 30))
            d = ImageDraw.Draw(canvas)
            col = (200, 0, 0) if cr else (20, 20, 20)
            d.text((10, 5), f"{name}", font=font, fill=(20, 20, 20))
            d.text((330, 7), f"경고 수신 {w}/{tot}대   누적 재전송 {tx}회   충돌 {cr}대", font=small, fill=col)
            rows.append(canvas)
        W = rows[0].width; Ht = sum(r.height for r in rows) + 34
        frame = Image.new("RGB", (W, Ht), "white"); y = 0
        d = ImageDraw.Draw(frame)
        d.text((10, 8), f"t = {st[i][0]:4.1f} s  (급정거 2.0 s)   손실 {args.loss*100:.0f}%  반경 {args.radius:.0f} m  시드 {args.seed}"
                         "     빨강 급정거 · 주황 재전송 · 파랑 경고 받음 · 회색 못 받음 · 검정 충돌", font=small, fill=(60, 60, 60))
        y = 34
        for r in rows:
            frame.paste(r, (0, y)); y += r.height
        out.append(frame)
    out[0].save(args.out, save_all=True, append_images=out[1:], duration=150, loop=0)
    last = {k: st[n - 1] for k, (_, st) in runs.items()}
    for k, (t, cr, w, tot, tx) in last.items():
        print(f"{k:16s} 경고 {w}/{tot}  재전송 {tx}  충돌 {cr}")
    print("저장:", args.out, f"{n}프레임")


if __name__ == "__main__":
    main()
