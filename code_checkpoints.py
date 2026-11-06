"""Retain model-authored source snapshots and restore rejected regressions."""
from pathlib import Path
import zipfile
PREFIXES=('src/Clean.Architecture.Core/','src/Clean.Architecture.UseCases/','src/Clean.Architecture.Infrastructure/','src/Clean.Architecture.Web/')

def snapshot(checkout,destination):
 with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
  for prefix in PREFIXES:
   for p in (checkout/prefix).rglob('*.cs'):
    if not any(x in p.parts for x in ('obj','bin')):z.write(p,p.relative_to(checkout).as_posix())

def restore(checkout,archive,except_paths=()):
 root=checkout.resolve();keep=set(except_paths)
 with zipfile.ZipFile(archive) as z:
  names=set(z.namelist())
  for prefix in PREFIXES:
   for p in (root/prefix).rglob('*.cs'):
    if any(x in p.parts for x in ('obj','bin')):continue
    relative=p.relative_to(root).as_posix()
    if relative not in names and relative not in keep:
     if root not in p.resolve().parents:raise ValueError('Out-of-fixture path')
     p.unlink()
  for relative in names:
   if relative in keep:continue
   target=(root/relative).resolve()
   if root not in target.parents:raise ValueError('Out-of-fixture path')
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(relative))
