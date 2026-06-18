#!/usr/bin/env python3
"""
update.py — Télécharge les layers uMap de Paolo et push data.json sur GitHub
Usage : python update.py
"""

import json, urllib.request, time, subprocess
from datetime import datetime
from pathlib import Path


def rdp(pts, epsilon):
    if len(pts) < 3:
        return pts
    start, end = pts[0], pts[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    norm = (dx*dx + dy*dy) ** 0.5
    max_d, max_i = 0.0, 0
    for i in range(1, len(pts) - 1):
        if norm:
            d = abs(dy*pts[i][0] - dx*pts[i][1] + end[0]*start[1] - end[1]*start[0]) / norm
        else:
            d = ((pts[i][0]-start[0])**2 + (pts[i][1]-start[1])**2) ** 0.5
        if d > max_d:
            max_d, max_i = d, i
    if max_d > epsilon:
        left  = rdp(pts[:max_i+1], epsilon)
        right = rdp(pts[max_i:],   epsilon)
        return left[:-1] + right
    return [start, end]

# ─── CONFIG ───────────────────────────────────────────────────────
LAYERS = [
    {"url": "https://umap.openstreetmap.fr/fr/datalayer/1007436/6c83c270-c92c-4cf9-8338-98033e16cd10/",
     "type": "avion",   "label": "Avion",   "emoji": "✈️",  "color": "#4a90d9"},
    {"url": "https://umap.openstreetmap.fr/fr/datalayer/1007436/83c373a4-1701-4cfe-be18-92a32a83a38b/",
     "type": "train",   "label": "Train",   "emoji": "🚆",  "color": "#c0392b"},
    {"url": "https://umap.openstreetmap.fr/fr/datalayer/1007436/d901a5e2-79d5-45da-a2c0-758ec6fd7b29/",
     "type": "bateau",  "label": "Bateau",  "emoji": "🚢",  "color": "#4a5568"},
    {"url": "https://umap.openstreetmap.fr/fr/datalayer/1007436/f732a9fd-d680-43eb-a449-9295a0293adc/",
     "type": "bus",     "label": "Bus",     "emoji": "🚌",  "color": "#27ae60"},
    {"url": "https://umap.openstreetmap.fr/fr/datalayer/1007436/f81757c9-4dd1-41fa-b689-6bd9840a3967/",
     "type": "voiture", "label": "Voiture", "emoji": "🚗",  "color": "#6c3483"},
]

OUTPUT_FILE = Path(__file__).parent / "data.json"
CACHE_DIR    = Path(__file__).parent / ".cache"

GEO_FILE = CACHE_DIR / "countries.geojson"
GEO_URL  = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"

# Epsilon RDP en degrés décimaux.
# 0.00005 = ~5m d'écart max → qualité haute, ~60-70% de réduction
# 0.0001  = ~10m            → bon compromis, ~75-80% de réduction
# 0.0003  = ~30m            → tracés longs (avion), ~85-90%
RDP_EPSILON = {
    "avion":   0.0003,
    "train":   0.0001,
    "bus":     0.0001,
    "voiture": 0.0001,
    "bateau":  0.0003,
}


# ─── POINT-IN-POLYGON ─────────────────────────────────────────────
def pip(lon, lat, ring):
    x, y = lon, lat
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_feature(lon, lat, feature):
    g = feature["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polys:
        if pip(lon, lat, poly[0]):
            if not any(pip(lon, lat, hole) for hole in poly[1:]):
                return True
    return False


def load_countries():
    if not GEO_FILE.exists():
        print("  ↓ Téléchargement Natural Earth…")
        req = urllib.request.Request(GEO_URL, headers={"User-Agent": "PaoloTracker/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        GEO_FILE.write_bytes(data)
        print(f"    Sauvegardé ({len(data)/1024:.0f} Ko)")
    return json.loads(GEO_FILE.read_bytes())


def coord_to_country(lon, lat, countries_data):
    for f in countries_data["features"]:
        if point_in_feature(lon, lat, f):
            props = f["properties"]
            return props.get("NAME") or props.get("name") or ""
    return ""


# ─── HELPERS ──────────────────────────────────────────────────────
def parse_date(s):
    try:
        return datetime.strptime(s, "%d/%m/%Y")
    except Exception:
        return datetime.min


def fetch_layer(layer):
    print(f"  ↓ {layer['label']:8s} … ", end="", flush=True)

    req = urllib.request.Request(
        layer["url"],
        headers={"User-Agent": "PaoloTracker/1.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())

    trips = []
    epsilon = RDP_EPSILON.get(layer["type"], 0.0001)
    total_before = 0
    total_after = 0

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if not props.get("date"):
            continue

        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [])

        dest_coord = None
        all_coords = None

        if geom.get("type") == "LineString" and len(coords) >= 2:
            dest_coord = coords[-1][:2]
            raw = [c[:2] for c in coords]
            simplified = rdp(raw, epsilon=epsilon)
            total_before += len(raw)
            total_after += len(simplified)
            all_coords = simplified

        elif geom.get("type") == "Point":
            dest_coord = coords[:2]

        trips.append({
            "date": props.get("date", ""),
            "from": props.get("from", ""),
            "to": props.get("to", ""),
            "km": int(props.get("km") or 0),
            "type": layer["type"],
            "label": layer["label"],
            "emoji": layer["emoji"],
            "color": layer["color"],
            "destCoord": dest_coord,
            "allCoords": all_coords,
            "country": "",
        })

    reduction = round((1 - total_after / total_before) * 100) if total_before else 0
    print(f"{len(trips)} trajets — coords {total_before}→{total_after} pts (-{reduction}%)")
    return trips


# ─── GIT PUSH ─────────────────────────────────────────────────────
def git_push():
    try:
        print("\n  🚀 Push GitHub...")

        subprocess.run(["git", "add", "data.json"], check=True)

        subprocess.run([
            "git", "commit",
            "-m", f"update data {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ], check=True)

        subprocess.run(["git", "pull", "--rebase"], check=True)
        subprocess.run(["git", "push"], check=True)

        print("  ✅ Push OK")

    except subprocess.CalledProcessError:
        print("  ⚠️ Rien à push ou erreur git (ignoré)")


# ─── MAIN ─────────────────────────────────────────────────────────
def main():
    print("=" * 52)
    print("  Où est Paolo ? — Update data.json + GitHub")
    print("=" * 52)

    CACHE_DIR.mkdir(exist_ok=True)
    all_trips = []

    for layer in LAYERS:
        try:
            trips = fetch_layer(layer)

            cache_file = CACHE_DIR / f"{layer['type']}.json"
            cache_file.write_text(json.dumps(trips, ensure_ascii=False, indent=2), encoding="utf-8")

            all_trips.extend(trips)

        except Exception as e:
            print(f"ERREUR — {e}")
            cache_file = CACHE_DIR / f"{layer['type']}.json"

            if cache_file.exists():
                print(f"    ↻ Cache utilisé pour {layer['label']}")
                all_trips.extend(json.loads(cache_file.read_text(encoding="utf-8")))

    # Sort by date
    all_trips.sort(key=lambda t: parse_date(t["date"]), reverse=True)

    # Countries
    print("\n  🌍 Résolution pays…")
    countries_data = load_countries()

    countries = set()

    for t in all_trips:
        if t.get("destCoord"):
            lon, lat = t["destCoord"]
            country = coord_to_country(lon, lat, countries_data)
            t["country"] = country
            if country:
                countries.add(country)

    countries = sorted(countries)

    # Stats
    total_km = sum(t["km"] for t in all_trips)
    year = datetime.now().year
    year_km = sum(t["km"] for t in all_trips if parse_date(t["date"]).year == year)
    year_trips = sum(1 for t in all_trips if parse_date(t["date"]).year == year)

    print(f"\n  ✓ {len(all_trips)} trajets — {total_km:,} km")
    print(f"  ✓ {year_km:,} km en {year} ({year_trips} trajets)")
    print(f"  ✓ {len(countries)} pays")

    updated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")

    output = {
        "updated_at": updated_at,
        "stats": {
            "total_km": total_km,
            "year_km": year_km,
            "year_trips": year_trips,
            "countries": countries
        },
        "trips": all_trips
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, separators=(',', ':')),
        encoding="utf-8"
    )

    print(f"\n  ✅ data.json généré ({OUTPUT_FILE.stat().st_size/1024:.0f} Ko)")

    git_push()

    print("=" * 52)

from datetime import datetime, timedelta
def run_daily():
    while True:
        print("\n[LOOP] Lancement update.py...")

        try:
            main()
        except Exception as e:
            print("[ERROR]", e)

        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        sleep_time = (next_run - datetime.now()).total_seconds()

        print(f"[LOOP] Prochain run dans {int(sleep_time)} sec")
        time.sleep(max(0, sleep_time))


if __name__ == "__main__":
    run_daily()
