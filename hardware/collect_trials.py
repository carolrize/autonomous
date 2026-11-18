"""AS5600 시행 데이터 수집기.

q + Enter : 시행 시작 (그 위치가 0°)  /  다시 q + Enter : 시행 끝 -> 저장
z + Enter : 영점 다시 맞춤
s + Enter : 자석 상태
x + Enter : 종료

저장 위치
  data/trials.csv          시행마다 한 줄 (최대 각도 등 요약)
  data/raw/trial_001.csv   시행별 전체 시계열 (1D CNN 입력용)

실행: python collect_trials.py COM3
"""
import csv
import os
import sys
import threading
import time
from datetime import datetime

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
BAUD = 115200
DATA_DIR = "data"
RAW_DIR = os.path.join(DATA_DIR, "raw")
SUMMARY = os.path.join(DATA_DIR, "trials.csv")
FIELDS = ["trial", "time", "n_samples", "duration_ms",
          "max_deg", "min_deg", "final_deg", "raw_file"]

recording = False
samples = []          # (t_ms, count, deg)
lock = threading.Lock()
stop_flag = False


def next_trial_no():
    if not os.path.exists(SUMMARY):
        return 1
    with open(SUMMARY, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return int(rows[-1]["trial"]) + 1 if rows else 1


def reader(ser):
    while not stop_flag:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue
        if line.startswith("#"):
            print(line)
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue            # 헤더(t_ms,count,deg) 등은 건너뜀
        try:
            t, c, d = int(parts[0]), int(parts[1]), float(parts[2])
        except ValueError:
            continue
        with lock:
            if recording:
                samples.append((t, c, d))


def save_trial(no, data):
    os.makedirs(RAW_DIR, exist_ok=True)
    raw_file = os.path.join(RAW_DIR, f"trial_{no:03d}.csv")
    with open(raw_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_ms", "count", "deg"])
        w.writerows(data)

    degs = [d for _, _, d in data]
    row = {
        "trial": no,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_samples": len(data),
        "duration_ms": data[-1][0] - data[0][0],
        "max_deg": round(max(degs), 2),
        "min_deg": round(min(degs), 2),
        "final_deg": round(degs[-1], 2),
        "raw_file": raw_file,
    }
    new = not os.path.exists(SUMMARY)
    with open(SUMMARY, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def main():
    global recording, stop_flag
    os.makedirs(DATA_DIR, exist_ok=True)
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(2)                       # ESP32 리셋 대기
    ser.reset_input_buffer()
    th = threading.Thread(target=reader, args=(ser,), daemon=True)
    th.start()

    trial = next_trial_no()
    print(f"연결됨: {PORT}  /  다음 시행 번호: {trial}")
    print("q: 시작/끝   z: 영점   s: 자석 상태   x: 종료  (입력 후 Enter)")

    try:
        while True:
            cmd = input().strip().lower()
            if cmd == "q":
                if not recording:
                    with lock:
                        samples.clear()
                        recording = True
                    ser.write(b"q")
                    print(f"[시행 {trial}] 기록 중... 문을 밀고, 멈추면 q")
                else:
                    ser.write(b"q")
                    time.sleep(0.2)     # 남은 줄 받기
                    with lock:
                        recording = False
                        data = list(samples)
                    if len(data) < 2:
                        print("데이터가 없어 저장하지 않음 (센서 연결 확인)")
                        continue
                    row = save_trial(trial, data)
                    print(f"[시행 {trial}] 저장  최대 {row['max_deg']}°  "
                          f"최종 {row['final_deg']}°  "
                          f"{row['duration_ms']} ms, {row['n_samples']}개")
                    trial += 1
            elif cmd in ("z", "s"):
                ser.write(cmd.encode())
            elif cmd == "x":
                if recording:
                    ser.write(b"q")     # ESP32 측정 정지 (저장은 안 함)
                break
    finally:
        stop_flag = True
        time.sleep(0.2)
        ser.close()
        print("종료")


if __name__ == "__main__":
    main()
