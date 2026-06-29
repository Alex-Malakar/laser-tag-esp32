/*
 * ESP32-S3 Feather Laser Tag System - PRODUCTION READY (TEAM MODE - FIXED)
 * * Hardware Requirements:
 * - ESP32-S3 Feather (STEMMA QT)
 * - IR LED (940nm) on GPIO 18 with 100Ω resistor
 * - IR Receiver (TSOP38238) on GPIO 16
 * - Trigger Button on GPIO 9
 * * Key Fixes:
 * 1. Removed local health deduction in checkForHits() to prevent double damage.
 * 2. Corrected HIT message payload format (Shooter is source_id, Victim is target_id) 
 * to correctly report the hit to the server.
 * 3. Player now relies entirely on the server's HIT_RECEIVED message for damage.
 */

#include <WiFi.h>
#include <WiFiClient.h>
#include <IRremote.hpp>
#include <ArduinoJson.h>

// ============ Configuration ============
const char* WIFI_SSID = "iPhone";
const char* WIFI_PASSWORD = "// input password";
const char* SERVER_IP = "###.##.##.##";
const int SERVER_PORT = 5000;

// Pin Definitions
const int IR_SEND_PIN = 18;
const int IR_RECEIVE_PIN = 16;
const int TRIGGER_PIN = 9;

// Game Configuration
const int MAX_HEALTH = 100;
const int MAX_AMMO = 10;
const int DAMAGE_PER_HIT = 10;
const int SHOT_COOLDOWN_MS = 500;
const int RESPAWN_TIME_MS = 5000;  // 5 seconds to respawn

// Connection Configuration
const int RECONNECT_INTERVAL = 5000;
const int CONNECTION_TIMEOUT = 10000;
const int RELOAD_HOLD_TIME = 3000;

// ============ Global Variables ============
// IMPORTANT: Change these values for each player device
String playerID = "P2"; 
int teamID = 2;          // Team 1 or Team 2
int health = MAX_HEALTH;
int ammo = MAX_AMMO;
int score = 0;
bool isActive = true;
bool isConnected = false;
unsigned long lastShotTime = 0;
unsigned long lastHeartbeat = 0;
unsigned long lastConnectionAttempt = 0;
unsigned long buttonPressStart = 0;
unsigned long deathTime = 0;  
bool buttonWasPressed = false;

WiFiClient client;

// ============ Function Prototypes ============
void connectToWiFi();
void reconnectWiFi();
void connectToServer();
void generatePlayerID();
void sendInitMessage();
void sendHitMessage(String sourceID, String targetID); // Fixed signature
void sendStateUpdate();
void requestReload();
void handleServerMessages();
void shootLaser();
void checkForHits();
void playerDied();
void respawnPlayer();
void resetPlayer();

// ============ Setup ============
void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\n\n=== ESP32-S3 Laser Tag - PRODUCTION (FIXED TEAM) ===");
  
  // Initialize pins
  pinMode(TRIGGER_PIN, INPUT_PULLUP);
  pinMode(IR_SEND_PIN, OUTPUT);
  pinMode(IR_RECEIVE_PIN, INPUT);
  digitalWrite(IR_SEND_PIN, LOW);
  Serial.println("Pins initialized");
  
  // Initialize IR sender
  IrSender.begin(IR_SEND_PIN, ENABLE_LED_FEEDBACK);
  Serial.println("IR Sender initialized");
  
  // Generate unique player ID from MAC (only used if playerID is default)
  generatePlayerID();
  
  // Connect to WiFi
  connectToWiFi();
  
  // Initialize IR receiver
  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK);
  Serial.println("IR Receiver initialized");
  
  // Connect to server
  connectToServer();
  
  Serial.println("Setup complete!");
  Serial.println("---");
}

// ============ Main Loop ============
void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected!");
    reconnectWiFi();
  }
  
  // Check server connection and reconnect if needed
  if (!client.connected()) {
    if (isConnected) {
      Serial.println("Server connection lost!");
      isConnected = false;
    }
    
    if (millis() - lastConnectionAttempt > RECONNECT_INTERVAL) {
      connectToServer();
      lastConnectionAttempt = millis();
    }
  }
  
  // Only process game logic if connected
  if (isConnected) {
    // Handle server messages
    handleServerMessages();
    
    // Check for auto-respawn if dead
    if (!isActive && deathTime > 0 && (millis() - deathTime >= RESPAWN_TIME_MS)) {
      respawnPlayer();
      deathTime = 0; 
    }
    
    // Check for IR hits
    checkForHits();
    
    // Handle trigger button (Shooting and Reloading)
    bool buttonPressed = (digitalRead(TRIGGER_PIN) == LOW);
    
    if (buttonPressed && !buttonWasPressed) {
      buttonPressStart = millis();
      buttonWasPressed = true;
    }
    
    if (buttonPressed && buttonWasPressed) {
      if (ammo == 0 && isActive) {
        // Check for long press to reload
        if (millis() - buttonPressStart >= RELOAD_HOLD_TIME) {
          requestReload();
          buttonWasPressed = false; 
        }
      }
    }
    
    if (!buttonPressed && buttonWasPressed) {
      unsigned long holdTime = millis() - buttonPressStart;
      
      // Handle short press as a shot
      if (holdTime < RELOAD_HOLD_TIME && isActive && ammo > 0) {
        shootLaser();
      }
      
      buttonWasPressed = false;
    }
    
    // Send heartbeat every 2 seconds
    if (millis() - lastHeartbeat > 2000) {
      sendStateUpdate();
      lastHeartbeat = millis();
    }
  }
  
  delay(10);
}

