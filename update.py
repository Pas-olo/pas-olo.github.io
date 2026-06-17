#!/usr/bin/env python3
"""
update.py — Télécharge les layers uMap de Paolo et push data.json sur GitHub
Usage : python update.py
"""

import json, urllib.request, time, subprocess
from datetime import datetime
from pathlib import Path

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
            step = max(1, len(coords) // 200)
            all_coords = [c[:2] for c in coords[::step]]
            if all_coords[-1] != coords[-1][:2]:
                all_coords.append(coords[-1][:2])

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

    print(f"{len(trips)} trajets")
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
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n  ✅ data.json généré ({OUTPUT_FILE.stat().st_size/1024:.0f} Ko)")

    git_push()

    print("=" * 52)


if __name__ == "__main__":
    main()
