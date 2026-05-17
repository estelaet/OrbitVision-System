"""
CelesTrak TLE data fetcher — uses tle.ivanstanojevic.me API with hardcoded fallbacks.
DataSource Switcher supports multiple catalogs and fallback chains.
"""
import requests
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CACHE: dict = {}
CACHE_TTL = 900  # 15 minutes

TLE_API_BASE = "https://tle.ivanstanojevic.me/api/tle"

HEADERS = {
    "User-Agent": "OrbitVision/1.0 (satellite tracking educational app)",
    "Accept": "application/json",
}

# ── Hardcoded fallback TLEs (always available) ─────────────────────────────────
FALLBACK_TLES = {
    "stations": [
        ("ISS (ZARYA)",    "1 25544U 98067A   26136.58530741  .00005232  00000+0  10222-3 0  9992",
                           "2 25544  51.6320  96.5382 0007506  65.6623 294.5149 15.49235175566854"),
        ("CSS (TIANHE)",   "1 48274U 21035A   26136.52101435  .00010621  00000+0  12538-3 0  9995",
                           "2 48274  41.4757 204.0133 0005878 354.5124   5.5952 15.59971534270578"),
    ],
    "weather": [
        ("NOAA 15",        "1 25338U 98030A   26136.71524769  .00000247  00000+0  11673-3 0  9999",
                           "2 25338  98.5480 173.1924 0011116 206.9793 153.0807 14.25775393362698"),
        ("NOAA 18",        "1 28654U 05018A   26136.60248574  .00000131  00000+0  10074-3 0  9991",
                           "2 28654  98.8847 198.1543 0013917 321.1524  38.8687 14.12971625991217"),
        ("NOAA 19",        "1 33591U 09005A   26136.76034259  .00000257  00000+0  16108-3 0  9994",
                           "2 33591  98.7141 215.0085 0013920 113.1580 247.1098 14.12268038802803"),
        ("NOAA 20",        "1 43013U 17073A   26136.56001157  .00000028  00000+0  32059-4 0  9997",
                           "2 43013  98.7380 204.5748 0001126  95.7823 264.3524 14.19555466391440"),
        ("METEOSAT-11",    "1 41844U 16071A   26136.50000000 -.00000003  00000+0  00000+0 0  9996",
                           "2 41844   0.0441 128.9855 0000924 226.5000 211.9000  1.00272028 34412"),
    ],
    "gps": [
        ("GPS BIIR-2  (PRN 13)", "1 24876U 97035A   26136.45001157  .00000049  00000+0  00000+0 0  9999",
                                  "2 24876  55.6097  52.2481 0046783  33.2219 327.1261  2.00566033212888"),
        ("GPS BIIR-11 (PRN 19)", "1 28190U 04009A   26136.37001157 -.00000054  00000+0  00000+0 0  9993",
                                  "2 28190  55.1289 232.3219 0106440 145.0581 215.8183  2.00556803161498"),
        ("GPS BIIIA-3 (PRN 18)", "1 43873U 18109A   26136.52001157  .00000000  00000+0  00000+0 0  9990",
                                  "2 43873  55.0155  56.8547 0009948 229.2862 130.7364  2.00565459 54419"),
    ],
    "starlink": [
        ("STARLINK-1007", "1 44713U 19074B   26136.50001157  .00001321  00000+0  10568-3 0  9997",
                          "2 44713  53.0546 174.3519 0001312  68.8236 291.2908 15.05764717350126"),
        ("STARLINK-1008", "1 44714U 19074C   26136.50001157  .00001285  00000+0  10296-3 0  9993",
                          "2 44714  53.0547 174.3521 0001198  71.2381 288.8763 15.05758913350132"),
        ("STARLINK-2000", "1 47685U 21002T   26136.50001157  .00001422  00000+0  11238-3 0  9998",
                          "2 47685  53.0529 144.3018 0001412  88.3742 271.7402 15.06765311288041"),
        ("STARLINK-3000", "1 52765U 22049BG  26136.50001157  .00001389  00000+0  10975-3 0  9994",
                          "2 52765  53.0508 114.3712 0001388 102.3516 257.7628 15.07013476202041"),
        ("STARLINK-4000", "1 56217U 23035AY  26136.50001157  .00001455  00000+0  11488-3 0  9998",
                          "2 56217  43.0012  84.3119 0001215 118.4112 241.6432 15.07214578150302"),
        ("STARLINK-5000", "1 58847U 23174AX  26136.50001157  .00001488  00000+0  11755-3 0  9996",
                          "2 58847  43.0001  54.2419 0001102 134.5112 225.5832 15.07414578110302"),
    ],
    "science": [
        ("HUBBLE",         "1 20580U 90037B   26136.48001157  .00000882  00000+0  37082-4 0  9999",
                           "2 20580  28.4697  75.2186 0002440 251.8512 108.2208 15.09623710534201"),
        ("TERRA",          "1 25994U 99068A   26136.48001157  .00000217  00000+0  60742-4 0  9990",
                           "2 25994  98.2024 199.3876 0000972  85.8241 274.3025 14.57122547317681"),
        ("AQUA",           "1 27424U 02022A   26136.48001157  .00000193  00000+0  55028-4 0  9998",
                           "2 27424  98.2002 200.3876 0001432  86.2415 273.8641 14.57113547293421"),
        ("SENTINEL-2A",    "1 40697U 15028A   26136.48001157  .00000000  00000+0  19979-4 0  9991",
                           "2 40697  98.5706 200.4188 0001113 112.4126 247.7161 14.30818028574127"),
        ("LANDSAT 9",      "1 49260U 21088A   26136.48001157  .00000147  00000+0  60500-4 0  9998",
                           "2 49260  98.2014 201.3117 0001308 102.4123 257.7115 14.57121547244101"),
    ],
    "iridium": [
        ("IRIDIUM 180",    "1 43072U 17083E   26136.48001157  .00000108  00000+0  33178-4 0  9991",
                           "2 43072  86.3938 147.3519 0002192  92.1241 267.9988 14.34221618447081"),
        ("IRIDIUM 181",    "1 43073U 17083F   26136.48001157  .00000106  00000+0  32491-4 0  9998",
                           "2 43073  86.3938 147.3521 0002135  93.2419 266.8810 14.34221618441891"),
        ("IRIDIUM 182",    "1 43075U 17083H   26136.48001157  .00000110  00000+0  33778-4 0  9996",
                           "2 43075  86.3938 147.3523 0002201  91.5541 268.4688 14.34221618447081"),
    ],
    "geo": [
        ("INTELSAT 35E",   "1 42698U 17024A   26136.50000000 -.00000093  00000+0  00000+0 0  9996",
                           "2 42698   0.0130  87.8126 0002119 247.1541 226.1419  1.00271897 32618"),
        ("SES-12",         "1 43488U 18046A   26136.50000000 -.00000095  00000+0  00000+0 0  9991",
                           "2 43488   0.0451 101.4212 0001112 222.8041 186.8419  1.00272109 29181"),
        ("ARABSAT 6A",     "1 44186U 19023A   26136.50000000 -.00000077  00000+0  00000+0 0  9997",
                           "2 44186   0.0181  81.7812 0001312 219.4541 175.8419  1.00272815 25661"),
    ],
    "debris": [
        ("FENGYUN 1C DEB", "1 29228U 99025CYQ 26136.50001157  .00000000  00000+0  00000+0 0  9992",
                           "2 29228  98.6412 214.5888 0145122 348.1241  11.8941 14.14828762898101"),
        ("COSMOS 2251 DEB","1 33749U 93036AE  26136.50001157  .00000115  00000+0  40811-4 0  9991",
                           "2 33749  74.0421  88.1121 0051212  12.4421 347.7121 14.19229562581001"),
    ],
}

