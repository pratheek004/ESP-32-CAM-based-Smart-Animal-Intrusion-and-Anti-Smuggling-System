#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ============= WiFi Configuration =============
const char* ssid = "Your WiFi";          
const char* password = "******"; 

// ============= Camera Pin Setup =============
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define LED_PIN 4  // built-in flash LED

WebServer server(80);

// ==================== CAPTURE HANDLER ====================
void handleCapture() {
  digitalWrite(LED_PIN, HIGH);
  delay(120);

  // 🔹 Drop a few frames to clear the sensor pipeline
  for (int i = 0; i < 2; i++) {
    camera_fb_t *tmp = esp_camera_fb_get();
    if (tmp) esp_camera_fb_return(tmp);
    delay(80);
  }

  // 🔹 Now grab the fresh frame
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    digitalWrite(LED_PIN, LOW);
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  // 🔹 Force no-cache headers
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
  server.sendHeader("Pragma", "no-cache");
  server.sendHeader("Expires", "0");

  // 🔹 Send image directly
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  WiFiClient client = server.client();
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
  digitalWrite(LED_PIN, LOW);
  Serial.println("📸 Fresh frame captured and sent");
}

// ==================== SETUP ====================
void setup() {
  Serial.begin(115200);
  Serial.println("\nInitializing ESP32-CAM...");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // 🔹 Force SINGLE frame buffer for real-time capture
  config.frame_size = FRAMESIZE_VGA;   // 640x480, faster refresh
  config.jpeg_quality = 12;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("❌ Camera init failed!");
    while (true);
  }
  Serial.println("✅ Camera init success!");

  // --- WiFi connection ---
  Serial.printf("Connecting to WiFi: %s\n", ssid);
  WiFi.begin(ssid, password);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi connection failed");
    while (true);
  }

  Serial.println("✅ WiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
  Serial.println("Use this URL in Flask: http://<ESP_IP>/capture");

  // --- Web server ---
  server.on("/capture", HTTP_GET, handleCapture);
  server.begin();
  Serial.println("🌐 HTTP server started");
}

// ==================== LOOP ====================
void loop() {
  server.handleClient();
}
