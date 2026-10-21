"""Production entry point for a native Buggcraft relay node.

Run with ``python src/main.py --config path/to/server.conf``.
"""
import argparse
import asyncio
import configparser
import json
import logging
import os
from pathlib import Path
import signal
import ssl

import asyncssh

from tunnel.relay import RelayServer


async def run(config_path):
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(config_path, encoding="utf-8"):
        raise SystemExit("Relay configuration file missing")
    settings = config["relay"]
    base = Path(config_path).resolve().parent
    token = (base / settings["token_file"]).read_text(encoding="utf-8").strip()
    relay = RelayServer(
        settings.get("host", "0.0.0.0"), settings.getint("port", 3333),
        host_key=str(base / settings["host_key"]), token=token,
        max_connections=settings.getint("max_connections", 512),
        max_rooms=settings.getint("max_rooms", 128),
        max_streams=settings.getint("max_streams_per_room", 128),
        max_total_streams=settings.getint("max_total_streams", 512),
        max_client_streams=settings.getint("max_streams_per_client", 8),
    )
    portal = federation = None
    if config.has_section("web"):
        from tunnel.federation import Federation, identity, validate_profile
        from tunnel.portal import Portal

        web_settings = config["web"]
        state_path = base / web_settings.get("state_file", "node-state.json")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        profile = json.loads((base / web_settings.get(
            "profile_file", "relay-profile.json")).read_text(encoding="utf-8"))
        # Advertise only the configured public entrance; never infer an origin
        # address from the bind socket.
        if settings.get("entry_host"):
            profile["server_host"] = settings["entry_host"]
        if settings.get("entry_port"):
            profile["server_port"] = settings.getint("entry_port")
        federation = Federation(
            asyncssh.read_private_key(str(base / settings["host_key"])), profile,
            network_key=state["network_key"], name=state["name"],
            blocked=state.get("blocked", []),
        )
        seeds = state.get("seeds", [])
        if len(seeds) > 31:
            raise ValueError("Federation is limited to 32 nodes")
        federation.seeds = {
            identity(item["server_public_key"]): validate_profile(item) for item in seeds
        }
        federation.relay = relay
        relay.federation = federation
        portal = Portal(relay, federation, state_path)

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    if os.name != "nt":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopped.set)
    try:
        await relay.start()
        if portal:
            tls = None
            if web_settings.get("tls_cert"):
                tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                tls.minimum_version = ssl.TLSVersion.TLSv1_2
                tls.load_cert_chain(base / web_settings["tls_cert"], base / web_settings["tls_key"])
            await portal.start(web_settings.get("host", "127.0.0.1"),
                               web_settings.getint("port", 18443), tls)
            federation.task = asyncio.create_task(federation.run())
        await stopped.wait()
    finally:
        if portal:
            await portal.close()
        if federation:
            await federation.close()
        await relay.close()


def main():
    parser = argparse.ArgumentParser(description="Run one Buggcraft federation relay node")
    parser.add_argument("--config", default="config/server.conf")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    try:
        asyncio.run(run(args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
