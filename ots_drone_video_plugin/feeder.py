"""Puts a video marker on the connected TAK clients' maps while the drone is streaming.

The video itself is received by MediaMTX, which OpenTAKServer already runs.
This plugin only asks MediaMTX whether the stream is live, and tells the
clients where to find it.

The marker is published straight to the exchange "groups" (routing
"<group>.OUT"), the same way the server itself reaches the clients. It does NOT
pass cot_parser: nothing is written to the database and nothing is forwarded to
Meshtastic/LoRa.
"""
import json
import os
import threading
import time

import pika
from opentakserver.extensions import logger

from . import video
from .default_config import P

FEED_UID = "drone-video-feed"
TAG = "DRONE-VIDEO:"
GPS_EVERY_S = 60


class Feeder:
    def __init__(self, app):
        self._app = app
        self._stop = None
        self._thread = None
        self._conn = self._ch = None
        self._state = None
        self._gps = None
        self._gps_time = 0

    # --- on/off (called from the plugin's activate/stop) ---
    def start(self):
        if self._thread and self._thread.is_alive() and self._stop and not self._stop.is_set():
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,), daemon=True, name="drone-video")
        self._thread.start()

    def stop(self):
        if self._stop:
            self._stop.set()
        self._set_state("disabled")

    # --- helpers ---
    def cfg(self, key):
        return self._app.config.get(P + key)

    def _cache_dir(self):
        d = os.path.expanduser(self.cfg("CACHE_DIR"))
        os.makedirs(d, exist_ok=True)
        return d

    def _set_state(self, state, **extra):
        """The state in a small file, so that scripts and status icons can show it."""
        if state == self._state and not extra:
            return
        if state != self._state:
            logger.info(f"{TAG} {state}" + (f" ({extra['error']})" if "error" in extra else ""))
        self._state = state
        try:
            path = os.path.join(self._cache_dir(), "status.json")
            with open(path + ".tmp", "w") as fh:
                json.dump({"state": state, "time": int(time.time()), **extra}, fh)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def _position(self):
        fallback = video.parse_position(self.cfg("FALLBACK_POSITION")) or (0.0, 0.0)
        if self.cfg("POSITION") != "gps":
            return video.parse_position(self.cfg("POSITION")) or fallback
        if time.time() - self._gps_time > GPS_EVERY_S:
            self._gps_time = time.time()
            self._gps = video.gps_position() or self._gps
        return self._gps or fallback

    def _publish(self, cot, ttl_ms):
        if not self._conn or self._conn.is_closed or not self._ch or self._ch.is_closed:
            c = self._app.config
            self._conn = pika.BlockingConnection(
                pika.ConnectionParameters(
                    c.get("OTS_RABBITMQ_SERVER_ADDRESS", "127.0.0.1"),
                    credentials=pika.PlainCredentials(
                        c.get("OTS_RABBITMQ_USERNAME", "guest"), c.get("OTS_RABBITMQ_PASSWORD", "guest")
                    ),
                    heartbeat=0,
                )
            )
            self._ch = self._conn.channel()
        self._ch.basic_publish(
            exchange="groups",
            routing_key=f"{self.cfg('GROUP')}.OUT",
            body=json.dumps({"cot": cot, "uid": FEED_UID}),
            properties=pika.BasicProperties(expiration=str(ttl_ms)),
        )

    def _close(self):
        try:
            if self._conn and self._conn.is_open:
                self._conn.close()
        except Exception:
            pass
        self._conn = self._ch = None

    # --- main loop ---
    def _run(self, stop):
        try:
            self._loop(stop)
        except Exception as exc:
            logger.exception(f"{TAG} the feed stopped: {exc}")
            if not stop.is_set():
                self._set_state("error", error=str(exc)[:200])
        finally:
            self._close()

    def _loop(self, stop):
        pause_flag = os.path.join(self._cache_dir(), "paused")
        while not stop.is_set():
            interval = self.cfg("INTERVAL_S")
            started = time.time()
            if os.path.exists(pause_flag):
                self._close()
                self._set_state("paused")
                stop.wait(interval)
                continue
            path = self.cfg("STREAM_PATH")
            try:
                api = self._app.config.get("OTS_MEDIAMTX_API_ADDRESS", "http://localhost:9997")
                if not video.stream_ready(api, path):
                    self._close()
                    self._set_state("waiting")  # switched on, but the drone is not streaming
                else:
                    address = self.cfg("ADDRESS") or video.local_address()
                    token = self._app.config.get("OTS_MEDIAMTX_TOKEN")
                    query = f"token={token}" if self.cfg("SHARE_TOKEN") and token else ""
                    cot = video.make_cot(
                        path, self.cfg("NAME"), self._position(), address, self.cfg("RTSP_PORT"), query,
                        stale_s=interval * 3,
                    )
                    if stop.is_set():
                        break
                    self._publish(cot, ttl_ms=int(interval * 1000))
                    self._set_state("streaming", path=path, address=address)
            except Exception as exc:
                logger.warning(f"{TAG} {exc}")
                self._close()
                self._set_state("error", error=str(exc)[:200])
            stop.wait(max(1, interval - (time.time() - started)))
