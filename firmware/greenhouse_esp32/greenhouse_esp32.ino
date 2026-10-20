/* Greenhouse IoT Lab V2: read-only monitoring firmware for classic ESP32 DevKit.
 * No pump/relay control. Configure secrets.h; calibrate soil references in the Python application.
 * Libraries: DHT sensor library (Adafruit), Adafruit Unified Sensor, BH1750 (claws).
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>
#include <esp_system.h>
#include "secrets.h"

constexpr int DHT_PIN = 4;
constexpr int SOIL_PIN = 34; // Classic ESP32 ADC1; verify pins for your own board.
constexpr int SDA_PIN = 21;
constexpr int SCL_PIN = 22;
constexpr int ADC_SAMPLES = 10;
constexpr unsigned long SAMPLE_MS = 60000;
constexpr unsigned long RETRY_MS = 5000;
constexpr int QUEUE_SIZE = 32;
DHT dht(DHT_PIN, DHT22);
BH1750 lightMeter;
bool lightReady = false;
struct Sample {
  float temperature, humidity, soilRaw, soilMv;
  uint16_t lightRaw;
  unsigned long sampledMillis;
  unsigned long sequence;
};
Sample samples[QUEUE_SIZE];
int head = 0, queued = 0;
unsigned long sequenceId = 0, lastSample = 0, lastSend = 0;
String bootId;

void enqueueSample() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  // H-resolution mode, MTreg=69. Read the actual 16-bit count for audit/saturation.
  bool lightOK = lightReady && Wire.requestFrom((uint8_t)0x23, (uint8_t)2) == 2;
  uint16_t lightRaw = 0;
  if (lightOK) {
    uint8_t highByte = Wire.read();
    uint8_t lowByte = Wire.read();
    lightRaw = ((uint16_t)highByte << 8) | lowByte;
  }
  float sumRaw = 0, sumMv = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sumRaw += analogRead(SOIL_PIN);
    // Separate conversion using the ESP32 voltage calibration (not an ideal ADC formula).
    sumMv += analogReadMilliVolts(SOIL_PIN);
    delay(10);
  }
  float raw = sumRaw / ADC_SAMPLES, mv = sumMv / ADC_SAMPLES;
  Serial.printf("Soil ADC avg(10): %.1f | measured mV avg(10): %.1f\n", raw, mv);
  if (isnan(t) || isnan(h) || t < -40 || t > 80 || h < 0 || h > 100 || !lightOK) {
    Serial.println("Sensor error: no complete sample sent. Check DHT22 and BH1750.");
    return;
  }
  if (lightRaw == 65535) Serial.println("BH1750 saturated: flagged by Python.");
  if (queued == QUEUE_SIZE) {
    head = (head + 1) % QUEUE_SIZE; queued--;
    Serial.println("RAM queue full: oldest sample discarded.");
  }
  int index = (head + queued) % QUEUE_SIZE;
  samples[index] = {t, h, raw, mv, lightRaw, millis(), ++sequenceId};
  queued++;
}

void flushOne() {
  if (!queued || WiFi.status() != WL_CONNECTED) return;
  Sample &s = samples[head];
  unsigned long age = (millis() - s.sampledMillis) / 1000;
  if (age > 86400) {
    head = (head + 1) % QUEUE_SIZE; queued--;
    Serial.println("Expired sample discarded (older than one day)."); return;
  }
  String id = bootId + ":" + String(s.sequence);
  String payload = "{\"schema_version\":2,\"device_id\":\"greenhouse-01\",\"sample_id\":\"" + id +
    "\",\"temperature\":" + String(s.temperature, 2) +
    ",\"humidity\":" + String(s.humidity, 2) +
    ",\"soil_raw\":" + String(s.soilRaw, 2) +
    ",\"soil_mv\":" + String(s.soilMv, 2) +
    ",\"adc_samples\":10,\"light_raw\":" + String(s.lightRaw) +
    ",\"sample_age_seconds\":" + String(age) + "}";
  WiFiClient client;
  HTTPClient http;
  http.setTimeout(2500);
  if (!http.begin(client, SERVER_URL)) return;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + API_TOKEN);
  int code = http.POST(payload);
  Serial.printf("POST result: %d | queued: %d\n", code, queued);
  http.end();
  if (code >= 200 && code < 300) {
    head = (head + 1) % QUEUE_SIZE; queued--;
  } else if (code == 400 || code == 413 || code == 415) {
    head = (head + 1) % QUEUE_SIZE; queued--;
    Serial.println("Invalid sample rejected; inspect sensor readings and firmware.");
  }
  // 401 or temporary network/storage failures: retain sample for retry.
}

void setup() {
  Serial.begin(115200);
  bootId = String(esp_random(), HEX) + String(esp_random(), HEX);
  analogReadResolution(12);
  analogSetPinAttenuation(SOIL_PIN, ADC_ATTEN_DB_11);
  dht.begin();
  Wire.begin(SDA_PIN, SCL_PIN);
  lightReady = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
  if (lightReady) lightReady = lightMeter.setMTreg(69);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  delay(2200); // DHT22 and light sensor stabilization.
  enqueueSample();
  lastSample = millis();
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now; enqueueSample();
  }
  if (now - lastSend >= RETRY_MS) {
    lastSend = now;
    if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
    flushOne();
  }
  delay(10);
}
