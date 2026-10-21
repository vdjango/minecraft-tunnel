"""Exercise a running local_cluster.py with real launcher SDKs and game bytes."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'buggcraft/src/buggcraft'))
from hookup.relay import RelayProfile, TunnelHost, TunnelClient
from hookup.rooms import list_rooms


async def run(args):
    started = time.perf_counter()
    profiles = [RelayProfile.load(Path(args.directory) / label / 'relay-profile.json') for label in 'ABCD']
    endpoints, tasks, errors, chats = [], [], [], {}
    async def echo(reader, writer):
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
        except ConnectionError:
            pass  # Game status probes may close after rejecting the echo data.
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
    world = await asyncio.start_server(echo, '127.0.0.1', 0)
    game_port = world.sockets[0].getsockname()[1]
    async def start(cls, profile, invite=None):
        ready = asyncio.Event()
        def status(state, detail):
            if state == 'online':
                ready.set()
            elif state == 'error':
                errors.append(detail)
        endpoint = cls(profile, invite, game_port=game_port, listen_port=0, announce=False,
                       on_status=status, room_settings={'title': 'Multi-node verification',
                           'public': True, 'capacity': 32, 'game': {}} if cls is TunnelHost else None)
        messages = []
        endpoint.on_chat = messages.append
        chats[endpoint] = messages
        endpoints.append(endpoint)
        tasks.append(asyncio.create_task(endpoint.run()))
        await asyncio.wait_for(ready.wait(), 20)
        return endpoint
    try:
        hosts = await asyncio.gather(*(start(TunnelHost, p) for p in profiles))
        ids = {h.invite.room_id for h in hosts}
        async with asyncio.timeout(20):
            while True:
                listings = await asyncio.gather(*(list_rooms(p) for p in profiles))
                if all(ids <= {r['id'] for r in listing['rooms']} for listing in listings):
                    break
                await asyncio.sleep(.25)
        clients = await asyncio.gather(*(start(TunnelClient, profiles[(i + 1 + j % 3) % 4], host.invite)
                                         for i, host in enumerate(hosts) for j in range(args.clients)))
        async def transfer(index, client):
            reader, writer = await asyncio.open_connection('127.0.0.1', client.listen_port)
            try:
                payload = secrets.token_bytes(args.bytes)
                writer.write(payload)
                await writer.drain()
                result = await asyncio.wait_for(reader.readexactly(len(payload)), 20)
                if hashlib.sha256(result).digest() != hashlib.sha256(payload).digest():
                    raise AssertionError('Payload corruption')
                assert client._active_profile == profiles[index // args.clients], 'Wrong room owner'
            finally:
                writer.close()
                await writer.wait_closed()
        await asyncio.gather(*(transfer(i, client) for i, client in enumerate(clients)))
        # A unique message reaches the host and exactly its own room participants.
        for i, host in enumerate(hosts):
            message = 'cluster-check-' + str(i) + '-' + secrets.token_hex(8)
            await clients[i * args.clients].send_chat(message)
            async with asyncio.timeout(8):
                while not any(e.get('text') == message for e in chats[host]):
                    await asyncio.sleep(.025)
            assert not any(e.get('text') == message for other in hosts if other is not host for e in chats[other])
        assert not errors, errors
        report = {'passed': True, 'node_processes': 4, 'rooms': len(hosts),
                  'launcher_clients': len(clients), 'payload_bytes_per_client': args.bytes,
                  'verified_roundtrip_bytes': len(clients) * args.bytes * 2,
                  'seconds': round(time.perf_counter() - started, 2),
                  'checks': ['all-entry discovery', 'owner-only relay', 'SHA256 payload integrity',
                             'cross-entry room chat', 'room isolation']}
        print(json.dumps(report, indent=2))
        if args.report:
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
    finally:
        await asyncio.gather(*(e.stop() for e in endpoints), return_exceptions=True)
        await asyncio.gather(*tasks, return_exceptions=True)
        world.close()
        await world.wait_closed()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default=str(ROOT / 'config/local-cluster'))
    parser.add_argument('--clients', type=int, default=5, help='Clients per room')
    parser.add_argument('--bytes', type=int, default=1024 * 1024)
    parser.add_argument('--report')
    args = parser.parse_args()
    if not 1 <= args.clients <= 20 or not 1 <= args.bytes <= 16 * 1024 * 1024:
        parser.error('Use 1–20 clients per room and at most 16 MiB per client')
    asyncio.run(run(args))
