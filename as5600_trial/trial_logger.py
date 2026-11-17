"""AS5600 시행별 기록기.

q: 시행 시작/종료 (종료 시 trials/trial_001.csv 처럼 저장)
s: 자석 상태 확인
x: 종료 (기록 중이면 먼저 그 시행을 끝내고 저장)

사용: python trial_logger.py COM5
      python trial_logger.py /dev/ttyUSB0 --out data
필요: pip install pyserial
"""
import argparse
import os
import re
import sys
import threading
import time

import serial


# ---------- 키 입력 (한 글자, Enter 불필요) ----------
class Keys:
    def __init__(self):
        self.win = os.name == "nt"
        self.tty = sys.stdin.isatty()
        self.old = None
        if not self.win and self.tty:
            import termios
            import tty
            self.old = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

    def get(self):
        """키 하나를 돌려줌. 없으면 None (최대 0.1초 대기)."""
        if self.win:
            import msvcrt
            if msvcrt.kbhit():
                return msvcrt.getwch()
            time.sleep(0.02)
            return None
        if self.tty:
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            return sys.stdin.read(1) if r else None
        line = sys.stdin.readline()          # 파이프 입력(테스트용)
        if line == "":
            return "x"
        return line.strip()[:1] or None

    def close(self):
        if self.old is not None:
            import termios
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old)


# ---------- 기록기 ----------
class TrialLogger:
    def __init__(self, ser, outdir):
        self.ser = ser
        self.outdir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.f = None
        self.path = None
        self.rows = []          # (t_ms, total_deg, vel_dps)
        self.alive = True
        self.recording = False

    def next_path(self):
        nums = [int(m.group(1)) for n in os.listdir(self.outdir)
                if (m := re.fullmatch(r"trial_(\d+)\.csv", n))]
        return os.path.join(self.outdir, f"trial_{max(nums, default=0) + 1:03d}.csv")

    def open_trial(self):
        self.path = self.next_path()
        self.f = open(self.path, "w", newline="")
        self.rows = []
        self.recording = True
        print(f"\n[기록 시작] {self.path}")

    def close_trial(self, end_line=""):
        if self.f is None:
            return
        self.f.close()
        self.f = None
        self.recording = False
        if self.rows:
            t0, t1 = self.rows[0][0], self.rows[-1][0]
            dur = (t1 - t0) / 1000
            net = self.rows[-1][1]
            vmax = max(abs(r[2]) for r in self.rows)
            vmean = net / dur if dur > 0 else 0.0
            print(f"\n[저장] {self.path}  샘플 {len(self.rows)}개, {dur:.2f}s, "
                  f"누적 {net:.1f}°, 평균 각속도 {vmean:.1f}°/s, 최대 |ω| {vmax:.1f}°/s")
        else:
            print(f"[저장] {self.path}  (샘플 없음)")
        if end_line:
            print("  ESP32:", end_line)
        self.update_summary()

    def update_summary(self):
        """trials/summary.csv: 시행별 요약 한 줄씩."""
        if not self.rows:
            return
        t0, t1 = self.rows[0][0], self.rows[-1][0]
        dur = (t1 - t0) / 1000
        net = self.rows[-1][1]
        vmax = max(abs(r[2]) for r in self.rows)
        vmean = net / dur if dur > 0 else 0.0
        spath = os.path.join(self.outdir, "summary.csv")
        new = not os.path.exists(spath)
        with open(spath, "a", newline="") as s:
            if new:
                s.write("file,samples,dur_s,total_deg,mean_vel_dps,max_abs_vel_dps,saved_at\n")
            s.write(f"{os.path.basename(self.path)},{len(self.rows)},{dur:.3f},"
                    f"{net:.2f},{vmean:.2f},{vmax:.2f},{time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    def reader(self):
        while self.alive:
            try:
                raw = self.ser.readline()
            except serial.SerialException as e:
                print("\n[시리얼 끊김]", e)
                self.close_trial()
                self.alive = False
                break
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith("# START"):
                self.open_trial()
            elif line.startswith("# END"):
                self.close_trial(line)
            elif line.startswith("#"):
                print(line)
            elif self.f is not None:
                self.f.write(line + "\n")
                parts = line.split(",")
                if len(parts) >= 5 and parts[0] != "t_ms":
                    try:
                        self.rows.append((float(parts[0]), float(parts[3]), float(parts[4])))
                    except ValueError:
                        pass
                    if len(self.rows) % 40 == 0:     # 0.2초마다 현재 값 표시
                        t, a, v = self.rows[-1]
                        print(f"\r  t={t/1000:6.2f}s  각도={a:8.1f}°  ω={v:8.1f}°/s ",
                              end="", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", help="예: COM5, /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default="trials", help="저장 폴더")
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.2)
    time.sleep(2.0)                 # 포트 열 때 ESP32가 리셋되는 시간
    log = TrialLogger(ser, args.out)
    th = threading.Thread(target=log.reader, daemon=True)
    th.start()

    print("q: 시행 시작/종료   s: 자석 상태   x: 끝내기")
    keys = Keys()
    try:
        while log.alive:
            k = keys.get()
            if k is None:
                continue
            k = k.lower()
            if k == "q":
                ser.write(b"q")
            elif k == "s":
                ser.write(b"s")
            elif k == "x":
                if log.recording:
                    ser.write(b"q")
                    for _ in range(20):           # END 받을 때까지 최대 2초
                        if not log.recording:
                            break
                        time.sleep(0.1)
                    log.close_trial()             # END를 못 받았어도 저장
                break
    except KeyboardInterrupt:
        if log.recording:
            ser.write(b"q")
            time.sleep(0.5)
            log.close_trial()
    finally:
        keys.close()
        log.alive = False
        th.join(timeout=1)
        ser.close()
        print("\n끝")


if __name__ == "__main__":
    main()
