#include <Servo.h>

#define TRIG_PIN 9
#define ECHO_PIN 8
#define SERVO_PIN 6

Servo myServo;
unsigned long lastTriggerTime = 0;
const int triggerDelay = 3000;
bool isLocked = true;  // Track door state

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  myServo.attach(SERVO_PIN);
  myServo.write(90); // STOP for continuous servo
  isLocked = true;   // Start in locked position
  Serial.println("Arduino ready! Door locked.");
}

long getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 25000);
  long distance = duration * 0.034 / 2;
  return distance;
}

void loop() {
  long distance = getDistance();

  if (distance > 0 && distance < 50 && millis() - lastTriggerTime > triggerDelay) {
    Serial.println("MOTION");
    lastTriggerTime = millis();
  }

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    
    if (cmd == "SERVO_ON") {
      // Only unlock if currently locked
      if (isLocked) {
        myServo.write(180);  // full speed clockwise
        delay(200);          // rotate for 0.2 seconds = ~90 degrees
        myServo.write(90);   // STOP
        delay(100);          // wait before changing state
        isLocked = false;    // Mark as unlocked
        Serial.println("Door unlocked");
      } else {
        Serial.println("Door already unlocked - skipping");
      }
      // Clear serial buffer completely
      delay(50);
      while(Serial.available() > 0) {
        Serial.read();
      }
    }
    else if (cmd == "SERVO_LOCK") {
      // Only lock if currently unlocked
      if (!isLocked) {
        myServo.write(0);    // full speed counter-clockwise
        delay(200);          // rotate for 0.2 seconds = ~90 degrees
        myServo.write(90);   // STOP
        delay(100);          // wait before changing state
        isLocked = true;     // Mark as locked
        Serial.println("Door locked");
      } else {
        Serial.println("Door already locked - skipping");
      }
      // Clear serial buffer completely
      delay(50);
      while(Serial.available() > 0) {
        Serial.read();
      }
    }
  }

  delay(100);
}