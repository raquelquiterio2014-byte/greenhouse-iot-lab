/* Greenhouse IoT Lab V3 - classic ESP32 DevKit, MONITORING ONLY.
 * Libraries: DHT sensor library (Adafruit), Adafruit Unified Sensor,
 * BH1750 (claws), ArduinoJson 7. No physical relay/pump commands.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include <math.h>
#include "secrets.h"

constexpr int DHT_PIN=4, SOIL_PIN=34, SDA_PIN=21, SCL_PIN=22;
constexpr int ADC_SAMPLES=10, QUEUE_SIZE=32;
constexpr unsigned long SAMPLE_MS=60000, HEARTBEAT_MS=30000;
DHT dht(DHT_PIN,DHT22);
BH1750 lightMeter;
bool lightReady=false, sensorOK=false;
struct Sample {
  float temperature,humidity,soilRaw,soilMv;
  uint16_t lightRaw;
  unsigned long sampledMillis,sequence;
};
Sample samples[QUEUE_SIZE];
int head=0,queued=0;
unsigned long sequenceId=0,droppedSamples=0,lastSample=0,lastSend=0,lastHeartbeat=0,lastWifi=0;
unsigned long retryDelay=1000,wifiDelay=1000;
String bootId;

void fillTransport(JsonObject obj,unsigned long seq) {
  obj["boot_id"]=bootId;obj["sequence"]=seq;
  obj["queue_depth"]=queued;obj["dropped_samples"]=droppedSamples;
  obj["uptime_ms"]=millis();obj["firmware_version"]="3.0.0";
}

void enqueueSample() {
  float t=dht.readTemperature(),h=dht.readHumidity();
  if (!lightReady) {
    lightReady=lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
    if(lightReady)lightReady=lightMeter.setMTreg(69);
    if(lightReady)delay(180);
  }
  bool lightOK=lightReady&&Wire.requestFrom((uint8_t)0x23,(uint8_t)2)==2;
  uint16_t lightRaw=0;
  if(lightOK){uint8_t hi=Wire.read();uint8_t lo=Wire.read();lightRaw=((uint16_t)hi<<8)|lo;}
  else lightReady=false;
  float raw=0,mv=0;
  for(int i=0;i<ADC_SAMPLES;i++) {
    raw+=analogRead(SOIL_PIN);mv+=analogReadMilliVolts(SOIL_PIN);delay(10);
  }
  raw/=ADC_SAMPLES;mv/=ADC_SAMPLES;
  sensorOK=isfinite(t)&&isfinite(h)&&t>=-40&&t<=80&&h>=0&&h<=100&&lightOK;
  Serial.printf("ADC avg10: %.1f | mV avg10: %.1f | sensors: %s\n",raw,mv,sensorOK?"ok":"FAULT");
  if(!sensorOK)return; // Heartbeat reports fault; no fabricated replacement readings.
  if(queued==QUEUE_SIZE){head=(head+1)%QUEUE_SIZE;queued--;droppedSamples++;}
  samples[(head+queued)%QUEUE_SIZE]={t,h,raw,mv,lightRaw,millis(),++sequenceId};queued++;
}

int postDocument(const String &url,JsonDocument &doc,String &response) {
  WiFiClient client;HTTPClient http;
  http.setConnectTimeout(1200);http.setTimeout(1500);
  if(!http.begin(client,url))return 0;
  http.addHeader("Content-Type","application/json");
  http.addHeader("Authorization",String("Bearer ")+API_TOKEN);
  String payload;serializeJson(doc,payload);
  int code=http.POST(payload);
  if(code>0)response=http.getString();
  http.end();return code;
}

void sendHeartbeat() {
  if(WiFi.status()!=WL_CONNECTED)return;
  String url=SERVER_URL;
  if(!url.endsWith("/api/readings")){Serial.println("Invalid SERVER_URL path");return;}
  url.remove(url.length()-String("/api/readings").length());url+="/api/heartbeat";
  JsonDocument doc;doc["device_id"]="greenhouse-01";doc["status"]=sensorOK?"ok":"sensor_fault";
  fillTransport(doc["transport"].to<JsonObject>(),sequenceId);
  String reply;int code=postDocument(url,doc,reply);
  Serial.printf("Heartbeat HTTP %d | pending %d | dropped %lu\n",code,queued,droppedSamples);
}

void flushOne() {
  if(!queued||WiFi.status()!=WL_CONNECTED)return;
  Sample &s=samples[head];unsigned long age=(millis()-s.sampledMillis)/1000;
  if(age>86400){head=(head+1)%QUEUE_SIZE;queued--;droppedSamples++;return;}
  String id=bootId+":"+String(s.sequence);
  JsonDocument doc;doc["schema_version"]=2;doc["device_id"]="greenhouse-01";doc["sample_id"]=id;
  doc["temperature"]=s.temperature;doc["humidity"]=s.humidity;
  doc["soil_raw"]=s.soilRaw;doc["soil_mv"]=s.soilMv;doc["light_raw"]=s.lightRaw;
  doc["adc_samples"]=10;doc["sample_age_seconds"]=age;
  fillTransport(doc["transport"].to<JsonObject>(),s.sequence);
  String response;int code=postDocument(SERVER_URL,doc,response);
  JsonDocument ack;bool parsed=!deserializeJson(ack,response);
  bool accepted=(code==200||code==201)&&parsed&&ack["accepted"].is<bool>()&&ack["accepted"].as<bool>()&&
    ack["sample_id"].as<String>()==id&&ack["source"].as<String>()=="real";
  if(accepted){head=(head+1)%QUEUE_SIZE;queued--;retryDelay=1000;}
  else if(code==400||code==409||code==413||code==415) {
    head=(head+1)%QUEUE_SIZE;queued--;droppedSamples++;retryDelay=1000;
    Serial.println("Sample permanently rejected; inspect receiver and calibration.");
  } else {
    retryDelay=(code==401||code==403)?30000:min(30000UL,retryDelay*2);
    retryDelay+=esp_random()%250;
  }
  Serial.printf("Readings HTTP %d | ACK %s | pending %d\n",code,accepted?"yes":"no",queued);
}

void setup() {
  Serial.begin(115200);bootId=String(esp_random(),HEX)+String(esp_random(),HEX);
  analogReadResolution(12);analogSetPinAttenuation(SOIL_PIN,ADC_ATTEN_DB_11);
  dht.begin();Wire.begin(SDA_PIN,SCL_PIN);
  lightReady=lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
  if(lightReady)lightReady=lightMeter.setMTreg(69);
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  delay(2200);enqueueSample();lastSample=millis();
}

void loop() {
  unsigned long now=millis();
  if(now-lastSample>=SAMPLE_MS){lastSample=now;enqueueSample();}
  if(WiFi.status()!=WL_CONNECTED&&now-lastWifi>=wifiDelay) {
    lastWifi=now;WiFi.reconnect();wifiDelay=min(30000UL,wifiDelay*2);
  }
  if(WiFi.status()==WL_CONNECTED)wifiDelay=1000;
  if(now-lastHeartbeat>=HEARTBEAT_MS){lastHeartbeat=now;sendHeartbeat();}
  if(now-lastSend>=retryDelay){lastSend=now;flushOne();}
  delay(10);
}
