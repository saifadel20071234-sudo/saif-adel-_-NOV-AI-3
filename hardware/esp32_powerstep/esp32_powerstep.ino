#include <WiFi.h>
#include <HTTPClient.h>

// ---------------------------------------------------------
// إعدادات الشبكة (WiFi Credentials)
// ---------------------------------------------------------
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// ---------------------------------------------------------
// إعدادات السيرفر (FastAPI Backend)
// ---------------------------------------------------------
// ضع هنا الـ IP الخاص باللابتوب الذي يعمل عليه السيرفر
// تأكد أن اللابتوب والـ ESP32 على نفس شبكة الواي فاي
const char* serverName = "http://192.168.1.xxx:8000/api/ingest"; 

// ---------------------------------------------------------
// إعدادات البلاطة
// ---------------------------------------------------------
const int TILE_ID = 1; // رقم البلاطة (من 1 إلى 12)

// منافذ الحساسات (Analog Pins)
const int VOLTAGE_PIN = 34;
const int CURRENT_PIN = 35;

// Calibration variables (تعدل بناءً على المعايرة الحقيقية للحساسات)
float voltage_multiplier = 0.0033; // للتحويل من قيمة تناظرية (0-4095) إلى فولت
float current_multiplier = 0.05;   // للتحويل من قيمة تناظرية إلى تيار (mA)

void setup() {
  Serial.begin(115200);
  
  // إعداد دبابيس القراءة
  pinMode(VOLTAGE_PIN, INPUT);
  pinMode(CURRENT_PIN, INPUT);

  // الاتصال بالواي فاي
  WiFi.begin(ssid, password);
  Serial.println("Connecting to WiFi...");
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\nWiFi Connected!");
  Serial.print("ESP32 IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    // قراءة الحساسات
    int raw_v = analogRead(VOLTAGE_PIN);
    int raw_c = analogRead(CURRENT_PIN);

    // تحويل القراءات إلى أرقام فعلية
    float voltage = raw_v * voltage_multiplier;
    float current_ma = raw_c * current_multiplier;
    float rssi = WiFi.RSSI();

    // في حال عدم وجود ضغط (لا يوجد تيار)، قد يكون الفولت متولد من المكثف
    // نضع شرط بسيط لفلترة الضجيج
    if(current_ma < 2.0) {
      current_ma = 0.0;
    }

    // تجهيز حزمة البيانات (JSON Payload)
    // مثال: {"tile_id": 1, "voltage": 4.5, "current_ma": 150.0, "rssi": -65}
    String jsonPayload = "{";
    jsonPayload += "\"tile_id\":" + String(TILE_ID) + ",";
    jsonPayload += "\"voltage\":" + String(voltage, 2) + ",";
    jsonPayload += "\"current_ma\":" + String(current_ma, 2) + ",";
    jsonPayload += "\"rssi\":" + String(rssi);
    jsonPayload += "}";

    // إرسال البيانات للسيرفر
    int httpResponseCode = http.POST(jsonPayload);
    
    if (httpResponseCode > 0) {
      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);
      String response = http.getString();
      Serial.println(response);
    } else {
      Serial.print("Error code: ");
      Serial.println(httpResponseCode);
    }
    
    http.end();
  } else {
    Serial.println("WiFi Disconnected. Reconnecting...");
    WiFi.reconnect();
  }
  
  // إرسال البيانات كل ثانية (1000 ملي ثانية)
  // لتخفيف الضغط، يمكن جعلها 500 ملي ثانية (نصف ثانية) حسب الحاجة
  delay(1000); 
}
