import cv2
import numpy as np
import subprocess
import os
from udp_comm import UDPComm

# --- CONFIG ---
WIDTH, HEIGHT = 320, 240
MIN_AREA = 2500
THRESHOLD_VAL = 35
CONF_THRESHOLD = 0.5

# Absolute path setup to avoid "File Not Found" errors
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROTOTXT = os.path.join(BASE_DIR, "model/deploy.prototxt")
MODEL = os.path.join(BASE_DIR, "model/mobilenet_iter_73000.caffemodel")

CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat",
           "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
           "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
           "sofa", "train", "tvmonitor"]

# Load the network
print(f"Loading AI model from {MODEL}...")
net = cv2.dnn.readNetFromCaffe(PROTOTXT, MODEL)
# Force the network to use the OpenCV CPU backend
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
# Start Camera - Using 5 FPS to keep the Pi 3 stable
cmd = ['rpicam-vid', '-t', '0', '--inline', '--nopreview', '--width', str(WIDTH),
       '--height', str(HEIGHT), '--framerate', '5', '--codec', 'yuv420', '-o', '-']
pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)

avg_frame = None
comm = UDPComm()   # <-- starts background listener thread

print("System Live: Monitoring...")

try:
    while True:
        # Read exactly the Y-plane (Luminance)
        raw_image = pipe.stdout.read(WIDTH * HEIGHT)
        if not raw_image or len(raw_image) != (WIDTH * HEIGHT):
            continue

        # Create a writeable copy of the frame
        frame = np.frombuffer(raw_image, dtype=np.uint8).reshape((HEIGHT, WIDTH)).copy()

        # --- MOTION DETECTION (CHEAP) ---
        gray = cv2.GaussianBlur(frame, (21, 21), 0)
        if avg_frame is None:
            avg_frame = gray.copy().astype("float")
            continue

        cv2.accumulateWeighted(gray, avg_frame, 0.05)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg_frame))
        thresh = cv2.threshold(frame_delta, THRESHOLD_VAL, 255, cv2.THRESH_BINARY)[1]
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_detected = any(cv2.contourArea(c) > MIN_AREA for c in contours)

        if motion_detected:
            #comm.send_motion()

            # --- AI DETECTION (EXPENSIVE) ---
            # 1. Convert Grayscale to RGB (Required by MobileNet)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)

            # 2. Create the blob with proper scaling and normalization
            blob = cv2.dnn.blobFromImage(rgb_frame, 0.007843, (300, 300), 127.5)

            # 3. Double-check blob isn't empty before calling forward()
            if blob is not None:
                net.setInput(blob)
                detections = net.forward()

                # Loop through detections
                # Output shape is [1, 1, N, 7]
                for i in range(detections.shape[2]):
                    confidence = detections[0, 0, i, 2]

                    if confidence > CONF_THRESHOLD:
                        idx = int(detections[0, 0, i, 1])
                        label = CLASSES[idx]

                        if label == "person":
                            print(f"!!! PERSON DETECTED ({confidence:.2f})")
                            comm.send_person(confidence)
        else:
            comm.send_clear()
            print("Status: Scanning...", end='\r')

finally:
    pipe.terminate()
    comm.close()
