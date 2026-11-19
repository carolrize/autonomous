# ESP_Door 인수인계 (붙여넣기용 전체본)

> 이 파일 하나에 상황 정리와 코드 두 개가 모두 들어 있음.
> 받는 세션은 아래 "코드 파일" 두 개를 작업 폴더에 그대로 저장한 뒤, "다음 할 일" 1번부터 진행할 것.


브랜치 `claude/brave-johnson-44g2or`, 폴더 `hardware/`

## 목표
문을 처음에 한 번 밀었을 때 초기 움직임만 보고 최대 회전각 θ_max를 1D CNN으로 예측함.
그 값을 미리 입력한 장애물 각도와 비교해서 "닿음"이면 LED를 켬.
힘은 처음 밀 때만 주고, 문은 관성으로 가다가 마찰로 멈춤.

## 실험 설계 (사용자와 합의함)
- 학습: 장애물 없이, 미는 세기를 약~강으로 다양하게 해서 θ_max를 기록함. CNN은 θ_max 회귀
- 평가: 실제 장애물을 두고 따로 수집함. 예측 θ_max ≥ 장애물 각도면 닿음. 실제 닿음 여부와 비교
- 비교용 기준선: 물리식 θ_max ≈ ω₀² / (2α)
- 실시간 예측은 노트북(Python)에서 함. ESP32는 측정과 LED만 담당 (노트북 연결 가능)
- 학습은 코랩에서 해도 됨. 수집과 실시간 예측은 USB 때문에 노트북에서만 가능

## 하드웨어
- 보드: ESP32 DevKit V1 30핀(CP2102, USB-C), 확장 보드에 꽂음. Arduino IDE 보드 설정 "DOIT ESP32 DEVKIT V1", 포트 COM3. 업로드 성공 확인함
- AS5600은 확장 보드 오른쪽 아래 4줄 I2C 헤더에 연결함 (위에서부터 D22=SCL, D21=SDA, VCC, GND, 바깥쪽 핀)
  - DIR은 왼쪽 아래 GND 블록의 왼쪽 열에 연결함
  - VCC 전압은 노란 점퍼로 정해짐. 사진상 3.3V 쪽으로 보이지만 측정으로 확인하지는 않음
  - 사진: `as5600_pins_right.jpg`, `as5600_pins_left.jpg`
- 구조 문제: 처음에 센서·선이 회전하는 쪽에 있어 선의 장력이 복원력으로 작용함(단진동). 센서를 고정부에, 자석을 축(볼트) 끝에 두도록 안내했고 사용자가 원인을 확인함. 실제로 고쳤는지는 확인하지 못함
- 자석은 직경 방향 착자 원판(6×2.5 mm)이어야 함. 칩 위 1~3 mm, 중심 맞춤
- LED(아직 연결 전일 수 있음): GPIO25 → 220~330 Ω → LED(+, 긴 다리) → LED(−) → GND. 확장 보드 D25 줄의 S열(신호)과 G열(GND)을 씀. V열은 쓰지 않음

## ESP32 코드: `as5600_logger/as5600_logger.ino` (업로드 완료)
- 200 Hz로 측정. 시리얼 115200 baud
- `q`: 측정 시작/정지. 시작 위치가 영점
- `z` 또는 BOOT 버튼(GPIO0): 현재 위치를 영점으로
- `s`: 자석 상태
- 출력 형식 `t_ms,count,deg`
  - `count` = 1000 + 영점 이후 이동량(4096칸이 1바퀴). 0↔4095 경계에서 튀지 않음
  - `deg` = 영점 기준 각도. 뒤로 가면 음수
- LED 제어 명령은 아직 없음. 실시간 예측 단계에서 추가해야 함

## PC 수집 스크립트: `collect_trials.py`
- 실행: `pip install pyserial` 후 `python collect_trials.py COM3`. Arduino 시리얼 모니터는 닫아야 함
- 명령(입력 후 Enter)
  - `q`: 시행 시작/끝
  - `a 60`: 평가용 장애물 각도
  - `a`: 장애물 없음
  - `z`, `s`, `x`(종료)
- 저장 위치
  - `data/trials.csv`: 시행마다 한 줄. 칼럼은 trial, time, obstacle_deg, hit, n_samples, duration_ms, max_deg, min_deg, final_deg, raw_file
  - `data/raw/trial_###.csv`: 시계열 t_ms, count, deg
