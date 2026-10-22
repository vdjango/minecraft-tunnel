"""Maintainer build: native runtime, notices, source snapshot and SHA256 hashes."""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent


def main():
    if platform.machine().lower() not in ('amd64', 'x86_64') or sys.maxsize <= 2**32:
        raise SystemExit('This release configuration supports x64 builds only.')
    if sys.platform not in ('win32', 'linux'):
        raise SystemExit('Build on Windows or glibc Linux for the matching target.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(ROOT / 'packaging/node.spec')], cwd=ROOT, check=True)
    bundle = ROOT / 'dist/buggcraft-node'
    for name in ('LICENSE', 'COMMUNITY_LICENSE.md', 'PROTOCOL_STANDARD.md'):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copy2(ROOT / 'packaging/README.txt', bundle / 'README.txt')
    notices = bundle / 'licenses'
    notices.mkdir(exist_ok=True)
    packages = {}
    for dist in metadata.distributions():
        name = dist.metadata['Name']
        packages[name] = dist.version
        for item in dist.files or []:
            if any(part.endswith(('.dist-info', '.egg-info')) for part in item.parts) and (
                    'license' in item.name.lower() or 'copying' in item.name.lower() or
                    'notice' in item.name.lower()):
                target = notices / name / str(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dist.locate_file(item), target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.exists():
        python_license = Path(sys.base_prefix) / f'lib/python{sys.version_info.major}.{sys.version_info.minor}/LICENSE.txt'
    if not python_license.exists():
        raise SystemExit('Python LICENSE.txt was not found; do not distribute without it.')
    shutil.copy2(python_license, notices / 'Python-LICENSE.txt')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    (bundle / 'build-info.json').write_text(json.dumps(dict(
        revision=revision, modified=dirty, platform=platform.platform(),
        architecture=platform.machine(), python=platform.python_version(),
        signed=False, packages=packages), ensure_ascii=False, indent=2), encoding='utf-8')
    with tarfile.open(bundle / 'SOURCE.tar.gz', 'w:gz') as archive:
        for name in ('src', 'tests', 'docs', 'packaging', '.github', 'README.md', 'LICENSE',
                     'COMMUNITY_LICENSE.md', 'PROTOCOL_STANDARD.md', 'requirements.txt',
                     'requirements-test.txt', 'requirements-build.txt', 'build.py', '.gitignore'):
            path = ROOT / name
            def include(info):
                if '__pycache__' in Path(info.name).parts or info.name.endswith(('.pyc', '.log')):
                    return None
                return info
            archive.add(path, arcname=name, filter=include)
    target = 'windows-x64' if sys.platform == 'win32' else 'linux-x64'
    prefix = ROOT / 'dist' / ('buggcraft-node-' + target)
    if sys.platform == 'win32':
        output = Path(shutil.make_archive(str(prefix), 'zip', bundle.parent, bundle.name))
    else:
        output = Path(shutil.make_archive(str(prefix), 'gztar', bundle.parent, bundle.name))
    digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
    output.with_name(output.name + '.sha256').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    print(f'Package: {output}\nSHA256: {digest}', flush=True)


if __name__ == '__main__':
    main()
