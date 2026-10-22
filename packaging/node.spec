# Build on the target operating system in an isolated build environment.
from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis([str(root / 'src/main.py')], pathex=[str(root / 'src')],
             binaries=[], datas=[(str(root / 'src/tunnel/web'), 'tunnel/web'),
                                 (str(root / 'PROTOCOL_STANDARD.md'), '.')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter', 'unittest', 'pytest', 'PySide6', 'numpy', 'IPython'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='buggcraft-node',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='buggcraft-node')