// ============ WiFi Functions ============
void connectToWiFi() {
  // ... (WiFi connection logic remains the same) ...
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi failed!");
  }
}

void reconnectWiFi() {
  Serial.println("Reconnecting WiFi...");
  WiFi.disconnect();
  delay(1000);
  connectToWiFi();
}

// ============ Server Communication ============
void connectToServer() {
  // ... (Server connection logic remains the same) ...
  Serial.print("Connecting to server: ");
  Serial.print(SERVER_IP);
  Serial.print(":");
  Serial.println(SERVER_PORT);
  
  if (client.connected()) {
    client.stop();
    delay(100);
  }
  
  unsigned long startAttempt = millis();
  bool connected = false;
  
  while (millis() - startAttempt < CONNECTION_TIMEOUT && !connected) {
    if (client.connect(SERVER_IP, SERVER_PORT)) {
      connected = true;
      break;
    }
    delay(500);
    Serial.print(".");
  }
  
  if (connected) {
    Serial.println("\nConnected to server!");
    client.setNoDelay(true);
    isConnected = true;
    delay(100);
    sendInitMessage();
  } else {
    Serial.println("\nServer connection failed!");
    isConnected = false;
    client.stop();
  }
}

void sendInitMessage() {
  StaticJsonDocument<256> doc;
  doc["type"] = "INIT";
  doc["player_id"] = playerID;
  doc["team_id"] = teamID;
  doc["timestamp"] = millis();
  
  String message;
  serializeJson(doc, message);
  
  client.print(message);
  client.print('\n');
  client.flush();
  
  Serial.print("Sent INIT: ");
  Serial.println(message);
}

/**
 * @brief Sends a HIT message to the server, reporting a hit received.
 * * @param sourceID The Player ID of the shooter (source of the hit).
 * @param targetID The Player ID of the victim (target of the hit, which is 'this' device).
 */
void sendHitMessage(String sourceID, String targetID) {
  if (!isConnected || !client.connected()) {
    return;
  }
  
  StaticJsonDocument<256> doc;
  doc["type"] = "HIT";
  // The person who shot is the SOURCE
  doc["source_id"] = sourceID; 
  // The person who was hit (me) is the TARGET
  doc["target_id"] = targetID; 
  doc["timestamp"] = millis();
  
  String message;
  serializeJson(doc, message);
  
  client.print(message);
  client.print('\n');
  client.flush();
  
  Serial.print("Sent HIT: ");
  Serial.println(message);
}

void sendStateUpdate() {
  if (!isConnected || !client.connected()) {
    return;
  }
  
  StaticJsonDocument<256> doc;
  doc["type"] = "STATE_UPDATE";
  doc["player_id"] = playerID;
  doc["health"] = health;
  doc["ammo"] = ammo;
  doc["score"] = score;
  doc["active"] = isActive;
  doc["timestamp"] = millis();
  
  String message;
  serializeJson(doc, message);
  
  client.print(message);
  client.print('\n');
  client.flush();
  
  static int updateCount = 0;
  if (updateCount % 10 == 0) {
    Serial.print("Heartbeat (");
    Serial.print(updateCount);
    Serial.println(")");
  }
  updateCount++;
}

void requestReload() {
  if (!isConnected || !client.connected()) {
    return;
  }
  
  StaticJsonDocument<256> doc;
  doc["type"] = "REQUEST_RELOAD";
  doc["player_id"] = playerID;
  doc["timestamp"] = millis();
  
  String message;
  serializeJson(doc, message);
  
  client.print(message);
  client.print('\n');
  client.flush();
  
  Serial.println("Reload requested");
}

