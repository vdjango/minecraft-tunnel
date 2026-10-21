"""Run four isolated native node processes on loopback; Ctrl+C stops all four."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import sys

from aiohttp import ClientSession, Fingerprint

from init_node import initialize
from cryptography import x509
from cryptography.hazmat.primitives import hashes

ROOT = Path(__file__).resolve().parents[1]


async def run(args):
    base = Path(args.directory).resolve()
    ports = [args.ssh_port + i for i in range(4)] + [args.web_port + i for i in range(4)]
    if len(set(ports)) != 8 or any(not 1024 <= p <= 65535 for p in ports):
        raise ValueError('Eight distinct unprivileged ports are required')
    reservations = []
    try:
        for port in ports:
            sock = socket.socket()
            sock.bind(('127.0.0.1', port))
            reservations.append(sock)
    finally:
        for sock in reservations:
            sock.close()
    configs = []
    for index, label in enumerate('ABCD'):
        directory = base / label
        if not (directory / 'server.conf').exists():
            initialize(directory, '127.0.0.1', args.ssh_port + index,
                       name='本地测试节点 ' + label, web_port=args.web_port + index)
            config = directory / 'server.conf'
            config.write_text(config.read_text(encoding='utf-8').replace('0.0.0.0', '127.0.0.1'),
                              encoding='utf-8')
        config = directory / 'server.conf'
        # Refuse to accidentally expose reused local configurations on the LAN.
        import configparser
        settings = configparser.ConfigParser()
        settings.read(config, encoding='utf-8')
        if any(settings[section].get('host') != '127.0.0.1' for section in ('relay', 'web')):
            raise ValueError('Local cluster configuration must bind loopback only')
        if settings['relay'].getint('port') != args.ssh_port + index or settings['web'].getint('port') != args.web_port + index:
            raise ValueError('Existing cluster ports differ; use another --directory')
        configs.append(directory)
    processes, logs = [], []
    stopped = asyncio.Event()
    if os.name != 'nt':
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    try:
        for directory in configs:
            log = (directory / 'node.log').open('ab')
            logs.append(log)
            processes.append(await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / 'src/main.py'), '--config', str(directory / 'server.conf'),
                cwd=str(ROOT), stdout=log, stderr=log))
        async with ClientSession() as session:
            fingerprints = [Fingerprint(x509.load_pem_x509_certificate(
                (d / 'web-cert.pem').read_bytes()).fingerprint(hashes.SHA256())) for d in configs]
            async def request(index, path, data=None, csrf=''):
                url = f'https://127.0.0.1:{args.web_port + index}' + path
                async with session.request('GET' if data is None else 'POST', url, json=data,
                    headers={'X-CSRF-Token': csrf}, ssl=fingerprints[index]) as response:
                    if response.status != 200:
                        raise RuntimeError(f'Node {"ABCD"[index]} {path}: HTTP {response.status}')
                    return await response.json()
            async with asyncio.timeout(20):
                for i in range(4):
                    while True:
                        if processes[i].returncode is not None:
                            raise RuntimeError('Node failed to start; inspect node.log')
                        try:
                            await request(i, '/api/status')
                            break
                        except (OSError, TimeoutError):
                            await asyncio.sleep(.2)
            # Use the same password/CSRF-protected APIs used by the browser.
            # A token is passed explicitly per request because cookies share a
            # hostname across ports; each node has its own session namespace.
            tokens, cookies = [], []
            for i, directory in enumerate(configs):
                credentials = (directory / 'admin-credentials.txt').read_text(encoding='utf-8')
                password = next(line.split(': ', 1)[1] for line in credentials.splitlines()
                                if line.startswith('Admin password: '))
                async with session.post(f'https://127.0.0.1:{args.web_port + i}/api/login',
                    json={'username': 'admin', 'password': password}, ssl=fingerprints[i]) as response:
                    if response.status != 200:
                        raise RuntimeError('Local administrator login failed')
                    tokens.append((await response.json())['csrf'])
                    cookies.append(response.cookies['node_session'].value)
            async def admin(index, path, data=None):
                async with session.request('GET' if data is None else 'POST',
                    f'https://127.0.0.1:{args.web_port + index}' + path, json=data,
                    headers={'X-CSRF-Token': tokens[index], 'Cookie': 'node_session=' + cookies[index]},
                    ssl=fingerprints[index]) as response:
                    if response.status != 200:
                        raise RuntimeError(f'Admin API {path}: HTTP {response.status}')
                    return await response.json()
            a = await admin(0, '/api/federation/invite')
            await admin(1, '/api/federation/join', a)
            b = await admin(1, '/api/federation/invite')
            await admin(0, '/api/federation/join', b)
            await admin(2, '/api/federation/join', b)
            c = await admin(2, '/api/federation/invite')
            await admin(1, '/api/federation/join', c)
            await admin(3, '/api/federation/join', b)
            async with asyncio.timeout(30):
                while True:
                    states = await asyncio.gather(*(request(i, '/api/status') for i in range(4)))
                    if all(s['network_nodes'] == 4 for s in states):
                        break
                    await asyncio.sleep(.5)
            for index, label in enumerate('ABCD'):
                print(f'{label}: https://127.0.0.1:{args.web_port + index}/  SSH {args.ssh_port + index}', flush=True)
            print('PASS: Four separate processes discovered all four nodes using the administrator APIs.', flush=True)
            print('Private credentials: ' + str(base / '[A-D]' / 'admin-credentials.txt'), flush=True)
            if args.seconds:
                try:
                    await asyncio.wait_for(stopped.wait(), args.seconds)
                except TimeoutError:
                    pass
            else:
                await stopped.wait()
    finally:
        for process in processes:
            if process.returncode is None:
                process.terminate()
        await asyncio.gather(*(p.wait() for p in processes), return_exceptions=True)
        for log in logs:
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default=str(ROOT / 'config/local-cluster'))
    parser.add_argument('--ssh-port', type=int, default=34331)
    parser.add_argument('--web-port', type=int, default=18443)
    parser.add_argument('--seconds', type=int, default=0, help='Stop automatically after this many seconds')
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
