"""Build a deterministic source/bootstrap ZIP; excludes user data and dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.2.0'
PACKAGE = 'pi-gesture-mic'
TOP_LEVEL = (
    'README.md','CHANGELOG.md','requirements.txt','gesture_config.json',
    'gesture_engine.py','gesture_mouse_pi.py','profiles.py','calibration.py',
    'calibration_ui.py','devices.py','setup_ui.py','install_pi.sh','run_pi.sh',
    'setup_autostart.sh','check_microphone.sh','start_kiosk.sh','stop_pi.sh','desktop_input.py',
    'system/70-pi-gesture-mic-uinput.rules','system/pi-gesture-mic-uinput.conf',
)


def source_files(root):
    files = [root/name for name in TOP_LEVEL]
    for folder, pattern in (('docs','*.md'),('tests','test_*.py'),('tools','*.py')):
        files.extend(sorted((root/folder).glob(pattern)))
    for file in files:
        if not file.is_file() or file.is_symlink():
            raise ValueError(f'Missing or symlinked release input: {file}')
    return sorted(files)


def build(output=None, root=ROOT):
    output = Path(output) if output else root/'dist'
    output.mkdir(parents=True,exist_ok=True)
    archive = output/'pi-gesture-mic-pi5-v2.2.zip'
    payload = {str(p.relative_to(root)):p.read_bytes() for p in source_files(root)}
    for name,data in payload.items():
        if name.endswith('.py'):
            compile(data,name,'exec')
    manifest = {'version':VERSION,'files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}}
    payload['MANIFEST.json'] = (json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    tmp=archive.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name,data in sorted(payload.items()):
                entry=zipfile.ZipInfo(PACKAGE+'/'+name,date_time=(2026,11,12,0,0,0))
                entry.create_system=3
                mode=0o755 if name.endswith('.sh') else 0o644
                entry.external_attr=(stat.S_IFREG|mode)<<16
                entry.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(entry,data)
        with zipfile.ZipFile(tmp) as z:
            if z.testzip():
                raise ValueError('ZIP integrity check failed')
            for name,digest in manifest['files'].items():
                if hashlib.sha256(z.read(PACKAGE+'/'+name)).hexdigest()!=digest:
                    raise ValueError(f'Manifest mismatch: {name}')
        tmp.replace(archive)
    finally:
        tmp.unlink(missing_ok=True)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/'SHA256SUMS').write_text(f'{digest}  {archive.name}\n')
    return archive,digest,len(payload)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    archive,digest,count=build(args.output)
    print(f'{archive}\n{count} files | SHA-256 {digest}')
