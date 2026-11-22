import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("roadscan.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    trip_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS detections (
    id TEXT PRIMARY KEY,
    trip_id TEXT REFERENCES trips(trip_id),
    type TEXT NOT NULL,
    confidence REAL,
    lat REAL, lon REAL,
    road_name TEXT,
    detected_at TEXT,
    evidence_path TEXT,
    status TEXT DEFAULT 'New' CHECK (status IN ('New','Reviewed','Repaired')),
    seen_count INTEGER DEFAULT 1,
    alert_sent INTEGER DEFAULT 0
);
"""

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def next_id(conn):
    n = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0] + 1
    return f"RD{n:03d}"

def insert_detection(conn, trip_id, type_, conf, lat, lon, road, evidence_path):
    rid = next_id(conn)
    conn.execute(
        "INSERT INTO detections (id, trip_id, type, confidence, lat, lon, road_name,"
        " detected_at, evidence_path) VALUES (?,?,?,?,?,?,?,?,?)",
        (rid, trip_id, type_, conf, lat, lon, road,
         datetime.now().isoformat(timespec="seconds"), evidence_path))
    conn.commit()
    return rid

def list_nearby(conn, lat, lon, deg=0.0003):   # ~30 m box; refine with haversine
    return [dict(r) for r in conn.execute(
        "SELECT * FROM detections WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
        (lat - deg, lat + deg, lon - deg, lon + deg))]

def update_seen(conn, rid, conf=None, evidence_path=None):
    conn.execute("UPDATE detections SET seen_count = seen_count + 1 WHERE id = ?", (rid,))
    if conf is not None and evidence_path:     # keep the clearer frame
        conn.execute("UPDATE detections SET confidence=?, evidence_path=? "
                     "WHERE id=? AND confidence < ?", (conf, evidence_path, rid, conf))
    conn.commit()

if __name__ == "__main__":
    c = connect()
    rid = insert_detection(c, "TRIP-TEST", "pothole", 0.94, 13.7567, 100.5018,
                           "Ratchadamnoen Klang Road", "evidence/test.jpg")
    print(rid, list_nearby(c, 13.7567, 100.5018))