- hit = max_deg ≥ obstacle_deg − 1°. 학습용 시행은 obstacle_deg와 hit가 비어 있음
- 가짜 시리얼로만 검증함. 실제 보드로는 아직 실행하지 않음

## 현재 상태와 다음 할 일
1. 사용자가 노트북에서 수집 스크립트를 실행하려는 단계임. 직전에 "데이터 측정이 안 된다"고 함. 시리얼 모니터에서 `q`를 보내야 출력이 시작된다고 안내했지만 해결됐는지는 확인하지 못함
2. LED 점등 테스트(GPIO25 깜빡임 코드는 안내함)
3. 장애물 없이 30~50회 수집. 미는 세기를 고르게 하고 시작 위치를 같게 함
4. 코랩용 1D CNN(θ_max 회귀) 학습 코드와 물리식 기준선 비교
   - 입력: 밀림 감지 후 약 100 ms 구간
   - 입력 구간 안에 이미 장애물에 닿는 경우를 주의할 것
5. 노트북용 실시간 예측 스크립트 작성. 예측이 닿음이면 ESP32에 LED 명령을 보냄. ESP32 코드에 LED 명령 추가 필요

## 사용자 성향
- 한국어로 짧고 단정적인 답을 선호함
- 코드는 전체를 붙여넣을 수 있게 달라고 함
- 하드웨어는 사진에 위치를 표시해 주는 것을 잘 받아들임
- 같은 확인 질문을 반복하면 답답해함

---

## 코드 파일 1: `as5600_logger/as5600_logger.ino` (ESP32에 이미 업로드됨, 다시 올릴 필요 없음)

```cpp
#include <Wire.h>

// ---- 핀 / 설정 ----
const int PIN_SDA = 21;
const int PIN_SCL = 22;
const int PIN_ZERO_BTN = 0;        // 보드의 BOOT 버튼 (GPIO0) = 영점 버튼
const uint32_t SAMPLE_US = 5000;   // 5 ms = 200 Hz
const int32_t  ZERO_COUNT = 1000;  // 영점 위치에서 count 값 (뒤로 1000칸 ≈ 88° 여유)

// ---- AS5600 레지스터 ----
const uint8_t AS5600_ADDR   = 0x36;
const uint8_t REG_STATUS    = 0x0B;  // bit5 MD(자석 감지), bit4 ML(약함), bit3 MH(강함)
const uint8_t REG_RAW_ANGLE = 0x0C;  // 12비트, 0~4095

// ---- 상태 ----
bool     measuring = false;  // q로 시작/정지
uint16_t zeroRaw = 0;        // 영점일 때의 raw 값
uint16_t prevRaw = 0;
int32_t  turnCount = 0;      // 영점 이후 누적 바퀴 수
uint32_t lastSampleUs = 0;
uint32_t startMs = 0;

bool readRegs(uint8_t reg, uint8_t* buf, uint8_t n) {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)AS5600_ADDR, (int)n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

bool readRawAngle(uint16_t& raw) {
  uint8_t b[2];
  if (!readRegs(REG_RAW_ANGLE, b, 2)) return false;
  raw = ((uint16_t)(b[0] & 0x0F) << 8) | b[1];
  return true;
}

void printMagnetStatus() {
  uint8_t st;
  if (!readRegs(REG_STATUS, &st, 1)) {
    Serial.println("# AS5600 응답 없음: 배선 확인");
    return;
  }
  if (!(st & 0x20))      Serial.println("# 자석이 감지되지 않음");
  else if (st & 0x10)    Serial.println("# 자석이 너무 약함(멀다)");
  else if (st & 0x08)    Serial.println("# 자석이 너무 강함(가깝다)");
  else                   Serial.println("# 자석 위치 정상");
}

// 현재 위치를 영점으로
void setZero() {
  uint16_t raw;
  if (!readRawAngle(raw)) {
    Serial.println("# 영점 실패: 센서 읽기 오류");
    return;
  }
  zeroRaw = raw;
  prevRaw = raw;
  turnCount = 0;
  Serial.println("# zero set");
}

void startMeasuring() {
  setZero();                       // 시작 위치 = 영점
  measuring = true;
  startMs = millis();
  lastSampleUs = micros();
  Serial.println("t_ms,count,deg");
}

void printHelp() {
  Serial.println("# q: 측정 시작/정지 (시작 위치가 영점=1000)");
  Serial.println("# z 또는 BOOT 버튼: 지금 위치를 영점(1000)으로");
  Serial.println("# s: 자석 상태");
}

void handleSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'q') {
      if (measuring) {
        measuring = false;
        Serial.println("# stop");
      } else {
        startMeasuring();
      }
    } else if (c == 'z') {
      setZero();
    } else if (c == 's') {
      printMagnetStatus();
    }
  }
}

// BOOT 버튼으로 영점 (누르는 순간 한 번)
void handleButton() {
  static bool lastPressed = false;
  static uint32_t lastChangeMs = 0;
  bool pressed = (digitalRead(PIN_ZERO_BTN) == LOW);
  if (pressed != lastPressed && millis() - lastChangeMs > 50) {
    lastChangeMs = millis();
    lastPressed = pressed;
    if (pressed) setZero();
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(PIN_ZERO_BTN, INPUT_PULLUP);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);

  Wire.beginTransmission(AS5600_ADDR);
  if (Wire.endTransmission() != 0) {
    Serial.println("# AS5600(0x36) 찾지 못함");
  }
  printMagnetStatus();
  printHelp();
}

void loop() {
  handleSerial();
  handleButton();
  if (!measuring) return;

  uint32_t now = micros();
  if (now - lastSampleUs < SAMPLE_US) return;
  lastSampleUs += SAMPLE_US;

  uint16_t raw;
  if (!readRawAngle(raw)) {
    Serial.println("# read error");
    return;
  }

  // 4095 <-> 0 경계를 넘을 때 바퀴 수 보정
  int16_t d = (int16_t)raw - (int16_t)prevRaw;
  if (d >  2048) turnCount--;
  if (d < -2048) turnCount++;
  prevRaw = raw;

  // 영점에서 움직인 양 (4095<->0 경계에서 튀지 않음, 뒤로 가면 음수)
  int32_t moved = turnCount * 4096 + (int32_t)raw - (int32_t)zeroRaw;
  // 영점 = 1000, 앞으로 가면 증가, 뒤로 가면 감소
  int32_t count = ZERO_COUNT + moved;

  Serial.printf("%lu,%ld,%.2f\n",
                (unsigned long)(millis() - startMs),
                (long)count,
                moved * 360.0f / 4096.0f);
}
```

