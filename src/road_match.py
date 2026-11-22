import time
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import Point

# ---- load once at start-up ----
G = ox.load_graphml("data/roads.graphml")
edges = ox.graph_to_gdfs(G, nodes=False)
edges = edges.to_crs(edges.estimate_utm_crs())      # metres, so distances are real
if "name:en" not in edges.columns:
    edges["name:en"] = None

named = edges[edges["name"].notna()]
to_utm = Transformer.from_crs("EPSG:4326", edges.crs, always_xy=True)

def _first(v):
    return v[0] if isinstance(v, list) else v

def _clean(v):
    v = _first(v)
    return None if v is None or (isinstance(v, float) and v != v) else v   # drop NaN

def nearest_road(lat, lon, max_named_m=30):
    """Return (english_name, thai_name, distance_m) for a GPS point."""
    pt = Point(*to_utm.transform(lon, lat))

    # 1) nearest NAMED road within max_named_m metres
    idx, dist = named.sindex.nearest(pt, max_distance=max_named_m, return_distance=True)
    if len(idx[1]):
        row = named.iloc[idx[1][0]]
        th = _clean(row["name"])
        return _clean(row["name:en"]) or th, th, float(dist[0])

        # 2) fallback: nearest road of any kind + the closest named road for context
    idx, dist = edges.sindex.nearest(pt, return_distance=True)
    row = edges.iloc[idx[1][0]]
    kind = _clean(row["highway"]) or "road"

    near_idx, near_d = named.sindex.nearest(pt, max_distance=500, return_distance=True)
    if len(near_idx[1]):
        near = named.iloc[near_idx[1][0]]
        near_th = _clean(near["name"])
        near_en = _clean(near["name:en"]) or near_th
        return (f"Unnamed {kind} road (near {near_en})",
                f"Unnamed {kind} road (near {near_th})", float(dist[0]))

    label = f"Unnamed {kind} road"
    return label, label, float(dist[0])

if __name__ == "__main__":
    tests = {
        "Campus centre":     (13.612144, 100.837906),   # your point - already real
        "Soi Nawamintrarachinuthit 3":         (13.615357321783781, 100.84609151413244),   # replace
        "Soi Abac": (13.614360733964524, 100.84782249677416),   # replace
        "Soi Nawamintrarachinuthit 1":   (13.613458672378982, 100.8469066699959),   # replace
    }
    nearest_road(13.612144, 100.837906)   # warm-up (builds the index)
    for expected, (lat, lon) in tests.items():
        t = time.perf_counter()
        en, th, d = nearest_road(lat, lon)
        ms = (time.perf_counter() - t) * 1000
        print(f"expected {expected:30} → {en} / {th}  ({d:.0f} m away, {ms:.1f} ms)")