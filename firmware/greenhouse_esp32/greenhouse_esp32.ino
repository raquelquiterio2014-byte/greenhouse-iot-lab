/* Greenhouse IoT Lab: read-only monitoring firmware for classic ESP32 DevKit.
 * No pump/relay control. Configure secrets.h and soil calibration below.
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
// EXAMPLE raw endpoints only. Replace with YOUR dry/wet readings.
constexpr int SOIL_DRY_RAW = 3000;
constexpr int SOIL_WET_RAW = 1300;
constexpr unsigned long SAMPLE_MS = 60000;
constexpr unsigned long RETRY_MS = 5000;
constexpr int QUEUE_SIZE = 32;
DHT dht(DHT_PIN, DHT22);
BH1750 lightMeter;
bool lightReady = false;
struct Sample {
  float temperature, humidity, soil, lux;
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
  float lux = lightReady ? lightMeter.readLightLevel() : -1;
  int raw = analogRead(SOIL_PIN);
  Serial.printf("Soil raw: %d (calibrate dry/wet endpoints)\n", raw);
  if (isnan(t) || isnan(h) || t < -40 || t > 80 || h < 0 || h > 100 || lux < 0 || lux > 200000) {
    Serial.println("Sensor error: no complete sample sent. Check DHT22 and BH1750.");
    return;
  }
  float soil = 100.0f * (SOIL_DRY_RAW - raw) / (SOIL_DRY_RAW - SOIL_WET_RAW);
  soil = constrain(soil, 0.0f, 100.0f);
  if (queued == QUEUE_SIZE) {
    head = (head + 1) % QUEUE_SIZE; queued--;
    Serial.println("RAM queue full: oldest sample discarded.");
  }
  int index = (head + queued) % QUEUE_SIZE;
  samples[index] = {t, h, soil, lux, millis(), ++sequenceId};
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
  String payload = "{\"device_id\":\"greenhouse-01\",\"sample_id\":\"" + id +
    "\",\"temperature\":" + String(s.temperature, 2) +
    ",\"humidity\":" + String(s.humidity, 2) +
    ",\"soil_moisture\":" + String(s.soil, 2) +
    ",\"light_lux\":" + String(s.lux, 2) +
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
  dht.begin();
  Wire.begin(SDA_PIN, SCL_PIN);
  lightReady = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
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