## 코드 파일 2: `collect_trials.py` (노트북에서 실행)

```python
"""AS5600 시행 데이터 수집기.

a 60 + Enter : 장애물 각도 60° 설정 (평가할 때만. 학습용은 입력 안 함)
a + Enter    : 장애물 없음으로 되돌림
q + Enter : 시행 시작 (그 위치가 0°)  /  다시 q + Enter : 시행 끝 -> 저장
z + Enter : 영점 다시 맞춤
s + Enter : 자석 상태
x + Enter : 종료

저장 위치
  data/trials.csv          시행마다 한 줄 (최대 각도, 장애물 있으면 각도·닿음 여부)
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
HIT_MARGIN = 1.0      # 최대 각도가 (장애물 각도 - 1°) 이상이면 닿음으로 판정
FIELDS = ["trial", "time", "obstacle_deg", "hit", "n_samples", "duration_ms",
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


def save_trial(no, data, obstacle):
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
        "obstacle_deg": "" if obstacle is None else obstacle,
        "hit": "" if obstacle is None else int(max(degs) >= obstacle - HIT_MARGIN),
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
    obstacle = None
    print(f"연결됨: {PORT}  /  다음 시행 번호: {trial}")
    print("q: 시작/끝   z: 영점   s: 자석 상태   x: 종료   "
          "a 60: 장애물 60°(평가용)   a: 장애물 없음  (입력 후 Enter)")
    print("지금은 장애물 없음 (학습용)")

    try:
        while True:
            cmd = input().strip().lower()
            if cmd.startswith("a"):
                arg = cmd[1:].strip()
                if not arg:
                    obstacle = None
                    print("장애물 없음 (학습용 데이터)")
                    continue
                try:
                    obstacle = float(arg)
                    print(f"장애물 각도 = {obstacle}° (평가용 데이터)")
                except ValueError:
                    print("예: a 60  /  장애물 없음은 a")
            elif cmd == "q":
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
                    row = save_trial(trial, data, obstacle)
                    msg = f"[시행 {trial}] 저장  최대 {row['max_deg']}°"
                    if obstacle is not None:
                        msg += (f"  장애물 {obstacle}° -> "
                                f"{'닿음' if row['hit'] else '안 닿음'}")
                    print(f"{msg}  ({row['duration_ms']} ms, "
                          f"{row['n_samples']}개)")
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
```
