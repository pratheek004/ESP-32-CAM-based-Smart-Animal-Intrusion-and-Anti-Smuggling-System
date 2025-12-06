from flask import Flask, render_template_string, request, jsonify
import cv2
import numpy as np
import os, json, tempfile, time, requests, base64
from deepface import DeepFace
from ultralytics import YOLO
import serial
import threading

app = Flask(__name__)

KNOWN_FACES_FILE = "known_faces.json"
ESP32_URL = "http://192.168.0.101"   # Change this to your ESP32-CAM IP
known_faces = {}

# Load YOLOv8 model for animal detection
animal_model = YOLO("yolov8n.pt")

# ============= ARDUINO SERIAL CONNECTION =============
ARDUINO_PORT = "COM10"  # Change to your Arduino port (Linux: /dev/ttyUSB0, Mac: /dev/cu.usbserial)
ARDUINO_BAUD = 115200
arduino_serial = None
auto_capture_enabled = True  # Toggle for auto-capture
latest_capture = None  # Store latest capture result for web display

# --------------------------
# Helper Functions
# --------------------------
def load_known_faces():
    """Load known face embeddings from JSON, auto-fixing old dict format."""
    global known_faces
    if not os.path.exists(KNOWN_FACES_FILE):
        known_faces = {}
        return
    with open(KNOWN_FACES_FILE, "r") as f:
        data = json.load(f)

    fixed = {}
    for name, val in data.items():
        if isinstance(val, dict) and "embedding" in val:
            fixed[name] = val["embedding"]
        else:
            fixed[name] = val
    known_faces = fixed
    save_known_faces()


def save_known_faces():
    with open(KNOWN_FACES_FILE, "w") as f:
        json.dump(known_faces, f)


