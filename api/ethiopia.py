"""
EthioPass Predictor — Satellite pass predictions over Ethiopia.
Uses Addis Ababa as the reference location.
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from sgp4.api import Satrec, jday

logger = logging.getLogger(__name__)

# Addis Ababa, Ethiopia
ETHIOPIA_LAT = 9.0350
ETHIOPIA_LON = 38.7451
ETHIOPIA_ALT = 2.355  # km above sea level
MIN_ELEVATION = 10.0  # degrees minimum elevation for visibility

EARTH_RADIUS = 6371.0  # km


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> tuple:
    a = 6378.137
    f = 1 / 298.257223563
    e2 = 2 * f - f ** 2
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    N = a / math.sqrt(1 - e2 * sin_lat ** 2)
    x = (N + alt_km) * math.cos(lat) * math.cos(lon)
    y = (N + alt_km) * math.cos(lat) * math.sin(lon)
    z = (N * (1 - e2) + alt_km) * sin_lat
    return x, y, z


def elevation_angle(obs_lat: float, obs_lon: float, obs_alt: float,
                    sat_lat: float, sat_lon: float, sat_alt: float) -> float:
    """Compute elevation angle (degrees) of satellite from observer."""
    obs_x, obs_y, obs_z = geodetic_to_ecef(obs_lat, obs_lon, obs_alt)
    sat_x, sat_y, sat_z = geodetic_to_ecef(sat_lat, sat_lon, sat_alt)
    dx, dy, dz = sat_x - obs_x, sat_y - obs_y, sat_z - obs_z
    range_km = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
    obs_lat_r = math.radians(obs_lat)
    obs_lon_r = math.radians(obs_lon)
    # Local Up unit vector at observer
    ux = math.cos(obs_lat_r) * math.cos(obs_lon_r)
    uy = math.cos(obs_lat_r) * math.sin(obs_lon_r)
    uz = math.sin(obs_lat_r)
    dot = (dx * ux + dy * uy + dz * uz) / range_km
    el = math.degrees(math.asin(max(-1.0, min(1.0, dot))))
    return el


def predict_passes(tle1: str, tle2: str, sat_name: str,
                   hours_ahead: int = 24, step_seconds: int = 60) -> list:
    """Predict upcoming passes over Ethiopia."""
    try:
        satellite = Satrec.twoline2rv(tle1, tle2)
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours_ahead)
        passes = []
        current_pass = None
        dt = now
        while dt < end:
            jd, jf = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                          dt.second + dt.microsecond / 1e6)
            e, r, v = satellite.sgp4(jd, jf)
            if e == 0:
                from api.skytrack import eci_to_geodetic
                lat, lon, alt = eci_to_geodetic(r[0], r[1], r[2], jd, jf)
                el = elevation_angle(ETHIOPIA_LAT, ETHIOPIA_LON, ETHIOPIA_ALT, lat, lon, alt)
                if el >= MIN_ELEVATION:
                    if current_pass is None:
                        current_pass = {
                            "aos": dt.isoformat(),
                            "max_el": el,
                            "max_el_time": dt.isoformat(),
                            "los": None,
                            "sat_name": sat_name,
                            "duration_seconds": 0,
                            "visible": True,
                        }
                    else:
                        if el > current_pass["max_el"]:
                            current_pass["max_el"] = round(el, 1)
                            current_pass["max_el_time"] = dt.isoformat()
                else:
                    if current_pass is not None:
                        current_pass["los"] = dt.isoformat()
                        aos = datetime.fromisoformat(current_pass["aos"])
                        current_pass["duration_seconds"] = int((dt - aos).total_seconds())
                        current_pass["max_el"] = round(current_pass["max_el"], 1)
                        passes.append(current_pass)
                        current_pass = None
                        if len(passes) >= 10:
                            break
            dt += timedelta(seconds=step_seconds)
        return passes
    except Exception as e:
        logger.error(f"Pass prediction error for {sat_name}: {e}")
        return []


def get_ethiopia_passes(satellites: list, hours_ahead: int = 24) -> list:
    """Get passes for a list of satellites (prioritizes ISS)."""
    all_passes = []
    priority = ["ISS (ZARYA)", "ISS", "NOAA", "METEOSAT"]
    satellites_sorted = sorted(
        satellites,
        key=lambda s: 0 if any(p in s["name"].upper() for p in priority) else 1
    )
    for sat in satellites_sorted[:20]:  # limit to prevent timeout
        passes = predict_passes(sat["tle1"], sat["tle2"], sat["name"], hours_ahead)
        all_passes.extend(passes)
    all_passes.sort(key=lambda p: p["aos"])
    return all_passes[:50]
