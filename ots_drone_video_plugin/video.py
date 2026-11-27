"""The video marker (CoT) and the questions asked of MediaMTX and gpsd.

No Flask or OpenTAKServer imports here, so it can be tested on its own.
"""
import json
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape, quoteattr

UNKNOWN = 9999999.0  # CoT value for "not known"


def stream_ready(api_address, path):
    """True when MediaMTX is receiving the stream right now."""
    url = f"{api_address.rstrip('/')}/v3/paths/get/{urllib.parse.quote(path)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return bool(json.load(resp).get("ready"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # nobody has published on that path
            return False
        raise


def local_address():
    """The address the clients reach this server on: the one of the default route."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # no packet is sent; this only picks the interface
        return s.getsockname()[0]
    finally:
        s.close()


def parse_position(text):
    """ "lat,lon" to two floats, or None."""
    try:
        lat, lon = (float(p) for p in str(text).split(","))
    except ValueError:
        return None
    return (lat, lon) if abs(lat) <= 90 and abs(lon) <= 180 else None


def gps_position():
    """The server's own position from gpsd, or None."""
    try:
        out = subprocess.run(["gpspipe", "-w", "-n", "12"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("class") == "TPV" and msg.get("mode", 0) >= 2 and "lat" in msg and "lon" in msg:
            return msg["lat"], msg["lon"]
    return None


def make_cot(path, name, position, address, port, query, stale_s):
    """A sensor marker that carries the video stream.

    ATAK shows it as a camera on the map and adds the stream to its video list.
    `query` is appended to the stream's path, e.g. "token=..." to let the
    clients read without logging in.
    """
    lat, lon = position
    uid = f"DRONE-VIDEO-{path}"
    full_path = "/" + path + (f"?{query}" if query else "")
    url = f"rtsp://{address}:{port}{full_path}"
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (
        f'<event version="2.0" uid={quoteattr(uid)} type="b-m-p-s-p-loc" how="m-g" '
        f'time="{now.strftime(fmt)}" start="{now.strftime(fmt)}" '
        f'stale="{(now + timedelta(seconds=stale_s)).strftime(fmt)}">'
        f'<point lat="{lat:.6f}" lon="{lon:.6f}" hae="{UNKNOWN}" ce="{UNKNOWN}" le="{UNKNOWN}"/>'
        f"<detail><contact callsign={quoteattr(name)}/>"
        # The camera's direction is not known, so no field of view is drawn.
        '<sensor azimuth="0" fov="45" range="100" hideFov="true"/>'
        f"<__video uid={quoteattr(uid)} url={quoteattr(url)}>"
        f"<ConnectionEntry uid={quoteattr(uid)} alias={quoteattr(name)} protocol=\"rtsp\" "
        f'address={quoteattr(address)} port="{port}" path={quoteattr(full_path)} '
        'networkTimeout="12000" bufferTime="-1" roverPort="-1" rtspReliable="1" ignoreEmbeddedKLV="false"/>'
        "</__video>"
        f"<remarks>{escape(f'Video: {name}. The marker shows where the server is, not the drone.')}</remarks>"
        "</detail></event>"
    )
