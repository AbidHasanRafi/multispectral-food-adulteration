/*
  spectral_logger_reconstructed.ino
  =====================================================================================
  RECONSTRUCTED REFERENCE SKETCH - THIS IS NOT THE FIRMWARE THAT RECORDED THE DATASET.

  The original Arduino firmware is not part of this project. This sketch was written from
  the serial protocol that ../../logger/multispectcode.py expects, so the rig can be run and
  the logger tested. It was only compile-checked (Arduino Uno, arduino:avr 1.8.6), never run
  on the hardware. Sensor gain / integration time and the exact pin wiring of the original
  rig are UNKNOWN; the values below are placeholders to be tuned (see NOTES).

  Serial protocol (115200 baud, one line per measurement, ~2 s per line):
      DATA,<31 comma-separated numbers>
  Value order (must match CSV_HEADERS in multispectcode.py):
      0-17   AS7265x   410 435 460 485 510 535 560 585 610 645 680 705 730 760 810 860 900 940 nm
      18-27  AS7341    415 445 480 515 555 590 630 680 nm, Clear, NIR   (raw 16-bit counts)
      28-30  LDR 1-3   Arduino ADC 0-1023
  Any other line (e.g. a start-up message) is printed by the logger as "[Arduino] ...".

  Wiring assumed (VERIFY against the real rig):
      AS7265x and AS7341 : SDA -> A4, SCL -> A5, VCC -> 3.3 V, GND -> GND  (I2C 0x49 and 0x39)
      LDR modules        : DO -> A0, A1, A2 (see NOTES), VCC -> 5 V, GND -> GND

  Libraries: "SparkFun Spectral Triad AS7265X" and "Adafruit AS7341" (+ Adafruit BusIO).
  Compile-checked with SparkFun Spectral Triad AS7265X 1.0.5, Adafruit AS7341 1.4.1,
  Adafruit BusIO 1.17.4 (36 % flash, 22 % RAM on an Uno).

  NOTES
   * The dataset shows the AS7341 Clear channel always at 65535 and NIR mostly at 65535
     (saturated). Lower AS7341_GAIN / AS7341_ASTEP / AS7341_ATIME before collecting new data.
   * The dataset's AS7265x values are whole numbers although the logger calls them
     "calibrated float"; this sketch sends calibrated floats with 4 decimals.
   * The 3-pin LM393 light modules on the rig expose only a digital output (DO). Reading DO
     with analogRead() gives a comparator level, not a light level. For real light readings
     use a bare LDR in a voltage divider (or a module with an analog AO pin).
  =====================================================================================
*/
#include <Wire.h>
#include <SparkFun_AS7265X.h>
#include <Adafruit_AS7341.h>

// ---------------------------------------------------------------- settings (placeholders)
const unsigned long BAUD_RATE = 115200;                 // must equal BAUD_RATE in multispectcode.py
const uint8_t LDR_PINS[3] = {A0, A1, A2};
const uint8_t TRIAD_GAIN = AS7265X_GAIN_16X;            // 1X, 4X, 16X, 64X
const uint8_t TRIAD_CYCLES = 49;                        // integration time ~ cycles * 2.8 ms
const as7341_gain_t AS7341_GAIN_SETTING = AS7341_GAIN_4X;
const uint8_t AS7341_ATIME_SETTING = 29;
const uint16_t AS7341_ASTEP_SETTING = 599;              // integration ~ (ATIME+1)*(ASTEP+1)*2.78 us

AS7265X triad;
Adafruit_AS7341 as7341;
bool triadOk = false;
bool as7341Ok = false;

void setup() {
  Serial.begin(BAUD_RATE);
  Wire.begin();

  triadOk = triad.begin();
  if (triadOk) {
    triad.setGain(TRIAD_GAIN);
    triad.setIntegrationCycles(TRIAD_CYCLES);
  } else {
    Serial.println(F("AS7265X not found - check wiring"));
  }

  as7341Ok = as7341.begin();
  if (as7341Ok) {
    as7341.setATIME(AS7341_ATIME_SETTING);
    as7341.setASTEP(AS7341_ASTEP_SETTING);
    as7341.setGain(AS7341_GAIN_SETTING);
  } else {
    Serial.println(F("AS7341 not found - check wiring"));
  }
}

// 18 calibrated AS7265x channels in wavelength order (A,B,C,D,E,F,G,H,R,I,S,J,T,U,V,W,K,L)
void readTriad(float *v) {
  if (!triadOk) {
    for (uint8_t i = 0; i < 18; i++) v[i] = 0;
    return;
  }
  triad.takeMeasurements();                             // blocks until all three chips are done
  v[0]  = triad.getCalibratedA();   // 410
  v[1]  = triad.getCalibratedB();   // 435
  v[2]  = triad.getCalibratedC();   // 460
  v[3]  = triad.getCalibratedD();   // 485
  v[4]  = triad.getCalibratedE();   // 510
  v[5]  = triad.getCalibratedF();   // 535
  v[6]  = triad.getCalibratedG();   // 560
  v[7]  = triad.getCalibratedH();   // 585
  v[8]  = triad.getCalibratedR();   // 610
  v[9]  = triad.getCalibratedI();   // 645
  v[10] = triad.getCalibratedS();   // 680
  v[11] = triad.getCalibratedJ();   // 705
  v[12] = triad.getCalibratedT();   // 730
  v[13] = triad.getCalibratedU();   // 760
  v[14] = triad.getCalibratedV();   // 810
  v[15] = triad.getCalibratedW();   // 860
  v[16] = triad.getCalibratedK();   // 900
  v[17] = triad.getCalibratedL();   // 940
}

// F1..F8, Clear, NIR. readAllChannels() returns 12 values:
// [F1 F2 F3 F4 Clear NIR | F5 F6 F7 F8 Clear NIR]
void readAs7341(uint16_t *v) {
  uint16_t raw[12];
  if (!as7341Ok || !as7341.readAllChannels(raw)) {
    for (uint8_t i = 0; i < 10; i++) v[i] = 0;
    return;
  }
  v[0] = raw[0];  v[1] = raw[1];  v[2] = raw[2];  v[3] = raw[3];     // 415 445 480 515
  v[4] = raw[6];  v[5] = raw[7];  v[6] = raw[8];  v[7] = raw[9];     // 555 590 630 680
  v[8] = raw[4];                                                      // Clear
  v[9] = raw[5];                                                      // NIR
}

void loop() {
  float triadVals[18];
  uint16_t as7341Vals[10];
  readTriad(triadVals);
  readAs7341(as7341Vals);

  Serial.print(F("DATA"));
  for (uint8_t i = 0; i < 18; i++) { Serial.print(','); Serial.print(triadVals[i], 4); }
  for (uint8_t i = 0; i < 10; i++) { Serial.print(','); Serial.print(as7341Vals[i]); }
  for (uint8_t i = 0; i < 3;  i++) { Serial.print(','); Serial.print(analogRead(LDR_PINS[i])); }
  Serial.println();
}
