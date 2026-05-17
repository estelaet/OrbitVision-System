"""
OrbitVision: Earth & Satellite Intelligence System
Flask WSGI app — Vercel + gunicorn compatible.
"""
import os
import sys
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.celestrak import (
    fetch_catalog, fetch_multiple_catalogs, fetch_iss_open_notify,
    CELESTRAK_CATALOGS, FALLBACK_TLES, _build_from_tles,
)
from api.skytrack import (
    compute_position, compute_orbit_path, compute_future_path, batch_compute_positions
)
from api.ethiopia import get_ethiopia_passes
from api.analytics import compute_analytics, get_ground_stations
from api.providers import (
    fetch_multi_provider, aggregate_all_providers, fetch_open_notify_people,
    fetch_open_notify_iss, fetch_ivan_by_id, get_provider_status, MULTI_PROVIDER_SEARCHES
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# ── Enrichment helpers ────────────────────────────────────────────────────────

SAT_META_MAP = {
    "ISS": {"country": "International", "operator": "NASA/Roscosmos", "sat_type": "Space Station", "orbit_type": "LEO", "status": "Active",
            "description": "International Space Station — crewed orbital lab, largest human structure in space.",
            "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/International_Space_Station_after_undocking_of_STS-132.jpg/320px-International_Space_Station_after_undocking_of_STS-132.jpg"},
    "CSS": {"country": "China", "operator": "CNSA", "sat_type": "Space Station", "orbit_type": "LEO", "status": "Active",
            "description": "Chinese Space Station (Tiangong) — China's modular crewed space station.", "image": None},
    "STARLINK": {"country": "USA", "operator": "SpaceX", "sat_type": "Communication", "orbit_type": "LEO", "status": "Active",
                 "description": "SpaceX Starlink mega-constellation for global broadband internet.", "image": None},
    "GPS": {"country": "USA", "operator": "US Space Force", "sat_type": "Navigation", "orbit_type": "MEO", "status": "Active",
            "description": "US Global Positioning System navigation satellite.", "image": None},
    "GALILEO": {"country": "Europe", "operator": "ESA/GSA", "sat_type": "Navigation", "orbit_type": "MEO", "status": "Active",
                "description": "European Galileo global navigation satellite system.", "image": None},
    "GLONASS": {"country": "Russia", "operator": "Roscosmos", "sat_type": "Navigation", "orbit_type": "MEO", "status": "Active",
                "description": "Russian GLONASS global navigation satellite system.", "image": None},
    "NOAA": {"country": "USA", "operator": "NOAA", "sat_type": "Weather", "orbit_type": "LEO", "status": "Active",
             "description": "NOAA weather satellite providing global atmospheric data.", "image": None},
    "METEOSAT": {"country": "Europe", "operator": "EUMETSAT", "sat_type": "Weather", "orbit_type": "GEO", "status": "Active",
                 "description": "European geostationary meteorological satellite.", "image": None},
    "GOES": {"country": "USA", "operator": "NOAA", "sat_type": "Weather", "orbit_type": "GEO", "status": "Active",
             "description": "NOAA Geostationary Operational Environmental Satellite.", "image": None},
    "HUBBLE": {"country": "USA", "operator": "NASA/ESA", "sat_type": "Science", "orbit_type": "LEO", "status": "Active",
               "description": "Hubble Space Telescope — iconic space observatory since 1990.",
               "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/HST-SM4.jpeg/320px-HST-SM4.jpeg"},
    "IRIDIUM": {"country": "USA", "operator": "Iridium Communications", "sat_type": "Communication", "orbit_type": "LEO", "status": "Active",
                "description": "Iridium NEXT global satellite phone constellation.", "image": None},
    "ONEWEB": {"country": "UK", "operator": "OneWeb", "sat_type": "Communication", "orbit_type": "LEO", "status": "Active",
               "description": "OneWeb LEO broadband constellation.", "image": None},
    "SENTINEL": {"country": "Europe", "operator": "ESA", "sat_type": "Science", "orbit_type": "LEO", "status": "Active",
                 "description": "ESA Sentinel Earth observation satellite (Copernicus programme).", "image": None},
    "LANDSAT": {"country": "USA", "operator": "NASA/USGS", "sat_type": "Science", "orbit_type": "LEO", "status": "Active",
                "description": "Landsat Earth observation satellite for land surface monitoring.", "image": None},
    "TERRA": {"country": "USA", "operator": "NASA", "sat_type": "Science", "orbit_type": "LEO", "status": "Active",
              "description": "NASA Terra Earth observation — part of EOS.", "image": None},
    "AQUA": {"country": "USA", "operator": "NASA", "sat_type": "Science", "orbit_type": "LEO", "status": "Active",
             "description": "NASA Aqua ocean and atmosphere monitoring satellite.", "image": None},
    "INTELSAT": {"country": "International", "operator": "Intelsat", "sat_type": "Communication", "orbit_type": "GEO", "status": "Active",
                 "description": "Intelsat geostationary communication satellite.", "image": None},
    "SES": {"country": "Luxembourg", "operator": "SES", "sat_type": "Communication", "orbit_type": "GEO", "status": "Active",
            "description": "SES geostationary communication satellite.", "image": None},
    "EUTELSAT": {"country": "Europe", "operator": "Eutelsat", "sat_type": "Communication", "orbit_type": "GEO", "status": "Active",
                 "description": "Eutelsat European geostationary satellite.", "image": None},
    "FY": {"country": "China", "operator": "CMA", "sat_type": "Weather", "orbit_type": "LEO", "status": "Active",
           "description": "Chinese Fengyun meteorological satellite.", "image": None},
    "METEOR": {"country": "Russia", "operator": "Roscosmos", "sat_type": "Weather", "orbit_type": "LEO", "status": "Active",
               "description": "Russian Meteor meteorological satellite.", "image": None},
    "COSMOS": {"country": "Russia", "operator": "Roscosmos", "sat_type": "Military", "orbit_type": "LEO", "status": "Inactive",
               "description": "Russian Cosmos military/civil satellite.", "image": None},
    "DEB": {"country": "Unknown", "operator": "N/A", "sat_type": "Debris", "orbit_type": "LEO", "status": "Debris",
            "description": "Space debris fragment in orbit.", "image": None},
}


def enrich_satellite(sat: dict) -> dict:
    name_up = sat.get("name", "").upper()
    for key, meta in SAT_META_MAP.items():
        if key in name_up:
            for k, v in meta.items():
                if k not in sat or not sat[k] or sat[k] in ("Unknown", "Various", ""):
                    sat[k] = v
            break
    # Ensure sat_type is set
    if not sat.get("sat_type"):
        sat["sat_type"] = sat.get("type", "Various")
    if not sat.get("orbit_type"):
        sat["orbit_type"] = "LEO"
    if not sat.get("status"):
        sat["status"] = "Active"
    if not sat.get("country"):
        sat["country"] = "Unknown"
    return sat


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), filename)