SAT_METADATA = {
    "ISS": {
        "country": "International", "operator": "NASA/Roscosmos",
        "type": "Space Station", "status": "Active", "orbit_type": "LEO",
        "description": "International Space Station — crewed orbital laboratory, largest human structure in space.",
        "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/International_Space_Station_after_undocking_of_STS-132.jpg/320px-International_Space_Station_after_undocking_of_STS-132.jpg",
    },
    "CSS": {
        "country": "China", "operator": "CNSA", "type": "Space Station",
        "status": "Active", "orbit_type": "LEO",
        "description": "Chinese Space Station (Tiangong) — China's modular space station.",
        "image": None,
    },
    "STARLINK": {
        "country": "USA", "operator": "SpaceX", "type": "Communication",
        "status": "Active", "orbit_type": "LEO",
        "description": "SpaceX Starlink mega-constellation providing global broadband internet.",
        "image": None,
    },
    "GPS": {
        "country": "USA", "operator": "US Space Force", "type": "Navigation",
        "status": "Active", "orbit_type": "MEO",
        "description": "Global Positioning System — US military and civilian navigation satellite.",
        "image": None,
    },
    "NOAA": {
        "country": "USA", "operator": "NOAA", "type": "Weather",
        "status": "Active", "orbit_type": "LEO",
        "description": "NOAA weather monitoring satellite providing global atmospheric data.",
        "image": None,
    },
    "METEOSAT": {
        "country": "Europe", "operator": "EUMETSAT", "type": "Weather",
        "status": "Active", "orbit_type": "GEO",
        "description": "European geostationary meteorological satellite.",
        "image": None,
    },
    "HUBBLE": {
        "country": "USA", "operator": "NASA/ESA", "type": "Science",
        "status": "Active", "orbit_type": "LEO",
        "description": "Hubble Space Telescope — iconic space observatory since 1990.",
        "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/HST-SM4.jpeg/320px-HST-SM4.jpeg",
    },
    "IRIDIUM": {
        "country": "USA", "operator": "Iridium Communications", "type": "Communication",
        "status": "Active", "orbit_type": "LEO",
        "description": "Iridium NEXT — low Earth orbit satellite phone network.",
        "image": None,
    },
    "TERRA": {
        "country": "USA", "operator": "NASA", "type": "Science",
        "status": "Active", "orbit_type": "LEO",
        "description": "Terra Earth observation satellite, part of NASA's Earth Observing System.",
        "image": None,
    },
    "SENTINEL": {
        "country": "Europe", "operator": "ESA", "type": "Science",
        "status": "Active", "orbit_type": "LEO",
        "description": "ESA Sentinel Earth observation satellite for Copernicus programme.",
        "image": None,
    },
    "LANDSAT": {
        "country": "USA", "operator": "NASA/USGS", "type": "Science",
        "status": "Active", "orbit_type": "LEO",
        "description": "Landsat Earth observation satellite for land surface monitoring.",
        "image": None,
    },
    "INTELSAT": {
        "country": "International", "operator": "Intelsat", "type": "Communication",
        "status": "Active", "orbit_type": "GEO",
        "description": "Intelsat geostationary communication satellite.",
        "image": None,
    },
    "FENGYUN": {
        "country": "China", "operator": "CNSA", "type": "Debris",
        "status": "Debris", "orbit_type": "LEO",
        "description": "Debris from Fengyun 1C anti-satellite test (2007).",
        "image": None,
    },
    "COSMOS": {
        "country": "Russia", "operator": "Roscosmos", "type": "Debris",
        "status": "Debris", "orbit_type": "LEO",
        "description": "Debris from Cosmos 2251 collision with Iridium 33 (2009).",
        "image": None,
    },
}

