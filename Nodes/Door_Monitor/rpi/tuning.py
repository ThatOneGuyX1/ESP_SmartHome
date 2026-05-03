"""
tuning.py — Interactive detection tuner for the RPi camera node.

Runs a web server on port 8000. Open in your browser on any device
on the same network:
    http://<pi-ip>:8000

Shows a live annotated camera feed with real-time sliders to tune:
    - Confidence threshold
    - Minimum motion area
    - Motion pixel threshold

Install Flask if not already installed:
    pip install flask
"""

import cv2
import numpy as np
import subprocess
import os
import threading
import time
from flask import Flask, Response, request, jsonify

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROTOTXT = os.path.join(BASE_DIR, "model/deploy.prototxt")
MODEL    = os.path.join(BASE_DIR, "model/mobilenet_iter_73000.caffemodel")

WIDTH, HEIGHT = 320, 240

CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat",
           "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
           "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
           "sofa", "train", "tvmonitor"]

# ── Shared state (thread-safe) ────────────────────────────────────────────────
params = {
    "conf_threshold": 0.5,
    "min_area":       2500,
    "threshold_val":  35,
}
params_lock = threading.Lock()

status = {
    "motion":     False,
    "person":     False,
    "confidence": 0.0,
    "label":      "",
}
status_lock = threading.Lock()

latest_frame  = None
frame_lock    = threading.Lock()

