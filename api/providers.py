"""
Multi-provider satellite data aggregator.
Supports: ivanstanojevic TLE API, Open Notify, N2YO (optional key), 
          AMSAT, CelesTrak GP data, hardcoded fallbacks.
"""
import requests
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "OrbitVision/1.0 (educational satellite tracker)"}
CACHE: dict = {}
CACHE_TTL = 600  # 10 minutes

# Provider registry
PROVIDERS = {
    "ivanstanojevic": {"name": "Ivan Stanojevic TLE API", "status": "online"},
    "open_notify": {"name": "Open Notify (ISS)", "status": "online"},
    "n2yo": {"name": "N2YO API", "status": "requires_key"},
    "celestrak_gp": {"name": "CelesTrak GP Data", "status": "online"},
    "amsat": {"name": "AMSAT Amateur Sats", "status": "online"},
    "fallback": {"name": "Hardcoded TLE Fallback", "status": "always_available"},
}


def _cache_get(key: str):
    e = CACHE.get(key)
    if e and (time.time() - e["ts"]) < CACHE_TTL:
        return e["data"]
    return None


def _cache_set(key: str, data) -> None:
    CACHE[key] = {"ts": time.time(), "data": data}


def get_provider_status() -> dict:
    status = {}
    for pid, info in PROVIDERS.items():
        status[pid] = {**info, "last_checked": time.strftime("%H:%M:%S UTC", time.gmtime())}
    return status


# ── ivanstanojevic API ────────────────────────────────────────────────────────

def fetch_ivan_search(query: str, catalog: str = "active", limit: int = 30) -> list:
    """Fetch TLE data via ivanstanojevic.me search API."""
    cached = _cache_get(f"ivan_{query}_{catalog}")
    if cached:
        return cached
    try:
        url = f"https://tle.ivanstanojevic.me/api/tle/?search={query}&sort=name&sort-dir=asc"
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for m in (data.get("member") or [])[:limit]:
            tle1 = m.get("line1", "")
            tle2 = m.get("line2", "")
            if not (tle1 and tle2 and tle1.startswith("1 ") and tle2.startswith("2 ")):
                continue
            results.append({
                "id": tle1[2:7].strip(),
                "name": m.get("name", "Unknown").strip(),
                "tle1": tle1,
                "tle2": tle2,
                "catalog": catalog,
                "provider": "ivanstanojevic",
            })
        _cache_set(f"ivan_{query}_{catalog}", results)
        return results
    except Exception as e:
        logger.warning(f"Ivan API failed for '{query}': {e}")
        return []


def fetch_ivan_by_id(norad_id: int) -> Optional[dict]:
    """Fetch single satellite TLE by NORAD ID."""
    try:
        url = f"https://tle.ivanstanojevic.me/api/tle/{norad_id}"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        m = resp.json()
        tle1 = m.get("line1", "")
        tle2 = m.get("line2", "")
        if not (tle1 and tle2):
            return None
        return {
            "id": tle1[2:7].strip(),
            "name": m.get("name", "Unknown").strip(),
            "tle1": tle1,
            "tle2": tle2,
            "catalog": "norad",
            "provider": "ivanstanojevic",
        }
    except Exception:
        return None


# ── CelesTrak GP data ─────────────────────────────────────────────────────────

CELESTRAK_GP_URLS = {
    "stations": "https://celestrak.org/SOCRATES/query.php",  # fallback
    "gp_stations": "https://celestrak.org/pub/TLE/stations.txt",
}

def fetch_celestrak_gp(group: str) -> list:
    """Try CelesTrak GP data endpoint."""
    cached = _cache_get(f"celestrak_gp_{group}")
    if cached:
        return cached
    urls_to_try = [
        f"https://celestrak.org/pub/TLE/{group}.txt",
        f"https://www.celestrak.com/pub/TLE/{group}.txt",
    ]
    for url in urls_to_try:
        try:
            resp = requests.get(url, headers={
                **HEADERS,
                "Referer": "https://celestrak.org/",
            }, timeout=10)
            if resp.status_code == 200 and resp.text.strip():
                results = _parse_tle_text(resp.text, group)
                if results:
                    _cache_set(f"celestrak_gp_{group}", results)
                    logger.info(f"CelesTrak GP: {len(results)} sats from {group}")
                    return results
        except Exception as e:
            logger.warning(f"CelesTrak GP failed for {group}: {e}")
    return []


