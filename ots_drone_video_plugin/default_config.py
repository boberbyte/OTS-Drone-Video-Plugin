import os
import re
import traceback

import yaml
from flask import current_app as app
from opentakserver.extensions import logger

P = "OTS_DRONE_VIDEO_PLUGIN_"

# Sending the server's video token to the clients is a security decision. It
# can only be changed by editing config.yml on the server itself.
LOCKED = (P + "SHARE_TOKEN",)
MAY_BE_EMPTY = (P + "ADDRESS",)


class DefaultConfig:
    # Loaded first; values in ~/ots/config.yml take precedence.
    OTS_DRONE_VIDEO_PLUGIN_STREAM_PATH = "neo"  # the stream name the drone publishes on
    OTS_DRONE_VIDEO_PLUGIN_NAME = "Neo"  # the marker's name on the map
    OTS_DRONE_VIDEO_PLUGIN_ADDRESS = ""  # server address the clients use; empty = found automatically
    OTS_DRONE_VIDEO_PLUGIN_RTSP_PORT = 8554
    OTS_DRONE_VIDEO_PLUGIN_POSITION = "gps"  # "gps" = the server's own position, or "lat,lon"
    OTS_DRONE_VIDEO_PLUGIN_FALLBACK_POSITION = "55.609,13.001"  # used when gps gives nothing
    OTS_DRONE_VIDEO_PLUGIN_INTERVAL_S = 10  # how often the stream is checked and the marker is sent
    # True = the marker's address carries OTS_MEDIAMTX_TOKEN, so that clients can
    # watch without typing a user name and password. Everyone who gets the marker
    # can then also publish video to the server.
    OTS_DRONE_VIDEO_PLUGIN_SHARE_TOKEN = True
    OTS_DRONE_VIDEO_PLUGIN_CACHE_DIR = "~/.cache/ots-drone-video"
    OTS_DRONE_VIDEO_PLUGIN_GROUP = "__ANON__"

    @staticmethod
    def keys():
        return [k for k in vars(DefaultConfig) if k.startswith(P)]

    @staticmethod
    def validate(config: dict) -> dict:
        try:
            for key, value in config.items():
                if key not in DefaultConfig.keys():
                    return {"success": False, "error": f"{key} is not a valid config key"}
                default = getattr(DefaultConfig, key)
                if key in LOCKED and value != app.config.get(key, default):
                    return {"success": False, "error": f"{key} can only be changed in config.yml on the server"}
                if isinstance(default, bool):
                    if not isinstance(value, bool):
                        return {"success": False, "error": f"{key} must be true or false"}
                elif isinstance(default, int):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                        return {"success": False, "error": f"{key} must be a non-negative number"}
                elif not isinstance(value, str) or (not value.strip() and key not in MAY_BE_EMPTY):
                    return {"success": False, "error": f"{key} must be a non-empty string"}
            segment = r"[A-Za-z0-9_-][A-Za-z0-9_.-]*"  # no leading dot, so no ".."
            if not re.fullmatch(f"{segment}(/{segment})*", config.get(P + "STREAM_PATH", "neo")):
                return {"success": False, "error": "STREAM_PATH may only contain letters, digits, _ . - and /"}
            if not re.fullmatch(r"[A-Za-z0-9.:-]*", config.get(P + "ADDRESS", "")):
                return {"success": False, "error": "ADDRESS must be a host name or an IP address"}
            position = r"-?\d+(\.\d+)?,-?\d+(\.\d+)?"
            if not re.fullmatch(r"gps|" + position, config.get(P + "POSITION", "gps")):
                return {"success": False, "error": "POSITION must be gps or lat,lon"}
            if not re.fullmatch(position, config.get(P + "FALLBACK_POSITION", "0,0")):
                return {"success": False, "error": "FALLBACK_POSITION must be lat,lon"}
            if config.get(P + "INTERVAL_S", 10) < 2:
                return {"success": False, "error": "INTERVAL_S must be at least 2"}
            if not 1 <= config.get(P + "RTSP_PORT", 8554) <= 65535:
                return {"success": False, "error": "RTSP_PORT must be between 1 and 65535"}
            return {"success": True, "error": ""}
        except BaseException as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def update_config(config: dict) -> dict:
        try:
            valid = DefaultConfig.validate(config)
            if not valid["success"]:
                return valid
            path = os.path.join(app.config.get("OTS_DATA_FOLDER"), "config.yml")
            with open(path) as fh:
                on_disk = yaml.safe_load(fh.read())
            for key, value in config.items():
                app.config.update({key: value})
                on_disk[key] = value
            with open(path + ".tmp", "w") as fh:
                yaml.safe_dump(on_disk, fh)
            os.chmod(path + ".tmp", os.stat(path).st_mode & 0o777)
            os.replace(path + ".tmp", path)
            return {"success": True}
        except BaseException as e:
            logger.error(f"Failed to update config: {e}")
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
