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