# ── Satellite endpoints ───────────────────────────────────────────────────────

@app.route("/api/satellites")
def get_satellites():
    catalog = request.args.get("catalog", "stations")
    orbit_type = request.args.get("orbit_type", "").strip()
    sat_type = request.args.get("type", "").strip()
    country = request.args.get("country", "").strip()
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip().upper()
    launch_min = request.args.get("launch_min", type=int)
    launch_max = request.args.get("launch_max", type=int)
    limit = min(request.args.get("limit", 150, type=int), 300)

    if catalog == "all":
        raw = aggregate_all_providers(["stations", "starlink", "weather", "gps",
                                       "galileo", "glonass", "iridium", "oneweb", "science", "geo"])
    elif catalog in MULTI_PROVIDER_SEARCHES:
        raw = fetch_multi_provider(catalog)
    else:
        raw = fetch_catalog(catalog)

    raw = [enrich_satellite(s) for s in raw]
    with_pos = batch_compute_positions(raw)

    results = with_pos
    if orbit_type:
        results = [s for s in results if s.get("orbit_type", "").upper() == orbit_type.upper()]
    if sat_type:
        results = [s for s in results if sat_type.lower() in (s.get("sat_type") or s.get("type", "")).lower()]
    if country:
        results = [s for s in results if country.lower() in s.get("country", "").lower()]
    if status:
        results = [s for s in results if s.get("status", "").lower() == status.lower()]
    if q:
        results = [s for s in results if q in s.get("name", "").upper()]
    if launch_min:
        results = [s for s in results if (s.get("launch_year") or 0) >= launch_min]
    if launch_max:
        results = [s for s in results if (s.get("launch_year") or 9999) <= launch_max]

    return jsonify({
        "satellites": results[:limit],
        "total": len(results),
        "catalog": catalog,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/satellite/<sat_id>")
def get_satellite(sat_id: str):
    raw = aggregate_all_providers(["stations", "starlink", "weather", "gps", "galileo",
                                   "glonass", "iridium", "oneweb", "science", "geo"])
    sat = next((s for s in raw if s["id"] == sat_id), None)
    if not sat:
        sat_data = fetch_ivan_by_id(int(sat_id)) if sat_id.isdigit() else None
        if not sat_data:
            return jsonify({"error": "Satellite not found"}), 404
        sat = sat_data
    sat = enrich_satellite(sat)
    pos = compute_position(sat["tle1"], sat["tle2"])
    orbit = compute_orbit_path(sat["tle1"], sat["tle2"], num_points=90)
    future = compute_future_path(sat["tle1"], sat["tle2"], minutes_ahead=90)
    return jsonify({
        "satellite": {**{k: v for k, v in sat.items() if k not in ("tle1", "tle2")}, **(pos or {})},
        "orbit_path": orbit,
        "future_path": future,
        "tle": {"line1": sat["tle1"], "line2": sat["tle2"]},
    })


@app.route("/api/iss")
def get_iss():
    raw = fetch_catalog("stations")
    iss = next((s for s in raw if "ZARYA" in s["name"] or
                ("ISS" in s["name"] and "DEB" not in s["name"] and "NAUKA" not in s["name"])), None)
    if iss:
        pos = compute_position(iss["tle1"], iss["tle2"])
        orbit = compute_orbit_path(iss["tle1"], iss["tle2"], num_points=60)
        future = compute_future_path(iss["tle1"], iss["tle2"], minutes_ahead=90)
        if pos:
            return jsonify({**pos, "name": iss["name"], "id": iss["id"],
                            "orbit_path": orbit, "future_path": future, "source": "sgp4"})
    # Open Notify fallback
    on = fetch_open_notify_iss()
    if on:
        return jsonify({"lat": on["lat"], "lon": on["lon"], "alt": 408.0,
                        "speed_kmh": 27600, "source": "open_notify", "orbit_path": [], "future_path": []})
    return jsonify({"error": "ISS data unavailable"}), 503


@app.route("/api/people-in-space")
def people_in_space():
    data = fetch_open_notify_people()
    return jsonify(data)


@app.route("/api/catalogs")
def get_catalogs():
    return jsonify({
        "catalogs": [
            {"id": "stations",  "name": "Space Stations", "icon": "🛸"},
            {"id": "starlink",  "name": "Starlink", "icon": "🔵"},
            {"id": "weather",   "name": "Weather Sats", "icon": "🌩"},
            {"id": "gps",       "name": "GPS", "icon": "📡"},
            {"id": "galileo",   "name": "Galileo (EU)", "icon": "🔶"},
            {"id": "glonass",   "name": "GLONASS (RU)", "icon": "🔴"},
            {"id": "iridium",   "name": "Iridium", "icon": "💬"},
            {"id": "oneweb",    "name": "OneWeb", "icon": "🌐"},
            {"id": "science",   "name": "Science", "icon": "🔭"},
            {"id": "geo",       "name": "GEO Comm", "icon": "📺"},
            {"id": "amateur",   "name": "Amateur (AMSAT)", "icon": "📻"},
            {"id": "military",  "name": "Military", "icon": "🛡"},
            {"id": "all",       "name": "All Providers", "icon": "🌍"},
        ]
    })


@app.route("/api/search")
def search_satellites():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "total": 0})
    from api.providers import fetch_ivan_search
    raw = fetch_ivan_search(q.upper(), "search", limit=20)
    raw += fetch_ivan_search(q.capitalize(), "search", limit=10)
    seen = set()
    unique = []
    for s in raw:
        if s["id"] not in seen:
            seen.add(s["id"])
            unique.append(s)
    results = []
    for s in unique[:25]:
        s = enrich_satellite(s)
        pos = compute_position(s["tle1"], s["tle2"])
        entry = {k: v for k, v in s.items() if k not in ("tle1", "tle2")}
        if pos:
            entry.update(pos)
        results.append(entry)
    return jsonify({"results": results, "total": len(unique)})


