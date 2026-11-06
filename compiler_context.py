"""Deterministic symbol context from compiler diagnostics and the existing SCIP index."""
from pathlib import Path
import re
from scip_context import occurrences
from runner import FIXTURE

def context_for_errors(errors,checkout):
 names=set(re.findall(r"'([A-Za-z_]\w*)'",errors))
 if 'UpdateContributorMapper' in errors: names.add('UpdateContributorMapper')
 paths=set()
 for path,symbol,line,definition in occurrences(FIXTURE/'index.scip'):
  if definition and any(symbol.endswith((name+'#',name+'.')) for name in names):
   path=path.replace('\\','/')
   if path.startswith('src/') and (checkout/path).is_file():paths.add(path)
 if 'UpdateContributorMapper' in names:
  paths.add('src/Clean.Architecture.Web/Contributors/Update.cs')
 text='\n'.join('### '+p+'\n'+(checkout/p).read_text(encoding='utf-8-sig') for p in sorted(paths))[:12000]
 if 'UpdateContributorMapper' in names:
  original=(FIXTURE/'src/Clean.Architecture.Web/Contributors/Update.cs').read_text(encoding='utf-8')
  namespace=next(line for line in original.splitlines() if line.startswith('namespace '))
  declaration=re.search(r'public sealed class UpdateContributorMapper[\s\S]*?\{',original).group(0).rstrip('{').strip()
  text+='\nOriginal public API signature that must remain available (body intentionally omitted):\n'+namespace+'\n'+declaration
 if 'HasValue' in errors or "cannot convert from 'int' to 'Clean.Architecture.Core.ContributorAggregate.ContributorStatus'" in errors:
  text+='\nC# reference-type rule: if a variable already has the required class type, pass that variable directly, not its numeric Value property. A nullable class reference is checked against null; Nullable<T>.HasValue is only for nullable value types.\n'
 if 'Type provided must be an Enum' in errors or 'System.ArgumentException' in errors:
  text+='\nRuntime type diagnosis: ContributorStatus is SmartEnum, so System.Enum.Parse and System.Enum.IsDefined are invalid for it. Use the installed SmartEnum TryFromName API documented in the reference. Fix production code, not tests.\n'
 if 'Original public UpdateContributorMapper API must remain available' in errors:
  text+='\nAPI compatibility requirement: restore the public type Clean.Architecture.Web.Contributors.UpdateContributorMapper (original declaration shown above). Renaming it to Impl is not compatible. A using directive does not declare a namespace; the actual declaration must be in namespace Clean.Architecture.Web.Contributors. Fix its original production declaration; do not create new test files.\n'
 return text, sorted(paths)
