"""RoadScan AI - demo pipeline on a recorded video.

video -> YOLO detect + track -> one record per defect -> demo GPS on a real road
      -> road name (OSMnx) -> SQLite -> Telegram alert

How to use: change the SETTINGS below if needed, then run from the Roadscan_AI folder:
    python src/run_video.py
"""
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
from shapely.geometry import Point
from ultralytics import YOLO

# let Python find database.py (project folder) and road_match.py (src folder)
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import database as db          # noqa: E402
import road_match as rm        # noqa: E402


# ------------------------------------------------------------ 1. settings
# Change these values, save, and run the file again.
VIDEO = "data/videos/Dashcam-Front.mp4"   # the video to process
MODEL = "weights/best.pt"                 # the trained YOLO model
CONF = 0.25              # minimum detection confidence (0 to 1)

START = (13.6160, 100.8480)   # demo drive: GPS where the video starts
END = (13.6125, 100.8476)     # demo drive: GPS where the video ends

MIN_HITS = 3             # a defect must appear in at least this many frames
LOST_FRAMES = 15         # a defect is "gone" after this many frames without it
RADIUS = 12              # same type within this many metres = duplicate

RESET = True             # True = delete old records and evidence before starting
SHOW = True              # True = show the video window (press q to stop)
REALTIME = True          # True = play at normal video speed
TELEGRAM = True          # True = send Telegram alerts


# ------------------------------------------------------------ 2. helpers
def demo_gps(start, end, progress):
    """Pretend GPS: a point between start and end, moved onto the nearest named road."""
    lat = start[0] + (end[0] - start[0]) * progress
    lon = start[1] + (end[1] - start[1]) * progress
    pt = Point(*rm.to_utm.transform(lon, lat))
    idx = rm.named.sindex.nearest(pt, max_distance=300)
    if len(idx[1]):                                    # a named road is close: snap to it
        line = rm.named.iloc[idx[1][0]].geometry
        on = line.interpolate(line.project(pt))
        lon, lat = rm.to_utm.transform(on.x, on.y, direction="INVERSE")
    return lat, lon


def distance_m(lat1, lon1, lat2, lon2):
    """Distance in metres between two GPS points (haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(a))


def mark_alert_sent(rid):
    """Runs in the Telegram thread after an alert is delivered."""
    c = db.connect()
    c.execute("UPDATE detections SET alert_sent = 1 WHERE id = ?", (rid,))
    c.commit()
    c.close()


# ------------------------------------------------------------ 3. main
def main():
    # --- open the model, the video and the database
    model = YOLO(MODEL)
    cap = cv2.VideoCapture(VIDEO)
    if not cap.isOpened():
        sys.exit(f"Could not open video: {VIDEO}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    conn = db.connect()
    os.makedirs("evidence", exist_ok=True)
    if RESET:
        conn.execute("DELETE FROM detections")
        conn.execute("DELETE FROM trips")
        for f in Path("evidence").glob("RD*.jpg"):
            f.unlink()
    trip_id = "TRIP-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    conn.execute("INSERT INTO trips (trip_id, started_at, notes) VALUES (?,?,?)",
                 (trip_id, datetime.now().isoformat(timespec="seconds"), VIDEO))
    conn.commit()

    worker = None
    if TELEGRAM:
        from telegram_alert import AlertWorker
        worker = AlertWorker(on_sent=mark_alert_sent)

    tracks = {}          # track id -> the defect being followed right now
    new_records = []     # records saved in this run
    duplicates = 0

    # --- what happens when a defect leaves the view
    def finish_track(tid):
        nonlocal duplicates
        t = tracks.pop(tid)
        if t["hits"] < MIN_HITS:                  # seen too briefly: false alarm
            return
        lat, lon = t["gps"]
        road_en, road_th, _ = rm.nearest_road(lat, lon)

        for rec in db.list_nearby(conn, lat, lon):     # same type within radius = same defect
            if rec["type"] == t["cls"] and distance_m(lat, lon, rec["lat"], rec["lon"]) < RADIUS:
                db.update_seen(conn, rec["id"])
                duplicates += 1
                return

        rid = db.next_id(conn)
        path = f"evidence/{rid}.jpg"
        x1, y1, x2, y2 = t["box"]
        cv2.rectangle(t["frame"], (x1, y1), (x2, y2), (0, 200, 255), 3)
        cv2.putText(t["frame"], f"{t['cls']} {t['conf']:.0%}", (x1, max(y1 - 10, 25)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        cv2.imwrite(path, t["frame"])
        db.insert_detection(conn, trip_id, t["cls"], round(t["conf"], 3), lat, lon, road_th, path)
        row = dict(conn.execute("SELECT * FROM detections WHERE id = ?", (rid,)).fetchone())
        row["detected_at"] = row["detected_at"].replace("T", " ")
        new_records.append(row)
        print(f"NEW {rid}: {t['cls']} {t['conf']:.0%} at {lat:.5f}, {lon:.5f} - {road_en}")
        if worker:
            worker.add(row)

    # --- read the video frame by frame
    frame_no, t0 = 0, time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_no += 1
        result = model.track(frame, persist=True, conf=CONF,
                             tracker="bytetrack.yaml", verbose=False)[0]
        boxes = result.boxes

        if boxes.id is not None:                       # at least one tracked defect
            gps = demo_gps(START, END, frame_no / total)
            for tid, xyxy, conf, cls in zip(boxes.id.tolist(), boxes.xyxy.tolist(),
                                            boxes.conf.tolist(), boxes.cls.tolist()):
                x1, y1, x2, y2 = map(int, xyxy)
                t = tracks.setdefault(int(tid), {"cls": model.names[int(cls)], "hits": 0, "score": -1})
                t["hits"] += 1
                t["last"] = frame_no
                score = conf * (x2 - x1) * (y2 - y1)   # big and confident = clearest view
                if score > t["score"]:
                    t.update(score=score, conf=conf, box=(x1, y1, x2, y2),
                             frame=frame.copy(), gps=gps)

        for tid in [k for k, t in tracks.items() if frame_no - t["last"] > LOST_FRAMES]:
            finish_track(tid)

        if SHOW:
            cv2.imshow("RoadScan AI (press q to stop)", result.plot())
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if REALTIME:                              # wait so playback matches video speed
            time.sleep(max(0, frame_no / fps - (time.time() - t0)))

    # --- finish: save defects still on screen, close, summarise
    for tid in list(tracks):
        finish_track(tid)
    cap.release()
    cv2.destroyAllWindows()
    conn.execute("UPDATE trips SET ended_at = ? WHERE trip_id = ?",
                 (datetime.now().isoformat(timespec="seconds"), trip_id))
    conn.commit()

    counts = Counter(r["type"] for r in new_records)
    summary = "\n".join([f"🧾 Trip summary {trip_id}", f"New defects: {len(new_records)}"]
                        + [f"  • {name}: {n}" for name, n in counts.most_common()]
                        + [f"Duplicates skipped: {duplicates}"])
    print("\n" + summary)
    print(f"{frame_no} frames in {time.time() - t0:.0f}s")
    if worker:
        worker.finish(summary)                         # wait for alerts, then send the summary


if __name__ == "__main__":
    main()
