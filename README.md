# ESP32-CAM Based Smart Animal Intrusion & Anti-Smuggling System
# 🔐 AI-Powered Farm Security | 🐄 Animal Detection | 👤 Face Recognition | 🌐 IoT Web Dashboard | 🚪 Automated Gate Control
# 📌 Overview

This project presents an AI-enabled smart security system designed for farms and livestock sheds.
It integrates ESP32-CAM, Ultrasonic sensors, Arduino-controlled servo gate locking, and a Flask-based webserver with Machine Learning detection for:

Human intruder detection

Known vs unknown face recognition

Animal classification (Cow, Dog, Cat, Rabbit)

Web-controlled gate locking/unlocking

Real-time auto-capture and manual capture options

This low-cost system provides 24×7 automated monitoring, reducing the need for manual supervision.

# ✨ Features

🐄 Animal Detection

Uses YOLOv8n to identify cows, dogs, cats, and rabbits.

👤 Human Intrusion Detection

Uses DeepFace (Facenet512) for face embedding & recognition.

Detects:

Known person

Unknown person (Intruder)

🎥 Auto + Manual Capture

Auto-captures when Arduino detects motion.

User can manually trigger capture from the website.

🚪 Smart Gate Control

Gate opens automatically for known faces.

Farmer can manually lock/unlock via web dashboard.

🌐 Real-Time Web Interface

View detection results

Live updates of last auto-captured frame

Add new known faces

# 🛠️ Technologies Used

Component	Purpose

ESP32-CAM	              Image capture

Flask	                  Backend + Web UI

DeepFace           	    Face recognition

YOLOv8	                Animal detection

Arduino UNO	            Ultrasonic sensor + Servo gate

Serial Communication	  Python ↔ Arduino

# 📸 System Workflow

Ultrasonic sensor detects movement

Arduino sends "MOTION" to Flask

Flask triggers ESP32-CAM to capture

ML detection (animal first → then face)

Result displayed on the dashboard

Known face → gate automatically unlocks

Unknown → marked as intruder