@app.route("/api/categories")
def get_categories():
    return jsonify({
        "orbit_types": ["LEO", "MEO", "GEO", "HEO", "SSO"],
        "satellite_types": ["Space Station", "Communication", "Navigation", "Weather",
                            "Science", "Amateur", "Military", "Debris", "Various"],
        "statuses": ["Active", "Inactive", "Debris", "Unknown"],
        "countries": ["USA", "Russia", "China", "International", "Europe", "Japan",
                      "India", "France", "Germany", "UK", "Luxembourg"],
    })


# ── Ethiopia ──────────────────────────────────────────────────────────────────

@app.route("/api/ethiopia/passes")
def ethiopia_passes():
    hours = min(request.args.get("hours", 24, type=int), 48)
    raw = fetch_catalog("stations")
    passes = get_ethiopia_passes(raw, hours_ahead=hours)
    return jsonify({
        "passes": passes,
        "observer": {"lat": 9.0350, "lon": 38.7451, "location": "Addis Ababa, Ethiopia",
                     "altitude_km": 2.355},
        "total": len(passes),
        "hours_ahead": hours,
    })


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.route("/api/analytics")
def analytics():
    raw = aggregate_all_providers(["stations", "starlink", "weather", "gps",
                                   "galileo", "iridium", "oneweb", "science", "geo"])
    raw = [enrich_satellite(s) for s in raw]
    with_pos = batch_compute_positions(raw)
    return jsonify(compute_analytics(with_pos))


