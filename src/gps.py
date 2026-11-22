import csv, os, threading, time
from datetime import datetime
from flask import Flask, request

latest = {"lat": None, "lon": None, "time": None}
LOG = "data/gps_log.csv"
app = Flask(__name__)

@app.post("/gps")
def receive_gps():
    data = request.get_json(force=True, silent=True) or {}
    try:
        lat, lon = float(data["lat"]), float(data["lon"])
    except (KeyError, ValueError, TypeError):
        return "bad data", 400
    latest.update(lat=lat, lon=lon, time=time.time())
    with open(LOG, "a", newline="") as f:                 # also keep a log
        csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), lat, lon])
    return "ok"

def start(port=5001):
    """Run the receiver in the background."""
    os.makedirs("data", exist_ok=True)
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port),
                     daemon=True).start()

def get_fix(max_age=3.0):
    """Latest (lat, lon), or None if no GPS in the last few seconds."""
    if latest["time"] and time.time() - latest["time"] < max_age:
        return latest["lat"], latest["lon"]
    return None