def _parse_tle_text(text: str, catalog: str) -> list:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    results = []
    i = 0
    while i < len(lines) - 2:
        if lines[i].startswith("1 ") or lines[i].startswith("2 "):
            i += 1
            continue
        name = lines[i]
        if i + 2 < len(lines) and lines[i+1].startswith("1 ") and lines[i+2].startswith("2 "):
            tle1, tle2 = lines[i+1], lines[i+2]
            results.append({
                "id": tle1[2:7].strip(),
                "name": name,
                "tle1": tle1,
                "tle2": tle2,
                "catalog": catalog,
                "provider": "celestrak",
            })
            i += 3
        else:
            i += 1
    return results


# ── AMSAT amateur satellites ──────────────────────────────────────────────────

AMSAT_TLE_URL = "https://www.amsat.org/tle/current/nasabare.txt"

def fetch_amsat() -> list:
    cached = _cache_get("amsat")
    if cached:
        return cached
    try:
        resp = requests.get(AMSAT_TLE_URL, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        results = _parse_tle_text(resp.text, "amateur")
        for r in results:
            r["provider"] = "amsat"
            r["sat_type"] = "Amateur"
            r["orbit_type"] = "LEO"
            r["country"] = "Various"
            r["operator"] = "AMSAT"
            r["status"] = "Active"
        _cache_set("amsat", results)
        logger.info(f"AMSAT: {len(results)} amateur satellites")
        return results
    except Exception as e:
        logger.warning(f"AMSAT fetch failed: {e}")
        return []


# ── Open Notify (ISS precise position) ───────────────────────────────────────

def fetch_open_notify_iss() -> Optional[dict]:
    cached = _cache_get("open_notify_iss")
    if cached:
        return cached
    try:
        resp = requests.get("http://api.open-notify.org/iss-now.json", timeout=5)
        data = resp.json()
        result = {
            "lat": float(data["iss_position"]["latitude"]),
            "lon": float(data["iss_position"]["longitude"]),
            "timestamp": data["timestamp"],
            "source": "open_notify",
        }
        _cache_set("open_notify_iss", result)
        return result
    except Exception:
        return None


def fetch_open_notify_people() -> dict:
    try:
        resp = requests.get("http://api.open-notify.org/astros.json", timeout=5)
        data = resp.json()
        return data
    except Exception:
        return {"number": 0, "people": []}


# ── N2YO API (optional — needs API key) ──────────────────────────────────────

def fetch_n2yo(norad_id: int, api_key: str, observer_lat: float = 9.035,
               observer_lon: float = 38.745, observer_alt: float = 2.35) -> Optional[dict]:
    """Fetch satellite position from N2YO API (requires API key)."""
    if not api_key:
        return None
    try:
        url = (f"https://api.n2yo.com/rest/v1/satellite/positions/{norad_id}/"
               f"{observer_lat}/{observer_lon}/{observer_alt}/1/&apiKey={api_key}")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        info = data.get("info", {})
        positions = data.get("positions", [{}])[0]
        return {
            "id": str(norad_id),
            "name": info.get("satname", "Unknown"),
            "lat": positions.get("satlatitude"),
            "lon": positions.get("satlongitude"),
            "alt": positions.get("sataltitude"),
            "azimuth": positions.get("azimuth"),
            "elevation": positions.get("elevation"),
            "source": "n2yo",
        }
    except Exception as e:
        logger.warning(f"N2YO failed: {e}")
        return None


def fetch_n2yo_passes(norad_id: int, api_key: str, observer_lat: float = 9.035,
                      observer_lon: float = 38.745, observer_alt: float = 2.35,
                      days: int = 10, min_elevation: int = 10) -> list:
    """Fetch upcoming passes from N2YO API."""
    if not api_key:
        return []
    try:
        url = (f"https://api.n2yo.com/rest/v1/satellite/visualpasses/{norad_id}/"
               f"{observer_lat}/{observer_lon}/{observer_alt}/{days}/{min_elevation}"
               f"/&apiKey={api_key}")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        return data.get("passes", [])
    except Exception:
        return []


# ── Multi-provider aggregate search ──────────────────────────────────────────

MULTI_PROVIDER_SEARCHES = {
    "stations":    [("ivanstanojevic", "ISS"), ("ivanstanojevic", "TIANHE")],
    "starlink":    [("ivanstanojevic", "STARLINK-1"), ("ivanstanojevic", "STARLINK-2"),
                    ("ivanstanojevic", "STARLINK-3"), ("ivanstanojevic", "STARLINK-4"),
                    ("ivanstanojevic", "STARLINK-5")],
    "weather":     [("ivanstanojevic", "NOAA 1"), ("ivanstanojevic", "NOAA 2"),
                    ("ivanstanojevic", "METEOSAT"), ("ivanstanojevic", "GOES"),
                    ("ivanstanojevic", "FY-3"), ("ivanstanojevic", "METEOR")],
    "gps":         [("ivanstanojevic", "GPS BIIR"), ("ivanstanojevic", "GPS BIIF"),
                    ("ivanstanojevic", "GPS BIIIA"), ("ivanstanojevic", "GPS BIIIF")],
    "galileo":     [("ivanstanojevic", "GALILEO")],
    "glonass":     [("ivanstanojevic", "GLONASS")],
    "iridium":     [("ivanstanojevic", "IRIDIUM")],
    "oneweb":      [("ivanstanojevic", "ONEWEB")],
    "science":     [("ivanstanojevic", "HUBBLE"), ("ivanstanojevic", "TERRA"),
                    ("ivanstanojevic", "AQUA"), ("ivanstanojevic", "SENTINEL"),
                    ("ivanstanojevic", "LANDSAT"), ("ivanstanojevic", "SWIFT"),
                    ("ivanstanojevic", "CHANDRA"), ("ivanstanojevic", "JAMES WEBB")],
    "geo":         [("ivanstanojevic", "INTELSAT"), ("ivanstanojevic", "SES"),
                    ("ivanstanojevic", "ARABSAT"), ("ivanstanojevic", "EUTELSAT"),
                    ("ivanstanojevic", "DIRECTV"), ("ivanstanojevic", "ASTRA")],
    "debris":      [("ivanstanojevic", "FENGYUN 1C DEB"), ("ivanstanojevic", "COSMOS 2251")],
    "amateur":     [("amsat", None)],
    "military":    [("ivanstanojevic", "USA"), ("ivanstanojevic", "COSMOS"),
                    ("ivanstanojevic", "LACROSSE"), ("ivanstanojevic", "KEYHOLE")],
}


def fetch_multi_provider(catalog: str, max_per_search: int = 25) -> list:
    """Aggregate from multiple providers for a catalog."""
    cached = _cache_get(f"multi_{catalog}")
    if cached:
        return cached

    searches = MULTI_PROVIDER_SEARCHES.get(catalog, [("ivanstanojevic", catalog.upper())])
    all_sats = []
    seen_ids = set()

    for provider, query in searches:
        if provider == "ivanstanojevic" and query:
            results = fetch_ivan_search(query, catalog, limit=max_per_search)
        elif provider == "amsat":
            results = fetch_amsat()
        elif provider == "celestrak":
            results = fetch_celestrak_gp(query or catalog)
        else:
            results = []

        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_sats.append(r)

    _cache_set(f"multi_{catalog}", all_sats)
    return all_sats


def aggregate_all_providers(catalogs: list = None) -> list:
    """Aggregate satellites from all providers across catalogs."""
    if catalogs is None:
        catalogs = ["stations", "starlink", "weather", "gps", "iridium", "science", "geo"]
    all_sats = []
    seen_ids = set()
    for cat in catalogs:
        for s in fetch_multi_provider(cat):
            if s["id"] not in seen_ids:
                seen_ids.add(s["id"])
                all_sats.append(s)
    return all_sats
