"""Refresh the portable workbench snapshot from its sibling source project."""
import argparse
import hashlib
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=(root/'workbench' if (root/'workbench/sandbox/app.py').exists() else root.parent/'tgap-sandbox'))
args=parser.parse_args()
source=args.source.resolve()
target=root/'tgap_cli'/'data'/'sandbox.zip'
target.parent.mkdir(parents=True,exist_ok=True)
files=[]
for folder in ('sandbox','static','fixtures','publication'):
    files.extend(p for p in (source/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
files.append(source/'requirements.txt')
if (source/'README.md').exists():files.append(source/'README.md')
if (source/'STUDY_PROTOCOL.md').exists():files.append(source/'STUDY_PROTOCOL.md')
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for path in sorted(files):
        info=zipfile.ZipInfo(path.relative_to(source).as_posix(),date_time=(2026,10,7,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info,path.read_bytes())
target.with_suffix('.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'\n',encoding='utf-8')
print('Bundled',len(files),'files;',target.stat().st_size,'bytes. No users, sessions, logs, or study records included.')
