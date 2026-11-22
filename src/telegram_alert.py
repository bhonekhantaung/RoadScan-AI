import os, queue, threading, time
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API = f"https://api.telegram.org/bot{TOKEN}"

NICE = {
    "pothole": "Pothole",
    "water_filled_pothole": "Water-filled pothole",
    "longitudinal_crack": "Longitudinal crack",
    "transverse_crack": "Transverse crack",
    "alligator_crack": "Alligator crack",
}

# ---------- sending (one alert) ----------
def send_alert(rec):
    """Send one defect: photo + caption, then a map pin. Returns True if sent."""
    caption = (
        "⚠️ Road Damage Detected\n"
        f"ID: {rec['id']}\n"
        f"Type: {NICE.get(rec['type'], rec['type'])}\n"
        f"Confidence: {rec['confidence']:.0%}\n"
        f"Road: {rec['road_name']}\n"
        f"GPS: {rec['lat']:.5f}, {rec['lon']:.5f}\n"
        f"Time: {rec['detected_at']}\n"
        f"Status: {rec.get('status', 'New')}"
    )
    try:
        with open(rec["evidence_path"], "rb") as photo:
            r = requests.post(f"{API}/sendPhoto",
                              data={"chat_id": CHAT_ID, "caption": caption},
                              files={"photo": photo}, timeout=15)
        if not r.json().get("ok"):
            print("Telegram photo error:", r.json()); return False
        requests.post(f"{API}/sendLocation", timeout=10,
                      data={"chat_id": CHAT_ID,
                            "latitude": rec["lat"], "longitude": rec["lon"]})
        return True
    except (requests.RequestException, OSError) as e:
        print("Telegram send failed:", e)      # no signal, missing file, etc.
        return False

def send_text(text):
    try:
        requests.post(f"{API}/sendMessage", data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except requests.RequestException as e:
        print("Telegram text failed:", e)

# ---------- background worker (so detection never waits) ----------
class AlertWorker:
    """Put records in with .add(rec); a background thread sends them.
    on_sent(rec_id) is called after each successful send (e.g. mark alert_sent=1)."""

    def __init__(self, on_sent=None, retries=3):
        self.q = queue.Queue()
        self.failed = []
        self.on_sent, self.retries = on_sent, retries
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, rec):
        self.q.put(rec)

    def _run(self):
        while True:
            rec = self.q.get()
            for attempt in range(self.retries):
                if send_alert(rec):
                    if self.on_sent:
                        self.on_sent(rec["id"])
                    break
                time.sleep(2 * (attempt + 1))   # wait 2s, 4s, 6s between tries
            else:
                self.failed.append(rec)        # keep for end-of-trip retry
            self.q.task_done()

    def finish(self, summary_text=None):
        """Call at the end of a trip: wait for the queue, retry failures, send summary."""
        self.q.join()
        for rec in list(self.failed):
            if send_alert(rec):
                self.failed.remove(rec)
                if self.on_sent:
                    self.on_sent(rec["id"])
        if summary_text:
            send_text(summary_text)

# ---------- test: python src/telegram_alert.py ----------
if __name__ == "__main__":
    import cv2
    from datetime import datetime

    os.makedirs("evidence", exist_ok=True)
    img = cv2.imread("bus.jpg")                       # any image works for the test
    cv2.rectangle(img, (200, 400), (450, 600), (0, 200, 255), 4)
    cv2.putText(img, "Pothole 94%", (200, 390), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 3)
    cv2.imwrite("evidence/TEST001.jpg", img)

    test = {
        "id": "TEST001", "type": "pothole", "confidence": 0.94,
        "road_name": "ซอยเอแบค", "lat": 13.614360, "lon": 100.847822,
        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "evidence_path": "evidence/TEST001.jpg", "status": "New",
    }

    worker = AlertWorker(on_sent=lambda rid: print("✅ sent", rid))
    worker.add(test)
    print("Queued - detection would keep running here...")
    worker.finish("🧾 Trip summary (test): 1 defect - 1 pothole on ซอยเอแบค")
    print("Done.")