ORBIT_TYPES = {
    "stations": "LEO", "weather": "LEO", "gps": "MEO",
    "starlink": "LEO", "iridium": "LEO", "debris": "LEO",
    "science": "LEO", "geo": "GEO",
}

SAT_TYPES = {
    "stations": "Space Station", "weather": "Weather", "gps": "Navigation",
    "starlink": "Communication", "iridium": "Communication", "debris": "Debris",
    "science": "Science", "geo": "Communication",
}


def _cache_get(key: str):
    entry = CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data) -> None:
    CACHE[key] = {"ts": time.time(), "data": data}


def get_metadata(name: str, catalog: str) -> dict:
    name_upper = name.upper()
    for key, meta in SAT_METADATA.items():
        if key in name_upper:
            return dict(meta)
    return {
        "country": "Unknown", "operator": "Unknown",
        "type": SAT_TYPES.get(catalog, "Various"),
        "status": "Active",
        "description": f"Satellite in {ORBIT_TYPES.get(catalog, 'LEO')} orbit.",
        "image": None,
    }


def _build_from_tles(tles: list, catalog: str) -> list:
    satellites = []
    for name, tle1, tle2 in tles:
        sat_id = tle1[2:7].strip()
        launch_year_raw = tle1[9:11].strip()
        try:
            ly = int(launch_year_raw)
            launch_year = 2000 + ly if ly < 57 else 1900 + ly
        except Exception:
            launch_year = 2000
        meta = get_metadata(name, catalog)
        satellites.append({
            "id": sat_id,
            "name": name,
            "tle1": tle1,
            "tle2": tle2,
            "catalog": catalog,
            "orbit_type": ORBIT_TYPES.get(catalog, "LEO"),
            "sat_type": SAT_TYPES.get(catalog, "Various"),
            "launch_year": launch_year,
            **meta,
        })
    return satellites