# ── Ground stations ───────────────────────────────────────────────────────────

@app.route("/api/groundstations")
def ground_stations():
    return jsonify({"stations": get_ground_stations()})


# ── Providers ─────────────────────────────────────────────────────────────────

@app.route("/api/providers")
def providers():
    return jsonify({"providers": get_provider_status()})


@app.route("/api/status")
def api_status():
    return jsonify({
        "sources": get_provider_status(),
        "cache_ttl_seconds": 600,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Security ──────────────────────────────────────────────────────────────────

def _signal_from_orbital(sat: dict, pos: dict) -> dict:
    """Compute real RF signal parameters from orbital mechanics and known frequency allocations."""
    name = sat.get("name", "").upper()
    sat_type = sat.get("sat_type") or sat.get("type", "")
    alt = pos.get("alt") or 400.0

    # Published frequency allocations by satellite type / name
    if "GPS" in name or "BIIR" in name or "BIIF" in name or "BIIIA" in name:
        freq_mhz = 1575.42; band = "L1/L2-Band"; encrypted = True
    elif "GALILEO" in name:
        freq_mhz = 1575.42; band = "E1/E5-Band"; encrypted = False
    elif "GLONASS" in name:
        freq_mhz = 1602.0; band = "L1-Band"; encrypted = True
    elif "ISS" in name or "ZARYA" in name or "DESTINY" in name or "NAUKA" in name or "UNITY" in name:
        freq_mhz = 437.55; band = "UHF/S-Band"; encrypted = False
    elif "TIANHE" in name or "CSS" in name:
        freq_mhz = 2216.0; band = "S-Band"; encrypted = True
    elif "STARLINK" in name:
        freq_mhz = 11325.0; band = "Ku-Band"; encrypted = True
    elif "IRIDIUM" in name:
        freq_mhz = 1621.25; band = "L-Band"; encrypted = True
    elif "ONEWEB" in name:
        freq_mhz = 12500.0; band = "Ku-Band"; encrypted = True
    elif "NOAA" in name or "METEOR" in name or "FY" in name:
        freq_mhz = 137.5; band = "VHF/L-Band"; encrypted = False
    elif "METEOSAT" in name or "GOES" in name:
        freq_mhz = 1675.4; band = "L-Band/S-Band"; encrypted = False
    elif "HUBBLE" in name or "SWIFT" in name or "CHANDRA" in name:
        freq_mhz = 2287.5; band = "S-Band"; encrypted = False
    elif "TERRA" in name or "AQUA" in name or "LANDSAT" in name or "SENTINEL" in name:
        freq_mhz = 8212.5; band = "X-Band"; encrypted = False
    elif "INTELSAT" in name or "SES" in name or "ARABSAT" in name or "EUTELSAT" in name:
        freq_mhz = 11450.0; band = "Ku/Ka-Band"; encrypted = True
    elif "AMSAT" in name or sat_type == "Amateur":
        freq_mhz = 145.8; band = "VHF/UHF"; encrypted = False
    else:
        freq_mhz = 2025.0; band = "S-Band"; encrypted = True

    # Signal strength from altitude (inverse-square approximation, normalised to LEO)
    # Higher altitude → weaker received power. Reference: 400 km LEO = 90%.
    strength = max(20, min(97, round(97 * (400.0 / max(400.0, alt)) ** 0.45)))

    # SNR: LEO shorter path → better SNR; GEO weaker but stable
    snr = max(5.0, min(42.0, round(38.0 * (400.0 / max(400.0, alt)) ** 0.35, 1)))

    # Power received (dBm) — free-space path-loss simplified
    import math
    wavelength_m = 3e8 / (freq_mhz * 1e6)
    distance_m = alt * 1000
    fspl_db = 20 * math.log10(4 * math.pi * distance_m / wavelength_m)
    tx_power_dbm = 43.0  # typical transmit power ~20W = 43 dBm
    received_dbm = round(tx_power_dbm - fspl_db + 30.0, 1)  # +30 dB antenna gain est.
    received_dbm = max(-140.0, min(-60.0, received_dbm))

    return {
        "frequency_mhz": freq_mhz,
        "channel": band,
        "encrypted": encrypted,
        "signal_strength": strength,
        "snr_db": snr,
        "power_dbm": received_dbm,
        "anomaly": False,  # only flag real anomalies (e.g. out-of-plane if detected)
    }


@app.route("/api/security/signals")
def security_signals():
    catalogs_to_scan = ["stations", "gps", "iridium", "starlink", "weather", "science"]
    raw = []
    seen = set()
    for cat in catalogs_to_scan:
        for s in fetch_catalog(cat):
            if s["id"] not in seen:
                seen.add(s["id"])
                raw.append(s)
        if len(raw) >= 20:
            break

    signals = []
    for sat in raw[:20]:
        pos = compute_position(sat["tle1"], sat["tle2"])
        if not pos:
            continue
        rf = _signal_from_orbital(sat, pos)
        signals.append({
            "id": sat["id"],
            "name": sat["name"],
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt": pos["alt"],
            "sat_type": sat.get("sat_type") or sat.get("type", ""),
            "orbit_type": sat.get("orbit_type", "LEO"),
            **rf,
        })

    return jsonify({"signals": signals, "timestamp": datetime.now(timezone.utc).isoformat()})


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/api/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "OrbitVision", "version": "2.0"})


import time as _time

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"OrbitVision v2 starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
