import osmnx as ox
from pathlib import Path

ox.settings.useful_tags_way += ["name:en"]   # keep English road names too

CENTER = (13.612144, 100.837906)   # AU Suvarnabhumi campus   # AU Suvarnabhumi campus — verify in Google Maps
DIST_M = 5000                  # 5 km: campus, Bang Na–Trat Rd and nearby local roads

Path("data").mkdir(exist_ok=True)
G = ox.graph_from_point(CENTER, dist=DIST_M, network_type="drive_service")
ox.save_graphml(G, "data/roads.graphml")
print("Saved:", len(G.nodes), "nodes,", len(G.edges), "road segments")