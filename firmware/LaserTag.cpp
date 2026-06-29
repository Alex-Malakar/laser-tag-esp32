#include <WiFi.h>
#include <WiFiClient.h>
#include <IRremote.h>

// ============================================
// CONFIGURATION - CHANGE THESE FOR EACH PLAYER
// ============================================
const int PLAYER_ID = 1;              // Change to 2, 3, 4 for other players
const char* WIFI_SSID = "YourSSID";   // Your WiFi name
const char* WIFI_PASSWORD = "YourPassword"; // Your WiFi password
const char* SERVER_IP = "192.168.1.100";    // PC IP running Python server
const int SERVER_PORT = 5000;

// ============================================
// PIN CONFIGURATION
// ============================================
const int IR_SEND_PIN = 4;      // IR LED for shooting
const int IR_RECV_PIN = 15;     // IR receiver for getting hit
const int SHOOT_BUTTON = 18;    // Button to shoot
const int LED_PIN = 2;          // Status LED (built-in)
const int BUZZER_PIN = 5;       // Buzzer for feedback (optional)

// ============================================
// GAME STATE VARIABLES
// ============================================
int health = 100;
int ammo = 30;
bool active = true;
int score = 0;
unsigned long lastShootTime = 0;
const int SHOOT_COOLDOWN = 500; // 500ms between shots

// ============================================
// NETWORK & IR OBJECTS
// ============================================
WiFiClient client;
IRsend irsend(IR_SEND_PIN);
IRrecv irrecv(IR_RECV_PIN);
decode_results results;

// ============================================
// SETUP - RUNS ONCE
// ============================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32 Laser Tag System ===");
  Serial.print("Player ID: ");
  Serial.println(PLAYER_ID);

  // Pin setup
  pinMode(SHOOT_BUTTON, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  // Initialize IR
  irrecv.enableIRIn();
  
  // Connect to WiFi
  connectWiFi();
  
  // Connect to server
  connectToServer();
  
  // Send initialization message
  sendInit();
  
  Serial.println("System ready!");
  blinkLED(3, 200); // 3 blinks = ready
}

// ============================================
// MAIN LOOP
// ============================================
void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  
  // Check server connection
  if (!client.connected()) {
    connectToServer();
    sendInit();
  }
  
  // Handle shoot button
  if (digitalRead(SHOOT_BUTTON) == LOW && active) {
    if (millis() - lastShootTime > SHOOT_COOLDOWN) {
      shoot();
      lastShootTime = millis();
    }
  }
  
  // Check for incoming IR hits
  if (irrecv.decode(&results)) {
    handleIRHit(results.value);
    irrecv.resume();
  }
  
  // Check for server messages
  if (client.available()) {
    String response = client.readStringUntil('\n');
    response.trim();
    Serial.print("Server: ");
    Serial.println(response);
    handleServerMessage(response);
  }
  
  // Update LED status
  updateStatusLED();
  
  delay(10);
}

// ============================================
// WIFI CONNECTION
// ============================================
void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi Connection Failed!");
  }
}

// ============================================
// SERVER CONNECTION
// ============================================
void connectToServer() {
  Serial.print("Connecting to server: ");
  Serial.print(SERVER_IP);
  Serial.print(":");
  Serial.println(SERVER_PORT);
  
  if (client.connect(SERVER_IP, SERVER_PORT)) {
    Serial.println("Connected to server!");
    beep(100);
  } else {
    Serial.println("Server connection failed!");
    delay(2000);
  }
}

// ============================================
// SEND INIT MESSAGE
// ============================================
void sendInit() {
  String msg = "{\"type\":\"INIT\",\"player_id\":\"P" + String(PLAYER_ID) + "\"}";
  client.println(msg);
  Serial.println("Sent: " + msg);
}

// ============================================
// SHOOT FUNCTION
// ============================================
void shoot() {
  if (!active) {
    Serial.println("Cannot shoot - player inactive!");
    beep(50);
    return;
  }
  
  if (ammo <= 0) {
    Serial.println("Out of ammo! Need reload.");
    beep(50);
    delay(50);
    beep(50);
    return;
  }
  
  // Send IR signal with player ID encoded
  unsigned long irCode = 0xDEAD0000 | PLAYER_ID;
  irsend.sendNEC(irCode, 32);
  
  ammo--;
  Serial.print("SHOT! Ammo remaining: ");
  Serial.println(ammo);
  
  beep(30);
  blinkLED(1, 50);
}

// ============================================
// HANDLE INCOMING IR HIT
// ============================================
void handleIRHit(unsigned long irCode) {
  // Extract shooter ID from IR code
  int shooterID = irCode & 0xFF;
  
  // Ignore own shots
  if (shooterID == PLAYER_ID) {
    return;
  }
  
  if (!active) {
    Serial.println("Hit received but player inactive");
    return;
  }
  
  Serial.print("HIT by Player ");
  Serial.println(shooterID);
  
  // Send hit notification to server
  String msg = "{\"type\":\"HIT\",\"source_id\":\"P" + String(shooterID) + 
               "\",\"target_id\":\"P" + String(PLAYER_ID) + "\"}";
  client.println(msg);
  
  // Local feedback
  beep(200);
  blinkLED(2, 100);
}

// ============================================
// HANDLE SERVER MESSAGES
// ============================================
void handleServerMessage(String msg) {
  msg.toUpperCase();
  
  if (msg.indexOf("INIT_OK") >= 0) {
    Serial.println("Initialization confirmed!");
    health = 100;
    ammo = 30;
    active = true;
  }
  
  else if (msg.indexOf("HIT_OK") >= 0) {
    Serial.println("Hit confirmed by server");
  }
  
  else if (msg.indexOf("RESPAWN") >= 0) {
    Serial.println("=== RESPAWNING ===");
    health = 100;
    ammo = 30;
    active = true;
    beep(100);
    delay(100);
    beep(100);
    delay(100);
    beep(100);
  }
  
  else if (msg.indexOf("ELIMINATED") >= 0) {
    Serial.println("=== ELIMINATED ===");
    active = false;
    health = 0;
    blinkLED(5, 200);
  }
}

// ============================================
// LED STATUS INDICATOR
// ============================================
void updateStatusLED() {
  static unsigned long lastBlink = 0;
  static bool ledState = false;
  
  if (!active) {
    // Rapid blink when dead
    if (millis() - lastBlink > 200) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState);
      lastBlink = millis();
    }
  } else if (health > 50) {
    // Solid on when healthy
    digitalWrite(LED_PIN, HIGH);
  } else if (health > 0) {
    // Slow blink when injured
    if (millis() - lastBlink > 500) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState);
      lastBlink = millis();
    }
  }
}

// ============================================
// HELPER FUNCTIONS
// ============================================
void blinkLED(int times, int duration) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(duration);
    digitalWrite(LED_PIN, LOW);
    delay(duration);
  }
}

void beep(int duration) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(duration);
  digitalWrite(BUZZER_PIN, LOW);
}   