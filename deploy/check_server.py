"""Repeatable server regression checks, including real four-node SSH replication."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only', action='store_true', help='Run standalone server tests only')
    parser.add_argument('--launcher', type=Path, default=ROOT.parent / 'buggcraft',
                        help='Launcher checkout used for protocol and HTTP integration tests')
    args = parser.parse_args()
    launcher = args.launcher.resolve()
    if not args.native_only and not (launcher / 'tests/test_node_accounts.py').is_file():
        parser.error('Launcher integration tests are missing; provide --launcher or use --native-only')
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(ROOT / 'src'),
        str(launcher / 'src/buggcraft'), env.get('PYTHONPATH', '')]))
    subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover',
                    '-s', 'tests', '-p', 'test_*.py', '-v'], cwd=ROOT, env=env, check=True)
    if not args.native_only:
        subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', '-v',
            'tests.test_node_accounts', 'tests.test_node_portal', 'tests.test_node_federation',
            'tests.test_room_chat', 'tests.test_room_lifecycle', 'tests.test_game_status',
            'tests.test_peer_transport', 'tests.test_bridge_protocol'], cwd=launcher, env=env, check=True)
    print('PASS: all selected server regression suites passed.', flush=True)


if __name__ == '__main__':
    main()
