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

const char* HEADER = "t_ms,raw,angle_deg,total_deg,vel_dps,agc,mag,status";

// ---- 상태 ----
uint16_t prevRaw = 0;
int32_t  turnCount = 0;
int32_t  zeroOffset = 0;
int32_t  prevTotal = 0;
uint32_t lastSampleUs = 0;
uint32_t prevSampleUs = 0;
uint32_t trialStartUs = 0;

bool     recording = false;   // q로 토글
uint16_t trialNo = 0;
uint32_t sampleCount = 0;
uint32_t errorCount = 0;

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

// 샘플 한 줄 출력 (시행 시작 기준 시간, 시작 위치 기준 누적 각도)
void printSample(uint32_t now, uint16_t raw, int32_t total, float vel) {
  uint8_t agc = 0, st = 0, m[2] = {0, 0};
  readRegs(REG_AGC, &agc, 1);
  readRegs(REG_MAGNITUDE, m, 2);
  readRegs(REG_STATUS, &st, 1);
  uint16_t mag = ((uint16_t)(m[0] & 0x0F) << 8) | m[1];

  Serial.printf("%.3f,%u,%.2f,%.2f,%.1f,%u,%u,%u\n",
                (now - trialStartUs) / 1000.0f, raw,
                raw * 360.0f / 4096.0f,
                total * 360.0f / 4096.0f,
                vel, agc, mag, st);
  sampleCount++;
}

void startTrial() {
  uint16_t raw;
  if (!readRawAngle(raw)) {
    Serial.println("# 시작 실패: 센서 읽기 오류");
    return;
  }
  // 시행마다 각도 0, 시간 0에서 시작
  prevRaw = raw;
  turnCount = 0;
  zeroOffset = raw;
  prevTotal = 0;
  sampleCount = 0;
  errorCount = 0;
  trialNo++;

  trialStartUs = micros();
  prevSampleUs = trialStartUs;
  lastSampleUs = trialStartUs;   // 대기 중 밀린 샘플을 몰아 찍지 않도록
  recording = true;

  Serial.printf("# START %u\n", trialNo);
  Serial.println(HEADER);
  printSample(trialStartUs, raw, 0, 0.0f);   // t=0 기준점
}

void stopTrial() {
  recording = false;
  float dur = (micros() - trialStartUs) * 1e-6f;
  Serial.printf("# END %u samples=%lu errors=%lu dur_s=%.3f total_deg=%.2f\n",
                trialNo, (unsigned long)sampleCount, (unsigned long)errorCount,
                dur, prevTotal * 360.0f / 4096.0f);
}

void handleSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'q') {
      if (recording) stopTrial();
      else           startTrial();
    } else if (c == 's') {
      printMagnetStatus();
    }
    // '\r', '\n' 등은 무시 (시리얼 모니터에서 Enter 쳐도 됨)
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
  Serial.println("# READY  q: 시행 시작/종료, s: 자석 상태");
}

void loop() {
  handleSerial();
  if (!recording) return;           // 시행 중이 아니면 출력 없음

  uint32_t now = micros();
  if (now - lastSampleUs < SAMPLE_US) return;
  lastSampleUs += SAMPLE_US;

  uint16_t raw;
  if (!readRawAngle(raw)) {
    errorCount++;
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

  printSample(now, raw, total, vel);
}