void handleServerMessages() {
  while (client.available()) {
    String response = client.readStringUntil('\n');
    response.trim();
    
    if (response.length() == 0) {
      continue;
    }
    
    Serial.print("Server: ");
    Serial.println(response);
    
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, response);
    
    if (error) {
      Serial.print("JSON error: ");
      Serial.println(error.c_str());
      return;
    }
    
    String msgType = doc["type"] | "";
    
    if (msgType == "INIT_OK") {
      Serial.println("Init confirmed!");
      Serial.print("Players: ");
      Serial.println(doc["current_players"].as<int>());
    }
    else if (msgType == "HIT_OK") {
      Serial.println("Hit registered by server (Nice shot!)");
    }
    else if (msgType == "HIT_RECEIVED") {
      // *** FIX: DAMAGE IS APPLIED ONLY HERE, AS AUTHORIZED BY SERVER ***
      int damage = doc["damage"] | DAMAGE_PER_HIT;
      health -= damage;
      if (health < 0) health = 0;
      
      String source_id = doc["source_id"] | "Unknown";
      Serial.print("✗ Got hit by ");
      Serial.print(source_id);
      Serial.print("! New Health: ");
      Serial.println(health);
      
      if (health <= 0) {
        playerDied();
      }
    }
    else if (msgType == "RESPAWN") {
      respawnPlayer();
    }
    else if (msgType == "RELOAD") {
      ammo = MAX_AMMO;
      Serial.println("Reloaded!");
    }
    else if (msgType == "GAME_START") {
      Serial.println("Game started!");
      resetPlayer();
    }
    else if (msgType == "GAME_END") {
      Serial.println("Game ended!");
      isActive = false;
    }
    else if (msgType == "ERROR") {
      Serial.print("Error: ");
      Serial.println(doc["message"].as<String>());
    }
  }
}

// ============ IR Functions ============
void shootLaser() {
  if (!isActive || ammo <= 0) {
    Serial.println("Cannot shoot");
    return;
  }
  
  unsigned long currentTime = millis();
  if (currentTime - lastShotTime < SHOT_COOLDOWN_MS) {
    return;
  }
  
  // Encode player ID into IR signal
  uint8_t playerNum = playerID.substring(1).toInt();
  uint8_t address = (teamID << 4) | (playerNum & 0x0F);
  uint8_t command = 0x10;  // Laser tag identifier
  
  // Send NEC signal
  IrSender.sendNEC(address, command, 0);
  
  ammo--;
  lastShotTime = currentTime;
  
  Serial.print("Shot! Ammo: ");
  Serial.println(ammo);
  
  sendStateUpdate();
}

void checkForHits() {
  if (IrReceiver.decode()) {
    // Check if it's our laser tag command (0x10)
    if (IrReceiver.decodedIRData.command == 0x10) {
      // Decode address: high 4 bits = team, low 4 bits = player number
      uint8_t address = IrReceiver.decodedIRData.address;
      uint8_t shooterTeam = (address >> 4) & 0x0F;
      uint8_t shooterPlayer = address & 0x0F;
      
      // Check for friendly fire (Team vs Team logic retained)
      if (shooterTeam != teamID && isActive) {
        String shooterID = "P" + String(shooterPlayer);
        
        Serial.print("Hit detected by ");
        Serial.print(shooterID);
        Serial.print(" (Team ");
        Serial.print(shooterTeam);
        Serial.println("). Reporting to server...");
        
        // **FIX: Send the correct IDs to the server**
        // The shooterID is the SOURCE, my playerID is the TARGET
        sendHitMessage(shooterID, playerID); 
        
        // **FIX: Removed all local health/damage logic.**
        // Damage is now handled by the server's HIT_RECEIVED message.
        
      } else if (shooterTeam == teamID) {
        Serial.println("⚠ Friendly fire blocked");
      }
    }
    
    IrReceiver.resume();
  }
}

// ============ Game Logic ============
void playerDied() {
  Serial.println("☠ Eliminated! Awaiting server respawn...");
  isActive = false;
  deathTime = millis();  
}

void respawnPlayer() {
  Serial.println("♻ Respawning!");
  health = MAX_HEALTH;
  ammo = MAX_AMMO;
  isActive = true;
  sendStateUpdate(); 
}

void resetPlayer() {
  health = MAX_HEALTH;
  ammo = MAX_AMMO;
  score = 0;
  isActive = true;
  sendStateUpdate();
}

// ============ Helper Functions ============
void generatePlayerID() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  // Use % 15 + 1 to ensure the player ID fits within the 4-bit IR protocol (P1 to P15)
  uint8_t playerNum = (mac[4] + mac[5]) % 15 + 1; 
  
  // If playerID was left as the default "P2", assign the generated ID.
  if (playerID == "P2") { 
    playerID = "P" + String(playerNum);
  }
  Serial.print("Final Player ID: ");
  Serial.println(playerID);
  Serial.print("Team ID: ");
  Serial.println(teamID);
}