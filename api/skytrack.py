"""
SkyTrack Live — Real-time satellite position engine using SGP4 propagation.
Converts ECI coordinates to geodetic lat/lon/alt.
"""
import math
import time
import logging
from datetime import datetime, timezone
from sgp4.api import Satrec, jday

logger = logging.getLogger(__name__)


def eci_to_geodetic(x: float, y: float, z: float, jd: float, jf: float) -> tuple:
    """Convert ECI (km) to geodetic lat/lon/alt."""
    # Earth constants
    a = 6378.137  # km equatorial radius
    f = 1 / 298.257223563
    b = a * (1 - f)
    e2 = 1 - (b / a) ** 2

    # GMST (Greenwich Mean Sidereal Time)
    t = (jd + jf - 2451545.0) / 36525.0
    gmst = (280.46061837 + 360.98564736629 * (jd + jf - 2451545.0)
            + 0.000387933 * t ** 2 - t ** 3 / 38710000.0) % 360.0
    gmst_rad = math.radians(gmst)

    # ECEF coordinates
    x_ecef = x * math.cos(gmst_rad) + y * math.sin(gmst_rad)
    y_ecef = -x * math.sin(gmst_rad) + y * math.cos(gmst_rad)
    z_ecef = z

    # Geodetic conversion (Bowring iterative method)
    lon = math.degrees(math.atan2(y_ecef, x_ecef))
    p = math.sqrt(x_ecef ** 2 + y_ecef ** 2)
    lat = math.atan2(z_ecef, p * (1 - e2))
    for _ in range(5):
        sin_lat = math.sin(lat)
        N = a / math.sqrt(1 - e2 * sin_lat ** 2)
        lat = math.atan2(z_ecef + e2 * N * sin_lat, p)
    sin_lat = math.sin(lat)
    N = a / math.sqrt(1 - e2 * sin_lat ** 2)
    alt = p / math.cos(lat) - N if abs(lat) < math.pi / 4 else z_ecef / math.sin(lat) - N * (1 - e2)
    return math.degrees(lat), lon, alt


def compute_position(tle1: str, tle2: str, dt: datetime = None) -> dict:
    """Compute satellite position at given datetime."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    try:
        satellite = Satrec.twoline2rv(tle1, tle2)
        jd, jf = jday(dt.year, dt.month, dt.day,
                       dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)
        e, r, v = satellite.sgp4(jd, jf)
        if e != 0:
            return None
        lat, lon, alt = eci_to_geodetic(r[0], r[1], r[2], jd, jf)
        speed = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)  # km/s
        return {
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "alt": round(alt, 2),
            "speed_kms": round(speed, 3),
            "speed_kmh": round(speed * 3600, 1),
            "speed_mph": round(speed * 3600 * 0.621371, 1),
            "x": round(r[0], 2),
            "y": round(r[1], 2),
            "z": round(r[2], 2),
            "timestamp": dt.isoformat(),
        }
    except Exception as e:
        logger.error(f"SGP4 error: {e}")
        return None


def compute_orbit_path(tle1: str, tle2: str, num_points: int = 90) -> list:
    """Compute orbit path as a list of lat/lon points (one full orbit approx)."""
    try:
        satellite = Satrec.twoline2rv(tle1, tle2)
        # Approximate period from mean motion (rev/day on line 2)
        mean_motion = float(tle2[52:63].strip())  # rev/day
        period_minutes = 1440.0 / mean_motion if mean_motion > 0 else 90.0
        now = datetime.now(timezone.utc)
        points = []
        for i in range(num_points):
            minutes_offset = (i / num_points) * period_minutes
            dt = datetime(now.year, now.month, now.day,
                          now.hour, now.minute, now.second, tzinfo=timezone.utc)
            total_seconds = minutes_offset * 60
            import datetime as dt_module
            dt_offset = dt + dt_module.timedelta(seconds=total_seconds)
            jd, jf = jday(dt_offset.year, dt_offset.month, dt_offset.day,
                          dt_offset.hour, dt_offset.minute,
                          dt_offset.second + dt_offset.microsecond / 1e6)
            e, r, v = satellite.sgp4(jd, jf)
            if e == 0:
                lat, lon, alt = eci_to_geodetic(r[0], r[1], r[2], jd, jf)
                points.append({"lat": round(lat, 3), "lon": round(lon, 3), "alt": round(alt, 1)})
        return points
    except Exception as e:
        logger.error(f"Orbit path error: {e}")
        return []


def compute_future_path(tle1: str, tle2: str, minutes_ahead: int = 90, num_points: int = 45) -> list:
    """Compute predicted future orbit path."""
    try:
        satellite = Satrec.twoline2rv(tle1, tle2)
        import datetime as dt_module
        now = datetime.now(timezone.utc)
        points = []
        for i in range(num_points):
            minutes_offset = (i / num_points) * minutes_ahead
            dt_offset = now + dt_module.timedelta(minutes=minutes_offset)
            jd, jf = jday(dt_offset.year, dt_offset.month, dt_offset.day,
                          dt_offset.hour, dt_offset.minute,
                          dt_offset.second + dt_offset.microsecond / 1e6)
            e, r, v = satellite.sgp4(jd, jf)
            if e == 0:
                lat, lon, alt = eci_to_geodetic(r[0], r[1], r[2], jd, jf)
                points.append({"lat": round(lat, 3), "lon": round(lon, 3), "alt": round(alt, 1),
                                "minutes_from_now": round(minutes_offset, 1)})
        return points
    except Exception as e:
        logger.error(f"Future path error: {e}")
        return []


def batch_compute_positions(satellites: list, dt: datetime = None) -> list:
    """Compute current positions for a batch of satellites."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    results = []
    for sat in satellites:
        pos = compute_position(sat["tle1"], sat["tle2"], dt)
        if pos:
            sat_data = {k: v for k, v in sat.items() if k not in ("tle1", "tle2")}
            sat_data.update(pos)
            results.append(sat_data)
    return results