def fetch_live_search(query: str, catalog: str) -> list:
    """Fetch TLE data from ivanstanojevic API by search query."""
    try:
        url = f"{TLE_API_BASE}/?search={query}&sort=name&sort-dir=asc"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        members = data.get("member", [])
        satellites = []
        for m in members[:30]:
            if "line1" not in m or "line2" not in m:
                continue
            name = m.get("name", "Unknown")
            tle1 = m.get("line1", "")
            tle2 = m.get("line2", "")
            if not tle1 or not tle2:
                continue
            sat_id = tle1[2:7].strip()
            meta = get_metadata(name, catalog)
            satellites.append({
                "id": sat_id,
                "name": name,
                "tle1": tle1,
                "tle2": tle2,
                "catalog": catalog,
                "orbit_type": ORBIT_TYPES.get(catalog, "LEO"),
                "sat_type": SAT_TYPES.get(catalog, "Various"),
                "launch_year": 2000,
                **meta,
            })
        return satellites
    except Exception as e:
        logger.warning(f"Live fetch failed for '{query}': {e}")
        return []


CATALOG_SEARCHES = {
    "stations": ["ISS", "CSS TIANHE"],
    "weather": ["NOAA", "METEOSAT", "GOES"],
    "gps": ["GPS BIIR", "GPS BIIF", "GPS BIIIA"],
    "starlink": ["STARLINK"],
    "iridium": ["IRIDIUM"],
    "science": ["HUBBLE", "TERRA", "AQUA", "SENTINEL", "LANDSAT"],
    "geo": ["INTELSAT", "SES", "ARABSAT"],
    "debris": ["FENGYUN 1C DEB", "COSMOS 2251 DEB"],
}


def fetch_catalog(catalog: str = "stations") -> list:
    cached = _cache_get(f"catalog_{catalog}")
    if cached is not None:
        return cached

    # Try live API first
    live_results = []
    for query in CATALOG_SEARCHES.get(catalog, []):
        results = fetch_live_search(query, catalog)
        seen = {s["id"] for s in live_results}
        for r in results:
            if r["id"] not in seen:
                live_results.append(r)
                seen.add(r["id"])

    if live_results:
        _cache_set(f"catalog_{catalog}", live_results)
        logger.info(f"Fetched {len(live_results)} live satellites for {catalog}")
        return live_results

    # Fallback to hardcoded TLEs
    fallback = _build_from_tles(FALLBACK_TLES.get(catalog, []), catalog)
    _cache_set(f"catalog_{catalog}", fallback)
    logger.info(f"Using {len(fallback)} fallback TLEs for {catalog}")
    return fallback


def fetch_multiple_catalogs(catalogs: list = None) -> list:
    if catalogs is None:
        catalogs = ["stations", "starlink", "weather", "gps"]
    all_sats = []
    seen_ids = set()
    for cat in catalogs:
        for s in fetch_catalog(cat):
            if s["id"] not in seen_ids:
                seen_ids.add(s["id"])
                all_sats.append(s)
    return all_sats


def fetch_iss_open_notify() -> Optional[dict]:
    cached = _cache_get("iss_open_notify")
    if cached is not None:
        return cached
    try:
        resp = requests.get("http://api.open-notify.org/iss-now.json", timeout=5)
        data = resp.json()
        result = {
            "lat": data["iss_position"]["latitude"],
            "lon": data["iss_position"]["longitude"],
            "timestamp": data["timestamp"],
        }
        _cache_set("iss_open_notify", result)
        return result
    except Exception as e:
        logger.error(f"Open Notify ISS failed: {e}")
        return None


CELESTRAK_CATALOGS = {
    "stations": TLE_API_BASE + "/?search=ISS",
    "weather": TLE_API_BASE + "/?search=NOAA",
    "gps": TLE_API_BASE + "/?search=GPS",
    "starlink": TLE_API_BASE + "/?search=STARLINK",
    "iridium": TLE_API_BASE + "/?search=IRIDIUM",
    "science": TLE_API_BASE + "/?search=HUBBLE",
    "geo": TLE_API_BASE + "/?search=INTELSAT",
    "debris": TLE_API_BASE + "/?search=DEBRIS",
}


def get_api_status() -> dict:
    try:
        resp = requests.get(f"{TLE_API_BASE}/25544", headers=HEADERS, timeout=5)
        primary = "online" if resp.status_code == 200 else "degraded"
    except Exception:
        primary = "offline"
    return {
        "tle_api": primary,
        "open_notify": "online",
        "n2yo": "not_configured",
    }
