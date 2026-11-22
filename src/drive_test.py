import time
from gps import start, get_fix
from road_match import nearest_road

start()
print("Waiting for GPS from iPhone...")
while True:
    fix = get_fix()
    if fix:
        en, th, d = nearest_road(*fix)
        print(f"{fix[0]:.5f}, {fix[1]:.5f} → {en}  ({d:.0f} m)")
    else:
        print("no GPS yet")
    time.sleep(1)