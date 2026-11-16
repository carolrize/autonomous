#include <Wire.h>

// ---- 핀 / 설정 ----
const int PIN_SDA = 21;
const int PIN_SCL = 22;
const uint32_t SAMPLE_US = 5000;   // 5 ms = 200 Hz

// ---- AS5600 레지스터 ----
const uint8_t AS5600_ADDR   = 0x36;
const uint8_t REG_STATUS    = 0x0B;  // bit5 MD(자석 감지), bit4 ML(약함), bit3 MH(강함)
const uint8_t REG_RAW_ANGLE = 0x0C;  // 12비트, 0~4095
const uint8_t REG_AGC       = 0x1A;  // 자동 이득
const uint8_t REG_MAGNITUDE = 0x1B;  // 자기장 세기

// ---- 상태 ----
uint16_t prevRaw = 0;
int32_t  turnCount = 0;
int32_t  zeroOffset = 0;
uint32_t lastSampleUs = 0;
uint32_t prevSampleUs = 0;
int32_t  prevTotal = 0;
bool     running = true;

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
  Serial.printf("# STATUS=0x%02X  MD=%d ML=%d MH=%d\n",
                st, (st >> 5) & 1, (st >> 4) & 1, (st >> 3) & 1);
  if (!(st & 0x20))      Serial.println("# 자석이 감지되지 않음");
  else if (st & 0x10)    Serial.println("# 자석이 너무 약함(멀다)");
  else if (st & 0x08)    Serial.println("# 자석이 너무 강함(가깝다)");
  else                   Serial.println("# 자석 위치 정상");
}

int32_t totalCounts() {
  return turnCount * 4096 + (int32_t)prevRaw - zeroOffset;
}

void handleSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'z') {
      turnCount = 0;
      zeroOffset = prevRaw;
      prevTotal = 0;
      Serial.println("# zero set");
    } else if (c == 'p') {
      running = !running;
      Serial.println(running ? "# resume" : "# pause");
    } else if (c == 's') {
      printMagnetStatus();
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);

  Wire.beginTransmission(AS5600_ADDR);
  if (Wire.endTransmission() != 0) {
    Serial.println("# AS5600(0x36) 찾지 못함");
  }
  printMagnetStatus();

  readRawAngle(prevRaw);
  zeroOffset = prevRaw;
  prevSampleUs = micros();
  lastSampleUs = prevSampleUs;

  Serial.println("t_ms,raw,angle_deg,total_deg,vel_dps,agc,mag,status");
}

void loop() {
  handleSerial();
  if (!running) return;

  uint32_t now = micros();
  if (now - lastSampleUs < SAMPLE_US) return;
  lastSampleUs += SAMPLE_US;

  uint16_t raw;
  if (!readRawAngle(raw)) {
    Serial.println("# read error");
    return;
  }

  // 4095 -> 0 경계를 넘을 때 바퀴 수 보정
  int16_t d = (int16_t)raw - (int16_t)prevRaw;
  if (d >  2048) turnCount--;
  if (d < -2048) turnCount++;
  prevRaw = raw;

  int32_t total = totalCounts();
  float dt = (now - prevSampleUs) * 1e-6f;
  float vel = (total - prevTotal) * (360.0f / 4096.0f) / dt;  // deg/s
  prevTotal = total;
  prevSampleUs = now;

  uint8_t agc = 0, st = 0, m[2] = {0, 0};
  readRegs(REG_AGC, &agc, 1);
  readRegs(REG_MAGNITUDE, m, 2);
  readRegs(REG_STATUS, &st, 1);
  uint16_t mag = ((uint16_t)(m[0] & 0x0F) << 8) | m[1];

  Serial.printf("%lu,%u,%.2f,%.2f,%.1f,%u,%u,%u\n",
                (unsigned long)(now / 1000), raw,
                raw * 360.0f / 4096.0f,
                total * 360.0f / 4096.0f,
                vel, agc, mag, st);
}