# ── Detection loop ────────────────────────────────────────────────────────────
def detection_loop():
    global latest_frame

    print("[MODEL] Loading...")
    net = cv2.dnn.readNetFromCaffe(PROTOTXT, MODEL)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    print("[MODEL] Ready.")

    cmd = ['rpicam-vid', '-t', '0', '--inline', '--nopreview',
           '--width', str(WIDTH), '--height', str(HEIGHT),
           '--framerate', '5', '--codec', 'yuv420', '-o', '-']
    pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)

    avg_frame = None

    while True:
        raw = pipe.stdout.read(WIDTH * HEIGHT)
        if not raw or len(raw) != WIDTH * HEIGHT:
            continue

        frame = np.frombuffer(raw, dtype=np.uint8).reshape((HEIGHT, WIDTH)).copy()

        with params_lock:
            conf_threshold = params["conf_threshold"]
            min_area       = params["min_area"]
            threshold_val  = params["threshold_val"]

        # ── Motion detection ──────────────────────────────────────────────
        gray = cv2.GaussianBlur(frame, (21, 21), 0)
        if avg_frame is None:
            avg_frame = gray.copy().astype("float")
            continue

        cv2.accumulateWeighted(gray, avg_frame, 0.01)
        delta   = cv2.absdiff(gray, cv2.convertScaleAbs(avg_frame))
        thresh  = cv2.threshold(delta, threshold_val, 255, cv2.THRESH_BINARY)[1]
        thresh  = cv2.dilate(thresh, None, iterations=2)
        thresh  = cv2.erode(thresh, None, iterations=1)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_contours = [c for c in contours if cv2.contourArea(c) > min_area]
        motion_detected = len(motion_contours) > 0

        # ── Build display frame (convert to BGR for annotations) ──────────
        display = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # Draw motion contours in yellow
        cv2.drawContours(display, motion_contours, -1, (0, 220, 220), 1)

        person_detected = False
        best_conf       = 0.0
        best_label      = ""

        # ── AI inference (only when motion) ──────────────────────────────
        if motion_detected:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            blob = cv2.dnn.blobFromImage(rgb_frame, 0.007843, (300, 300), 127.5)
            net.setInput(blob)
            detections = net.forward()

            for i in range(detections.shape[2]):
                conf = float(detections[0, 0, i, 2])
                if conf > conf_threshold:
                    idx   = int(detections[0, 0, i, 1])
                    label = CLASSES[idx] if idx < len(CLASSES) else "?"

                    # Bounding box
                    box   = detections[0, 0, i, 3:7] * np.array([WIDTH, HEIGHT, WIDTH, HEIGHT])
                    x1, y1, x2, y2 = box.astype(int)
                    color = (0, 0, 255) if label == "person" else (0, 180, 0)
                    cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(display, "%s %.0f%%" % (label, conf * 100),
                                (x1, max(y1 - 5, 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

                    if label == "person" and conf > best_conf:
                        person_detected = True
                        best_conf       = conf
                        best_label      = label

        # ── Status overlay ────────────────────────────────────────────────
        motion_color = (0, 220, 220) if motion_detected  else (80, 80, 80)
        person_color = (0, 0, 255)   if person_detected  else (80, 80, 80)
        cv2.putText(display, "MOTION" if motion_detected else "still",
                    (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, motion_color, 1)
        cv2.putText(display, "PERSON %.0f%%" % (best_conf * 100) if person_detected else "no person",
                    (5, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.5, person_color, 1)

        with frame_lock:
            latest_frame = display.copy()

        with status_lock:
            status["motion"]     = motion_detected
            status["person"]     = person_detected
            status["confidence"] = round(best_conf, 3)
            status["label"]      = best_label


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Detection Tuner</title>
<style>
  body { background:#111; color:#eee; font-family:monospace; margin:0; padding:16px; }
  h2   { margin:0 0 12px; color:#0af; }
  .wrap  { display:flex; gap:24px; flex-wrap:wrap; }
  .feed  { flex:0 0 auto; }
  .panel { flex:1; min-width:260px; }
  img    { display:block; border:2px solid #333; }
  .slider-row { margin:14px 0; }
  label  { display:block; margin-bottom:4px; font-size:13px; color:#aaa; }
  .val   { color:#0af; font-weight:bold; }
  input[type=range] { width:100%; accent-color:#0af; }
  .status { margin-top:20px; padding:12px; background:#1a1a1a; border-radius:6px; }
  .badge  { display:inline-block; padding:3px 10px; border-radius:4px;
            font-size:13px; margin:4px 4px 4px 0; }
  .on  { background:#c00; }
  .off { background:#333; color:#666; }
  .note { margin-top:16px; font-size:12px; color:#555; }
</style>
</head>
<body>
<h2>Detection Tuner</h2>
<div class="wrap">
  <div class="feed">
    <img src="/video" width="320" height="240">
  </div>
  <div class="panel">

    <div class="slider-row">
      <label>Confidence threshold: <span class="val" id="conf_val">0.50</span></label>
      <input type="range" id="conf_threshold" min="0.1" max="1.0" step="0.05" value="0.5"
             oninput="update('conf_threshold', this.value, 'conf_val')">
    </div>

    <div class="slider-row">
      <label>Min motion area (px²): <span class="val" id="area_val">2500</span></label>
      <input type="range" id="min_area" min="500" max="15000" step="500" value="2500"
             oninput="update('min_area', this.value, 'area_val')">
    </div>

    <div class="slider-row">
      <label>Motion pixel threshold: <span class="val" id="thresh_val">35</span></label>
      <input type="range" id="threshold_val" min="5" max="100" step="5" value="35"
             oninput="update('threshold_val', this.value, 'thresh_val')">
    </div>

    <div class="status" id="status">
      <div><span class="badge off" id="b_motion">MOTION</span>
           <span class="badge off" id="b_person">PERSON</span></div>
      <div style="margin-top:8px;font-size:13px;">
        Confidence: <span class="val" id="s_conf">—</span>
      </div>
    </div>

    <div class="note">
      Yellow contours = motion areas<br>
      Red box = person &nbsp; Green box = other object<br>
      Overlays update live as you move sliders.
    </div>
  </div>
</div>

<script>
function update(param, value, labelId) {
  document.getElementById(labelId).textContent =
    param === 'conf_threshold' ? parseFloat(value).toFixed(2) : value;
  fetch('/params', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[param]: parseFloat(value)})
  });
}

function pollStatus() {
  fetch('/status').then(r => r.json()).then(s => {
    document.getElementById('b_motion').className = 'badge ' + (s.motion ? 'on' : 'off');
    document.getElementById('b_person').className = 'badge ' + (s.person ? 'on' : 'off');
    document.getElementById('s_conf').textContent =
      s.person ? (s.confidence * 100).toFixed(0) + '%' : '—';
  });
}
setInterval(pollStatus, 500);
</script>
</body>
</html>"""


@app.route('/')
def index():
    return HTML


@app.route('/video')
def video():
    def generate():
        while True:
            with frame_lock:
                f = latest_frame
            if f is not None:
                ok, buf = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                           + buf.tobytes() + b'\r\n')
            time.sleep(0.1)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/params', methods=['POST'])
def set_params():
    data = request.get_json()
    with params_lock:
        for key in ('conf_threshold', 'min_area', 'threshold_val'):
            if key in data:
                params[key] = float(data[key])
    return jsonify({"ok": True})


@app.route('/status')
def get_status():
    with status_lock:
        return jsonify(dict(status))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    t = threading.Thread(target=detection_loop, daemon=True)
    t.start()
    print("[WEB] Open http://<pi-ip>:8000 in your browser")
    app.run(host='0.0.0.0', port=8000, threaded=True)
