"""Collect installed dependency notices without copying local metadata or paths."""
from pathlib import Path
import importlib.metadata as metadata
import shutil
import sys
import urllib.request

destination = Path('licenses')
destination.mkdir(exist_ok=True)
names = ['PyMuPDF', 'PySide6', 'PySide6-Essentials', 'PySide6-Addons',
         'shiboken6', 'opencv-python-headless', 'numpy', 'Pillow', 'pyinstaller', 'qrcode', 'colorama', 'zxing-cpp']
names += [line.split('==')[0] for line in Path('requirements.txt').read_text().splitlines()
          if line.lower().startswith('winrt')]
for name in names:
    distribution = metadata.distribution(name)
    for entry in distribution.files or []:
        if any(part.lower().startswith(('license', 'licence', 'copying', 'notice'))
               for part in Path(entry).parts):
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                target = destination / name / Path(str(entry).replace('..', '_'))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
for base in (Path(sys.base_prefix), Path(sys.prefix)):
    if (base / 'LICENSE.txt').exists():
        shutil.copyfile(base / 'LICENSE.txt', destination / 'PYTHON-LICENSE.txt')
        break
print('Dependency licence notices collected.')

# Some Windows wheels omit the open-source licence texts. Include upstream copies.
upstream = {
    'LGPL-3.0.txt': 'https://raw.githubusercontent.com/spdx/license-list-data/main/text/LGPL-3.0-only.txt',
    'GPL-3.0.txt': 'https://raw.githubusercontent.com/spdx/license-list-data/main/text/GPL-3.0-only.txt',
    'PYWINRT-LICENSE.txt': 'https://raw.githubusercontent.com/pywinrt/pywinrt/main/LICENSE',
}
for name, url in upstream.items():
    with urllib.request.urlopen(url, timeout=30) as response:
        (destination / name).write_bytes(response.read())
