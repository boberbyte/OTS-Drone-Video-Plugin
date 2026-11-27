# OTS-Drone-Video-Plugin

A plugin for [OpenTAKServer](https://github.com/brian7704/OpenTAKServer) that puts a
drone's live video on the TAK map. While the drone is streaming to the server, the
connected TAK clients get a camera marker that opens the video.

OpenTAKServer already receives video with its built-in MediaMTX. What this plugin
adds is the marker: nobody has to type an address into their client, and the marker
disappears when the stream ends or the plugin is switched off.

> Status: first version. Tested on OpenTAKServer 1.8.3 on Linux (Raspberry Pi CM5)
> with a DJI Neo streaming RTMP from DJI Fly, and ATAK and iTAK as clients: the
> marker shows up and the video plays.

## What it does

- Turn the plugin on and off under **Plugins** in the OpenTAKServer dashboard.
- Every ten seconds it asks MediaMTX whether the stream is live. Only then is the
  marker sent.
- The marker is placed where the server is (from gpsd), not where the drone is: an
  RTMP stream carries no position.
- The marker is sent straight to the clients. It is not stored in the database and
  is not forwarded to Meshtastic/LoRa.
- Switching the plugin off removes the marker. It does not stop the server from
  receiving the video.

## Sending the drone's video to the server

Any app that can stream RTMP works, for example DJI Fly's live streaming with a
custom address, or a screen streaming app on the phone or tablet that shows the
drone's picture. The address is:

```
rtmp://SERVER:1935/neo?user=USER&pass=PASSWORD
```

`USER` and `PASSWORD` are an OpenTAKServer account. Make a separate account for the
drone: RTMP is not encrypted, so the password crosses the network in clear text.
`neo` is the stream name and must match the `STREAM_PATH` setting.

## Installation

Install into the same Python environment as OpenTAKServer, then restart the server:

```
~/.opentakserver_venv/bin/pip install git+https://github.com/boberbyte/OTS-Drone-Video-Plugin.git
sudo systemctl restart opentakserver
```

## Settings

All names start with `OTS_DRONE_VIDEO_PLUGIN_`. They are changed under the plugin's
**Config** tab in the dashboard, except the one marked "server only".

| Setting | Default | Meaning |
|---|---|---|
| `STREAM_PATH` | `neo` | Stream name the drone publishes on |
| `NAME` | `Neo` | The marker's name on the map |
| `ADDRESS` | empty | Server address the clients use for the video. Empty = the server's current address |
| `RTSP_PORT` | `8554` | MediaMTX's RTSP port |
| `POSITION` | `gps` | `gps` = the server's own position, or a fixed `lat,lon` |
| `FALLBACK_POSITION` | `55.609,13.001` | Used when gps gives no position |
| `INTERVAL_S` | `10` | How often the stream is checked and the marker is sent |
| `GROUP` | `__ANON__` | TAK group that receives the marker |
| `SHARE_TOKEN` | `true` | See below. **Server only** |

## Who can watch

MediaMTX asks OpenTAKServer before it lets anybody read a stream. With
`SHARE_TOKEN: true` the address in the marker carries the server's
`OTS_MEDIAMTX_TOKEN`, so every client that gets the marker can watch without
logging in.

Know what that means: the same token also allows publishing video to the server,
and it is sent to every client in the group. On a server where you do not trust
all clients, set `OTS_DRONE_VIDEO_PLUGIN_SHARE_TOKEN: false` in `~/ots/config.yml`.
The clients must then add their own user name and password to the video address.
The setting cannot be changed from the dashboard.

## Pausing without the dashboard

Create the file `~/.cache/ots-drone-video/paused` to pause, remove it to resume.
The current state is written to `~/.cache/ots-drone-video/status.json`:
`waiting` (on, no stream), `streaming`, `paused`, `disabled` or `error`.

## License

GPL-3.0-or-later. See `LICENSE`.
