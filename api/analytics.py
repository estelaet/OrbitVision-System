"""
OrbitAnalytics Engine — Satellite statistics and orbit behavior analysis.
"""
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone


def compute_analytics(satellites: list) -> dict:
    """Compute analytics from satellite dataset."""
    if not satellites:
        return {}

    total = len(satellites)
    orbit_types = Counter(s.get("orbit_type", "Unknown") for s in satellites)
    sat_types = Counter(s.get("sat_type", s.get("type", "Unknown")) for s in satellites)
    countries = Counter(s.get("country", "Unknown") for s in satellites)
    statuses = Counter(s.get("status", "Unknown") for s in satellites)
    operators = Counter(s.get("operator", "Unknown") for s in satellites)

    # Altitude statistics
    alts = [s["alt"] for s in satellites if "alt" in s and s["alt"] is not None]
    avg_alt = round(sum(alts) / len(alts), 1) if alts else 0
    max_alt = round(max(alts), 1) if alts else 0
    min_alt = round(min(alts), 1) if alts else 0

    # Speed statistics
    speeds = [s.get("speed_kmh", 0) for s in satellites if s.get("speed_kmh")]
    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0

    # Launch year distribution
    years = Counter(s.get("launch_year", 0) for s in satellites if s.get("launch_year", 0) > 1950)
    year_distribution = [{"year": y, "count": c} for y, c in sorted(years.items())]

    # Altitude bands
    leo = sum(1 for a in alts if a < 2000)
    meo = sum(1 for a in alts if 2000 <= a < 35786)
    geo = sum(1 for a in alts if a >= 35786)

    # Coverage map (simulated ground track density by region)
    coverage_regions = _compute_coverage_regions(satellites)

    return {
        "total_satellites": total,
        "orbit_types": dict(orbit_types),
        "satellite_types": dict(sat_types),
        "countries": dict(countries.most_common(10)),
        "operators": dict(operators.most_common(10)),
        "statuses": dict(statuses),
        "altitude": {
            "average_km": avg_alt,
            "max_km": max_alt,
            "min_km": min_alt,
            "leo_count": leo,
            "meo_count": meo,
            "geo_count": geo,
        },
        "speed": {
            "average_kmh": avg_speed,
        },
        "launch_years": year_distribution[-20:],  # last 20 years
        "coverage_regions": coverage_regions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _compute_coverage_regions(satellites: list) -> list:
    """Compute which regions have most satellite coverage."""
    regions = {
        "North America": {"lat_range": (24, 72), "lon_range": (-170, -52)},
        "South America": {"lat_range": (-56, 12), "lon_range": (-82, -34)},
        "Europe": {"lat_range": (36, 71), "lon_range": (-10, 40)},
        "Africa": {"lat_range": (-35, 37), "lon_range": (-18, 52)},
        "Asia": {"lat_range": (1, 77), "lon_range": (26, 180)},
        "Oceania": {"lat_range": (-47, -10), "lon_range": (112, 180)},
        "Polar": {"lat_range": (66, 90), "lon_range": (-180, 180)},
    }
    region_counts = {r: 0 for r in regions}
    for sat in satellites:
        lat = sat.get("lat")
        lon = sat.get("lon")
        if lat is None or lon is None:
            continue
        for region, bounds in regions.items():
            if (bounds["lat_range"][0] <= lat <= bounds["lat_range"][1] and
                    bounds["lon_range"][0] <= lon <= bounds["lon_range"][1]):
                region_counts[region] += 1
    return [{"region": r, "count": c} for r, c in sorted(region_counts.items(), key=lambda x: -x[1])]


def get_ground_stations() -> list:
    """Return simulated ground station network (TerraLink Network)."""
    return [
        {"id": "gs1", "name": "Cape Canaveral", "lat": 28.3922, "lon": -80.6077,
         "country": "USA", "status": "active", "latency_ms": 12, "signal_strength": 98},
        {"id": "gs2", "name": "Baikonur Cosmodrome", "lat": 45.9654, "lon": 63.3052,
         "country": "Kazakhstan", "status": "active", "latency_ms": 45, "signal_strength": 92},
        {"id": "gs3", "name": "Kennedy Space Center", "lat": 28.5734, "lon": -80.6490,
         "country": "USA", "status": "active", "latency_ms": 8, "signal_strength": 99},
        {"id": "gs4", "name": "Guiana Space Centre", "lat": 5.2390, "lon": -52.7680,
         "country": "France", "status": "active", "latency_ms": 38, "signal_strength": 95},
        {"id": "gs5", "name": "Jiuquan Launch Center", "lat": 40.9600, "lon": 100.2908,
         "country": "China", "status": "active", "latency_ms": 55, "signal_strength": 89},
        {"id": "gs6", "name": "Vandenberg AFB", "lat": 34.7420, "lon": -120.5724,
         "country": "USA", "status": "active", "latency_ms": 15, "signal_strength": 97},
        {"id": "gs7", "name": "Tanegashima Space Center", "lat": 30.4014, "lon": 130.9750,
         "country": "Japan", "status": "active", "latency_ms": 62, "signal_strength": 91},
        {"id": "gs8", "name": "ESRIN - ESA", "lat": 41.8266, "lon": 12.6484,
         "country": "Italy", "status": "active", "latency_ms": 28, "signal_strength": 96},
        {"id": "gs9", "name": "Addis Ababa Ground Station", "lat": 9.0350, "lon": 38.7451,
         "country": "Ethiopia", "status": "monitoring", "latency_ms": 72, "signal_strength": 78},
        {"id": "gs10", "name": "McMurdo Station", "lat": -77.8500, "lon": 166.7500,
         "country": "USA", "status": "active", "latency_ms": 110, "signal_strength": 84},
        {"id": "gs11", "name": "Svalbard Ground Station", "lat": 78.2280, "lon": 15.4080,
         "country": "Norway", "status": "active", "latency_ms": 35, "signal_strength": 93},
        {"id": "gs12", "name": "Alice Springs", "lat": -23.6980, "lon": 133.8807,
         "country": "Australia", "status": "active", "latency_ms": 88, "signal_strength": 87},
    ]
