from pathlib import Path
import sys
from multi_bench import HIDDEN, WEBTEST
from multi_endpoint_checks import EXTRA
from multi_database_checks import EXTRA as DBEXTRA
from coding_bench import command, PROJECT
import datetime
stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
root=Path(sys.argv[1]).resolve()
project=root/PROJECT
original=project.read_text(encoding='utf-8')
tests=root/'tests/Clean.Architecture.UnitTests/Core/ContributorAggregate'
files={'BenchMultiStatus.cs':HIDDEN,'BenchWebStatus.cs':WEBTEST,'BenchEndpointPropagation.cs':EXTRA,'BenchStatusPersistence.cs':DBEXTRA}
try:
    project.write_text(original.replace('<PackageReference Include="Mediator.SourceGenerator" />','').replace('</Project>','<ItemGroup><ProjectReference Include="../../src/Clean.Architecture.Web/Clean.Architecture.Web.csproj" /></ItemGroup></Project>'),encoding='utf-8')
    for name,text in files.items():
        (tests/name).write_text(text,encoding='utf-8')
    print(command(['dotnet','test',PROJECT,'--verbosity','quiet','--logger','trx;LogFileName=audit.trx','--results-directory',str(root.parent/('audit-results-'+stamp))],root,root.parent/('evaluator-audit-'+stamp+'.log')))
finally:
    project.write_text(original,encoding='utf-8')
    for name in files:
        (tests/name).unlink(missing_ok=True)