def get_face_embedding(image):
    """Get normalized face embedding using DeepFace (Facenet512)."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        cv2.imwrite(tmp.name, image)
        tmp.close()
        time.sleep(0.05)

        try:
            emb = DeepFace.represent(
                img_path=tmp.name,
                model_name="Facenet512",
                detector_backend="retinaface",
                enforce_detection=True,
                align=True
            )[0]["embedding"]
        except Exception:
            print("WARNING: RetinaFace failed, retrying with OpenCV backend...")
            emb = DeepFace.represent(
                img_path=tmp.name,
                model_name="Facenet512",
                detector_backend="opencv",
                enforce_detection=False,
                align=True
            )[0]["embedding"]

        os.remove(tmp.name)
        emb = np.array(emb, dtype=np.float32)
        emb /= np.linalg.norm(emb) + 1e-6
        return emb.tolist()
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None


def match_face(embedding, known_faces, threshold=0.50):
    """Compare new embedding with stored faces; return best match."""
    embedding = np.array(embedding, dtype=np.float32)
    best_match = ("INTRUDER", 0.0)

    for name, emb_list in known_faces.items():
        emb_list = np.array(emb_list, dtype=np.float32)
        sim = np.dot(embedding, emb_list) / (
            np.linalg.norm(embedding) * np.linalg.norm(emb_list)
        )
        conf = (sim + 1) / 2 * 100
        if sim > threshold and conf > 80 and conf > best_match[1]:
            best_match = (name, conf)
    return best_match


# --------------------------
# Arduino Serial Monitoring
# --------------------------
def monitor_arduino():
    """Background thread to listen for MOTION signal from Arduino."""
    global arduino_serial
    while True:
        try:
            if arduino_serial and arduino_serial.is_open:
                if arduino_serial.in_waiting > 0:
                    line = arduino_serial.readline().decode('utf-8').strip()
                    print(f"[Arduino] {line}")
                    
                    if line == "MOTION" and auto_capture_enabled:
                        print("ALERT: Motion detected! Auto-capturing...")
                        # Trigger capture in a separate thread to avoid blocking
                        threading.Thread(target=auto_capture_and_respond, daemon=True).start()
            time.sleep(0.1)
        except Exception as e:
            print(f"❌ Arduino monitoring error: {e}")
            time.sleep(1)


def auto_capture_and_respond():
    """Perform capture, detection, and send servo command if known face."""
    try:
        result = perform_capture_detection()
        
        # Store latest result for web display
        global latest_capture
        latest_capture = result
        
        # If KNOWN FACE detected (not intruder), trigger servo
        if result and "INTRUDER" not in result.get("result", "").upper() and result.get("result"):
            # Check if it's a known person (has checkmark or percentage)
            if "%" in result.get("result", "") or "✅" in result.get("result", ""):
                print("SUCCESS: Known face detected! Opening door (servo)...")
                send_servo_command()
    except Exception as e:
        print(f"ERROR: Auto-capture error: {e}")


def send_servo_command():
    """Send SERVO_ON command to Arduino."""
    global arduino_serial
    try:
        if arduino_serial and arduino_serial.is_open:
            arduino_serial.write(b"SERVO_ON\n")
            print("UNLOCK: Servo command sent to Arduino (Door unlocked)")
    except Exception as e:
        print(f"ERROR: Failed to send servo command: {e}")


def send_servo_lock_command():
    """Send SERVO_LOCK command to Arduino to lock door."""
    global arduino_serial
    try:
        if arduino_serial and arduino_serial.is_open:
            arduino_serial.write(b"SERVO_LOCK\n")
            print("LOCK: Servo lock command sent to Arduino (Door locked)")
    except Exception as e:
        print(f"ERROR: Failed to send servo lock command: {e}")


def perform_capture_detection():
    """Core capture and detection logic (extracted from /capture endpoint)."""
    import hashlib

    def get_frame_bytes_once():
        r = requests.get(
            f"{ESP32_URL}/capture?cb={int(time.time()*1000)}",
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            timeout=10,
        )
        r.raise_for_status()
        return r.content

    try:
        last_hash = None
        frame_bytes = None
        for attempt in range(3):
            try:
                frame_bytes = get_frame_bytes_once()
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.35)
                    continue
                else:
                    raise

            h = hashlib.md5(frame_bytes).hexdigest()
            if last_hash is None or h != last_hash:
                last_hash = h
                break
            time.sleep(0.45)
            last_hash = h

        if frame_bytes is None:
            return {"error": "Failed to fetch frame from ESP32"}

        img_array = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if frame is None:
            return {"error": "Failed to decode image"}

        # Animal detection first
        resized = cv2.resize(frame, (320, 320))
        results = animal_model.predict(source=resized, conf=0.25, verbose=False)

        animals = set()
        for res in results:
            if hasattr(res, "boxes") and hasattr(res.boxes, "cls"):
                for cls_idx in res.boxes.cls:
                    try:
                        label = animal_model.names[int(cls_idx)]
                    except Exception:
                        continue
                    if label in ("dog", "cat", "cow"):
                        animals.add(label)

        if animals:
            msg = " / ".join(["🐶 Dog" if a=="dog" else "🐱 Cat" if a=="cat" else "🐮 Cow" for a in sorted(animals)]) + " detected!"
            _, buf = cv2.imencode(".jpg", frame)
            img_b64 = base64.b64encode(buf).decode("utf-8")
            return {"result": msg, "image": img_b64}

        # Face detection
        emb = get_face_embedding(frame)
        if emb is None:
            msg = "❌ No human face detected."
            _, buf = cv2.imencode(".jpg", frame)
            img_b64 = base64.b64encode(buf).decode("utf-8")
            return {"result": msg, "image": img_b64}

        name, conf = match_face(emb, known_faces)
        msg = f"🚨 Intruder Detected!" if name == "INTRUDER" else f"✅ {name} ({conf:.1f}%)"

        _, buf = cv2.imencode(".jpg", frame)
        img_b64 = base64.b64encode(buf).decode("utf-8")
        return {"result": msg, "image": img_b64}

    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)}"}


# --------------------------
# Web Interface
# --------------------------
@app.route("/")
def index():
    html = """
    <html>
    <head>
        <title>ESP32-CAM Face & Animal Detection</title>
        <style>
            body { font-family: Arial; background: #111; color: #eee; text-align: center; }
            h1 { color: #0f0; }
            input, button { margin: 8px; padding: 8px; border-radius: 6px; }
            img { border-radius: 12px; margin-top: 15px; }
            .result { margin-top: 10px; font-size: 1.2em; }
            .status { margin: 10px; padding: 10px; border-radius: 8px; background: #222; }
            .toggle { background: #28a745; color: white; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>ESP32-CAM Face & Animal Detection</h1>
        
        <div class="status">
            <strong>Auto-Capture Status:</strong> 
            <span id="autoStatus">Enabled</span>
            <button class="toggle" onclick="toggleAuto()">Toggle Auto-Capture</button>
        </div>

        <form id="addForm" enctype="multipart/form-data">
            <input type="text" name="name" placeholder="Name" required>
            <input type="file" name="image" accept="image/*" required>
            <button type="submit">Add Known Face</button>
        </form>

        <hr>
        <button onclick="capture()">📸 Manual Capture & Detect</button>
        <button onclick="unlockDoor()">🔓 Unlock Door (Servo)</button>
        <button onclick="lockDoor()" style="background:#dc3545;">🔒 Lock Door (Servo)</button>
        <button onclick="refreshLatest()">🔄 Refresh Latest Auto-Capture</button>
        <div class="result" id="result"></div>
        <img id="preview" width="320"/>

        <script>
            // Auto-refresh latest capture every 2 seconds
            setInterval(refreshLatest, 2000);

            document.getElementById('addForm').onsubmit = async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const res = await fetch('/add_face', { method: 'POST', body: formData });
                const data = await res.json();
                alert(data.message || data.error);
            };

            async function capture() {
                document.getElementById('result').innerHTML = "Capturing from ESP32...";
                const res = await fetch('/capture');
                const data = await res.json();

                if (data.error) {
                    document.getElementById('result').innerHTML = "❌ " + data.error;
                    return;
                }
                document.getElementById('preview').src = "data:image/jpeg;base64," + data.image;
                document.getElementById('result').innerHTML = data.result;
            }

            async function refreshLatest() {
                const res = await fetch('/latest_capture');
                const data = await res.json();

                if (data.result && data.image) {
                    document.getElementById('preview').src = "data:image/jpeg;base64," + data.image;
                    document.getElementById('result').innerHTML = data.result + " <small>(Auto-captured)</small>";
                }
            }

            async function toggleAuto() {
                const res = await fetch('/toggle_auto');
                const data = await res.json();
                document.getElementById('autoStatus').innerHTML = data.enabled ? 'Enabled' : 'Disabled';
                document.getElementById('autoStatus').style.color = data.enabled ? '#0f0' : '#f00';
            }

            async function unlockDoor() {
                const res = await fetch('/unlock_door');
                const data = await res.json();
                alert(data.message || data.error);
            }

            async function lockDoor() {
                const res = await fetch('/lock_door');
                const data = await res.json();
                alert(data.message || data.error);
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


# --------------------------
# API Endpoints
# --------------------------
@app.route("/add_face", methods=["POST"])
def add_face():
    name = request.form.get("name")
    file = request.files["image"]
    if not file or not name:
        return jsonify({"error": "Name and image required"}), 400

    file_bytes = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    emb = get_face_embedding(img)
    if emb is None:
        return jsonify({"error": "No face detected"}), 400

    if name in known_faces:
        old_emb = np.array(known_faces[name])
        new_emb = np.array(emb)
        avg_emb = (old_emb + new_emb) / 2
        avg_emb /= np.linalg.norm(avg_emb) + 1e-6
        known_faces[name] = avg_emb.tolist()
    else:
        known_faces[name] = emb

    save_known_faces()
    return jsonify({"status": "success", "message": f"Added/Updated {name}."})


@app.route("/capture")
def capture():
    """Manual capture endpoint (same as before)."""
    result = perform_capture_detection()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/toggle_auto")
def toggle_auto():
    """Toggle auto-capture on/off."""
    global auto_capture_enabled
    auto_capture_enabled = not auto_capture_enabled
    return jsonify({"enabled": auto_capture_enabled})


@app.route("/unlock_door")
def unlock_door():
    """Manually unlock door (open servo)."""
    send_servo_command()
    return jsonify({"message": "Door unlocked! (Servo opened)"})


@app.route("/lock_door")
def lock_door():
    """Manually lock door (close servo)."""
    send_servo_lock_command()
    return jsonify({"message": "Door locked! (Servo closed)"})


@app.route("/latest_capture")
def get_latest_capture():
    """Return the latest auto-captured image and result."""
    global latest_capture
    if latest_capture:
        return jsonify(latest_capture)
    else:
        return jsonify({"result": None, "image": None})


# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    load_known_faces()
    print("✅ Known faces loaded:", list(known_faces.keys()))
    
    # Connect to Arduino
    try:
        arduino_serial = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
        time.sleep(2)  # Wait for Arduino to initialize
        print(f"✅ Arduino connected on {ARDUINO_PORT}")
        
        # Start Arduino monitoring thread
        arduino_thread = threading.Thread(target=monitor_arduino, daemon=True)
        arduino_thread.start()
        print("✅ Arduino monitoring started")
    except Exception as e:
        print(f"⚠ Could not connect to Arduino: {e}")
        print("   Auto-capture will be disabled.")
    
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)