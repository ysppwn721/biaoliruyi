"""Create the Windows portable archive with maximum standard ZIP compression."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
source = root / 'dist' / 'Zhilian'
target = root / 'artifacts' / 'Zhilian-0.2.1-windows-x64.zip'
target.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in source.rglob('*'):
        if path.is_file():
            archive.write(path, path.relative_to(source.parent))
    # Keep a Chinese-named launcher for users who expect to double-click it.
    archive.write(root / 'packaging' / '启动知链.bat', 'Zhilian/启动知链.bat')
print(f'Created {target} ({target.stat().st_size} bytes)')
