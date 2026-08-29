#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ==========================================
// 1. إعدادات الشبكة (غيّرها لبيانات الراوتر بتاعك)
// ==========================================
const char* ssid = "S24 Ultra saif";
const char* password = "12345678s";

// ==========================================
// 2. إعدادات سيرفر MQTT
// ==========================================
const char* mqtt_server = "broker.emqx.io";
const int mqtt_port = 1883;
const char* mqtt_client_id = "ESP32_Unified_Node";

WiFiClient espClient;
PubSubClient client(espClient);

// ==========================================
// 3. إعدادات الهاردوير (طاقة + تواجد)
// ==========================================
const char* tile_id = "tile_1";          // اسم البلاطة للطاقة
const char* node_id = "corridor_node_1"; // اسم نفس المكان لقياس الزحمة

const int PIEZO_PIN = 34;       // البن المتصل بحساس الضغط (Piezo)
const int LED_PIN = 2;          // لمبة إنذار مدمجة في بوردة ESP32
const int BUZZER_PIN = 4;       // بن توصيل جرس الإنذار (لو وجد)

// متغيرات لحفظ القراءات
unsigned long lastSendTime = 0;
int step_count = 0;
float accumulated_power_mw = 0;
float accumulated_energy_wh = 0;

// ==========================================
// دوال الاتصال بالواي فاي و MQTT
// ==========================================
void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected successfully!");
}

void callback(char* topic, byte* payload, unsigned int length) {
  // الدالة دي بتشتغل أول ما ييجي إنذار من الذكاء الاصطناعي
  Serial.print("🚨 ALERT RECEIVED on topic [");
  Serial.print(topic);
  Serial.println("]");
  
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println("Message: " + message);

  // تشغيل الإنذار لو الرسالة جات على alerts/system
  if (String(topic) == "alerts/system") {
    digitalWrite(LED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, HIGH);
    delay(3000);
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
  }
  
  // تشغيل اللمبة الذكية مع خطوات الرجل
  if (String(topic) == "actuators/relay/corridor_light/cmd") {
    if (message == "ON") {
      digitalWrite(LED_PIN, HIGH);
      digitalWrite(BUZZER_PIN, HIGH); // هنعتبر البن 4 هو اللمبة الإضافية
    } else {
      digitalWrite(LED_PIN, LOW);
      digitalWrite(BUZZER_PIN, LOW);
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(mqtt_client_id)) {
      Serial.println("connected");
      // الاشتراك في الإنذارات وأوامر اللمبة
      client.subscribe("alerts/system"); 
      client.subscribe("actuators/relay/corridor_light/cmd"); 
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

// ==========================================
// الدالة الرئيسية (Setup)
// ==========================================
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(PIEZO_PIN, INPUT);

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

// ==========================================
// دالة إرسال البيانات للسيرفر
// ==========================================
void sendTelemetry() {
  // --- 1. إرسال بيانات الطاقة ---
  StaticJsonDocument<256> docEnergy;
  docEnergy["tile_id"] = tile_id;
  docEnergy["steps"] = step_count;
  docEnergy["power_mw"] = accumulated_power_mw;
  docEnergy["energy_wh_delta"] = accumulated_energy_wh;
  docEnergy["ts"] = "ESP32_Time"; 

  char jsonBufferEnergy[256];
  serializeJson(docEnergy, jsonBufferEnergy);
  String topicEnergy = String("energy/tiles/") + tile_id + "/telemetry";
  client.publish(topicEnergy.c_str(), jsonBufferEnergy);
  Serial.println("⚡ Energy Sent: " + String(jsonBufferEnergy));

  // --- 2. قياس وإرسال إشارة الواي فاي (RSSI) للزحمة ---
  long rssi = WiFi.RSSI();
  StaticJsonDocument<256> docRssi;
  docRssi["node_id"] = node_id;
  docRssi["rssi"] = rssi;
  docRssi["ts"] = "ESP32_Time";

  char jsonBufferRssi[256];
  serializeJson(docRssi, jsonBufferRssi);
  String topicRssi = String("occupancy/rssi/") + node_id + "/telemetry";
  client.publish(topicRssi.c_str(), jsonBufferRssi);
  Serial.println("📡 RSSI Sent: " + String(jsonBufferRssi));
  Serial.println("-----------------------------------------");

  // تصفير عدادات الطاقة للدورة الجاية
  step_count = 0;
  accumulated_power_mw = 0;
  accumulated_energy_wh = 0;
}

// ==========================================
// حلقة التكرار المستمرة (Loop)
// ==========================================
void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // ==========================================
  // المهمة الأولى: قراءة حساس الضغط (الطاقة)
  // ==========================================
  int sensorValue = analogRead(PIEZO_PIN);
  if (sensorValue > 1000) { // الرقم ده بيتغير حسب الحساس بتاعك
    step_count++;
    
    // حساب طاقة وهمي - لازم تغيره بالمعادلة الفعلية للهاردوير بتاعك
    accumulated_power_mw += 15.5; 
    accumulated_energy_wh += 0.0001;
    
    Serial.println("👣 Step Detected!");
    
    // إرسال البيانات فوراً للداشبورد بدون انتظار
    sendTelemetry();
    lastSendTime = millis(); // تصفير العداد الزمني عشان ميبعتش تاني إلا بعد 5 ثواني أو ضغطة جديدة
    
    delay(300); // تأخير بسيط لمنع قراءة نفس الدوسة مرتين
  }

  // ==========================================
  // المهمة الثانية: إرسال كل البيانات (طاقة + إشارة) كل 5 ثواني لو مفيش حد داس
  // ==========================================
  unsigned long now = millis();
  if (now - lastSendTime > 5000) {
    sendTelemetry();
    lastSendTime = now;
  }
}
