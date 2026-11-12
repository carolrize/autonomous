"""실시간 시뮬레이션 뷰어: 시뮬레이션이 도는 동안 화면을 브라우저로 스트리밍.

같은 시드에서 4가지 방식(경고 없음 / 역치 / 거리 타이머 / RAC-U)을 동시에 한 스텝씩 진행하고,
매 스텝 화면을 http://localhost:PORT 로 보낸다. 시드가 끝나면 다음 시드로 넘어가며 누적 통계를 표시.

python live.py --loss 0.3 --speed 1.0 --port 8000
  --speed 1.0 = 실제 시간, 2.0 = 2배속, 0 = 최대 속도
가정은 hw_safety.py와 동일 (차간 0.6 s, 미경고 반응 지연 1.0 s, 미경고 제동 한계 4 m/s^2).
"""
import argparse
import io
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--loss", type=float, default=0.3)
ap.add_argument("--radius", type=float, default=100.0)
ap.add_argument("--seed0", type=int, default=0)
ap.add_argument("--seeds", type=int, default=40)
ap.add_argument("--speed", type=float, default=1.0)
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--scaling", type=float, default=2.6)
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
try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 17)
    SMALL = ImageFont.truetype("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 14)
except OSError:  # 본인 PC(윈도우)
    FONT = ImageFont.truetype("malgun.ttf", 17)
    SMALL = ImageFont.truetype("malgun.ttf", 14)

latest = {"jpg": None}
cond = threading.Condition()


class Run:
    """한 방식의 에피소드 하나를 스텝 단위로 진행."""

    def __init__(self, seed, make):
        self.make = make
        self.env, self.b, _ = H.setup(seed)
        u = self.env.unwrapped
        u.config.update({"screen_width": 1300, "screen_height": 110, "scaling": args.scaling,
                         "centering_position": [0.85, 0.5], "offscreen_rendering": True})
        u.render_mode = "rgb_array"
        self.hz = [None]
        for v in self.b.road.vehicles:
            H.patch(v, self.hz)
        self.lead = max(self.b.road.vehicles, key=lambda v: v.position[0])
        u.render()
        self.b.viewer.observer_vehicle = self.lead
        self.pr = np.random.default_rng(seed)
        self.tx, self.relays, self.pre, self.k = 0, set(), 0, 0
        self.min_ttc = np.inf

    def step(self):
        t = self.k * 0.2
        b, lead = self.b, self.lead
        if self.hz[0] is None and t >= 2.0:
            self.hz[0] = lead; H.P_brake(lead)
            self.pre = sum(v.crashed for v in b.road.vehicles)
        if self.hz[0] is not None and self.make is not None and abs((t - 2.0) % 1.0) < 1e-9:
            vs = [lead] + [v for v in b.road.vehicles if v is not lead]
            x = np.array([v.position[0] for v in vs]); y = np.array([v.position[1] for v in vs])
            sp = np.array([v.speed for v in vs])
            out = core.simulate(x, y, sp, args.radius, args.loss, self.make(self.pr), self.pr, return_rx=True)
            self.tx += out["tx"]; self.relays = {id(vs[i]) for i in out["sent"]}
            for v, g in zip(vs, out["got"]):
                v.warned = v.warned or bool(g)
        elif self.k % 2 == 1:
            self.relays = set()
        for v in b.road.vehicles:
            v.color = (BLACK if v.crashed else RED if (v is lead and self.hz[0] is not None) else
                       ORANGE if id(v) in self.relays else BLUE if v.warned else GRAY)
        self.env.step(0)
        for v in b.road.vehicles:
            if v is lead or v.crashed:
                continue
            fv, _ = b.road.neighbour_vehicles(v, v.lane_index)
            if fv is not None and v.speed > fv.speed:
                self.min_ttc = min(self.min_ttc, (fv.position[0] - v.position[0] - 5) / (v.speed - fv.speed))
        self.k += 1
        return self.env.unwrapped.render()

    def stats(self):
        b = self.b
        crashed = sum(v.crashed for v in b.road.vehicles) - (self.pre if self.hz[0] is not None else 0)
        warned = sum(v.warned for v in b.road.vehicles if v is not self.lead)
        return crashed, warned, len(b.road.vehicles) - 1, self.tx


def compose(t, seed, imgs, runs, totals, done):
    rows = []
    for (name, r), img in zip(runs.items(), imgs):
        cr, w, tot, tx = r.stats()
        im = Image.fromarray(img)
        c = Image.new("RGB", (im.width, im.height + 28), "white"); c.paste(im, (0, 28))
        d = ImageDraw.Draw(c)
        d.text((10, 4), name, font=FONT, fill=(20, 20, 20))
        tt = totals[name]
        avg = f"   |   누적 {done}시드: 충돌 발생 {tt['crash_eps']}회, 평균 재전송 {tt['tx'] / max(done, 1):.0f}" if done else ""
        d.text((300, 6), f"경고 {w}/{tot}대   재전송 {tx}회   충돌 {cr}대{avg}", font=SMALL,
               fill=(200, 0, 0) if cr else (20, 20, 20))
        rows.append(c)
    W = rows[0].width
    frame = Image.new("RGB", (W, sum(r.height for r in rows) + 32), "white")
    d = ImageDraw.Draw(frame)
    d.text((10, 8), f"시드 {seed}   t = {t:4.1f} s (급정거 2.0 s)   손실 {args.loss * 100:.0f}%   반경 {args.radius:.0f} m"
                    "     빨강 급정거 · 주황 재전송 · 파랑 경고 받음 · 회색 못 받음 · 검정 충돌", font=SMALL, fill=(60, 60, 60))
    y = 32
    for r in rows:
        frame.paste(r, (0, y)); y += r.height
    buf = io.BytesIO(); frame.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def sim_loop():
    totals = {k: {"crash_eps": 0, "tx": 0} for k in POL}
    done = 0
    for seed in range(args.seed0, args.seed0 + args.seeds):
        runs = {k: Run(seed, f) for k, f in POL.items()}
        for k in range(int(14 / 0.2)):
            t0 = time.time()
            imgs = [r.step() for r in runs.values()]
            jpg = compose(k * 0.2, seed, imgs, runs, totals, done)
            with cond:
                latest["jpg"] = jpg; cond.notify_all()
            if args.speed > 0:
                time.sleep(max(0.0, 0.2 / args.speed - (time.time() - t0)))
        for name, r in runs.items():
            cr, _, _, tx = r.stats()
            totals[name]["crash_eps"] += int(cr > 0); totals[name]["tx"] += tx
            r.env.close()
        done += 1
        print(f"시드 {seed} 끝: " + " | ".join(f"{k} 충돌 {totals[k]['crash_eps']} 재전송 {totals[k]['tx'] / done:.0f}" for k in POL), flush=True)


PAGE = b"""<!doctype html><html><head><meta charset="utf-8"><title>V2V live</title>
<style>body{margin:0;background:#fff;font-family:sans-serif}img{width:100%;height:auto;display:block}</style></head>
<body><img src="/stream"></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    with cond:
                        cond.wait(timeout=5)
                        jpg = latest["jpg"]
                    if jpg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                     str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE)


if __name__ == "__main__":
    threading.Thread(target=sim_loop, daemon=True).start()
    print(f"브라우저에서 http://localhost:{args.port} 열기", flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
