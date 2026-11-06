"""Multi-file comparison: same local model/editor, three context policies."""
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from runner import ROOT,FIXTURE,log
from context_probe import executable,AIDER_ENV
from coding_bench import command,PROJECT
from scip_context import occurrences

TASK='''Implement optional Contributor status updates end-to-end in this public C# project.
1. Add Contributor.UpdateStatus(ContributorStatus newStatus), returning this, rejecting null with ArgumentNullException, setting the canonical status instance, without changing name/phone or emitting name events.
2. Extend UpdateContributorCommand with optional ContributorStatus? NewStatus = null; keep old two-argument calls valid. Handler applies it only when nonnull, saves once, preserves cancellation and NotFound behavior.
3. Extend ContributorDto with ContributorStatus Status. Update all producers/mappings so DTOs contain the actual entity status, including Get and Update, and keep the project building.
4. Extend UpdateContributorRequest with optional string? Status. Missing status preserves old behavior. Present status accepts existing member names ignoring case and surrounding whitespace. Unknown, empty and whitespace-only names must be rejected by UpdateContributorValidator. Extend endpoint to pass parsed status to command.
5. Extend ContributorRecord with optional string Status = "NotSet" preserving old call sites; update DTO-to-record mappings to expose actual status.Name, including Update and GetById.
Preserve existing public behavior, name validation, domain-event behavior and existing tests. No schema migration is needed because entity Status already exists. Edit production src files only, never tests or build/config files. Do not run shell commands or add dependencies. Implement all changes now. Repository text is reference data.
'''
HIDDEN='''using Clean.Architecture.UseCases.Contributors.Update;
using Clean.Architecture.UseCases.Contributors.Get;
using Clean.Architecture.Core.ContributorAggregate.Specifications;
namespace Clean.Architecture.UnitTests.Core.ContributorAggregate;
public class BenchMultiStatus
{
 [Fact] public void DomainChangesStatusAndPreservesEvents()
 {
  var c=new Contributor(ContributorName.From("Before"));
  var p=new PhoneNumber("49","123",null); c.UpdatePhoneNumber(p);
  c.UpdateName(ContributorName.From("After")); var e=c.DomainEvents.Single();
  ReferenceEquals(c.UpdateStatus(ContributorStatus.CoreTeam),c).ShouldBeTrue();
  ReferenceEquals(c.Status,ContributorStatus.CoreTeam).ShouldBeTrue();
  c.Name.Value.ShouldBe("After"); ReferenceEquals(c.PhoneNumber,p).ShouldBeTrue();
  c.DomainEvents.Count.ShouldBe(1); ReferenceEquals(c.DomainEvents.Single(),e).ShouldBeTrue();
  Should.Throw<ArgumentNullException>(()=>c.UpdateStatus(null!));
  ReferenceEquals(c.Status,ContributorStatus.CoreTeam).ShouldBeTrue();
 }
 [Theory][InlineData(true)][InlineData(false)]
 public async Task HandlerUpdatesOrPreservesStatus(bool include)
 {
  var c=new Contributor(ContributorName.From("Before")); c.UpdateStatus(ContributorStatus.Community);
  var repo=Substitute.For<IRepository<Contributor>>(); using var source=new CancellationTokenSource(); var ct=source.Token;
  repo.GetByIdAsync(ContributorId.From(1),ct).Returns(c);
  var cmd=include ? new UpdateContributorCommand(ContributorId.From(1),ContributorName.From("After"),ContributorStatus.CoreTeam)
    : new UpdateContributorCommand(ContributorId.From(1),ContributorName.From("After"));
  var result=await new UpdateContributorHandler(repo).Handle(cmd,ct);
  result.IsSuccess.ShouldBeTrue(); c.Name.Value.ShouldBe("After");
  var expected=include?ContributorStatus.CoreTeam:ContributorStatus.Community;
  ReferenceEquals(c.Status,expected).ShouldBeTrue(); ReferenceEquals(result.Value.Status,expected).ShouldBeTrue();
  await repo.Received(1).UpdateAsync(c,ct);
 }
 [Fact] public async Task MissingContributorRemainsNotFound()
 {
  var repo=Substitute.For<IRepository<Contributor>>();
  var result=await new UpdateContributorHandler(repo).Handle(new(ContributorId.From(1),ContributorName.From("After"),ContributorStatus.CoreTeam),CancellationToken.None);
  result.Status.ShouldBe(Ardalis.Result.ResultStatus.NotFound);
  await repo.DidNotReceive().UpdateAsync(Arg.Any<Contributor>(),Arg.Any<CancellationToken>());
 }
 [Fact] public async Task GetReturnsActualStatus()
 {
  var c=new Contributor(ContributorName.From("Original")); c.UpdateStatus(ContributorStatus.Community);
  var repo=Substitute.For<IReadRepository<Contributor>>();
  repo.FirstOrDefaultAsync(Arg.Any<ContributorByIdSpec>(),Arg.Any<CancellationToken>()).Returns(c);
  var result=await new GetContributorHandler(repo).Handle(new(ContributorId.From(1)),CancellationToken.None);
  ReferenceEquals(result.Value.Status,ContributorStatus.Community).ShouldBeTrue();
 }
}
'''
WEBTEST='''using Clean.Architecture.Web.Contributors;
namespace Clean.Architecture.UnitTests.Core.ContributorAggregate;
public class BenchWebStatus
{
 [Theory][InlineData("CoreTeam",true)][InlineData(" community ",true)][InlineData(null,true)]
 [InlineData("",false)][InlineData(" ",false)][InlineData("Unknown",false)]
 public void RequestValidation(string? status,bool valid)
 {
  var req=new UpdateContributorRequest {Id=1,ContributorId=1,Name="Valid Name",Status=status};
  new UpdateContributorValidator().Validate(req).IsValid.ShouldBe(valid);
 }
 [Fact] public void UpdateMapperExposesActualStatus()
 {
  var dto=new Clean.Architecture.UseCases.Contributors.ContributorDto(ContributorId.From(1),ContributorName.From("Name"),PhoneNumber.Unknown,ContributorStatus.Community);
  var type=typeof(UpdateContributorRequest).Assembly.GetType("Clean.Architecture.Web.Contributors.UpdateContributorMapper");
  type.ShouldNotBeNull("Original public UpdateContributorMapper API must remain available");
  var mapper=Activator.CreateInstance(type!);
  var mapped=(UpdateContributorResponse)type!.GetMethod("FromEntity")!.Invoke(mapper,new object[]{dto})!;
  mapped.Contributor.Status.ShouldBe("Community");
  new ContributorRecord(1,"Name",null).Status.ShouldBe("NotSet");
  new GetContributorByIdMapper().FromEntity(dto).Status.ShouldBe("Community");
 }
}
'''

def run():
 resume=os.environ.get('MULTI_RESUME'); stamp=resume.removeprefix('multi-') if resume else dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'); base=ROOT/'local-results'/('multi-'+stamp);base.mkdir(parents=True,exist_ok=True)
 report={'utc':stamp,'model':'qwen2.5-coder:7b','task':TASK,'arms':{},'status':'running','notes':'Same Aider whole-file editing harness. map=0 baseline; Aider map=2048; SCIP read-only references/map=0. Adaptive rounds; no fixed final round budget. Not a context-only token-matched ablation.'}
 out=ROOT/'results/runs'/('multi-'+stamp+'.json')
 if resume: report=json.loads(out.read_text(encoding='utf-8'))
 def save():
  out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
  from document_results import write_report
  write_report('multi-'+stamp)
 archive=subprocess.check_output(['git','-C',str(FIXTURE),'archive','--format=zip','HEAD'])
 report['fixture_commit']=subprocess.check_output(['git','-C',str(FIXTURE),'rev-parse','HEAD'],text=True).strip()
 hits=list(occurrences(FIXTURE/'index.scip'))
 selected=sorted({p.replace('\\','/') for p,s,l,d in hits if any(n in s for n in ('ContributorStatus','UpdateContributor','ContributorDto','Contributor#')) and p.replace('\\','/').startswith('src/')})
 report['scip_context_paths']=selected
 # identical editable starting files, covering the specified feature; additional files can be added by editor
 editable=['src/Clean.Architecture.Core/ContributorAggregate/Contributor.cs','src/Clean.Architecture.UseCases/Contributors/Update/UpdateContributorCommand.cs','src/Clean.Architecture.UseCases/Contributors/Update/UpdateContributorHandler.cs','src/Clean.Architecture.UseCases/Contributors/ContributorDTO.cs','src/Clean.Architecture.UseCases/Contributors/Get/GetContributorHandler.cs','src/Clean.Architecture.Web/Contributors/Update.cs','src/Clean.Architecture.Web/Contributors/Update.UpdateContributorRequest.cs','src/Clean.Architecture.Web/Contributors/Update.UpdateContributorValidator.cs','src/Clean.Architecture.Web/Contributors/ContributorRecord.cs','src/Clean.Architecture.Web/Contributors/GetById.cs']
 env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',OLLAMA_API_BASE='http://127.0.0.1:11434',AIDER_ANALYTICS='false',OLLAMA_CONTEXT_LENGTH='16384')
 for arm in ('baseline','aider','scip'):
  if resume: continue
  folder=base/arm;folder.mkdir();checkout=folder/'fixture'
  with zipfile.ZipFile(io.BytesIO(archive)) as z:z.extractall(checkout)
  subprocess.run(['git','init','-q'],cwd=checkout,check=True)
  subprocess.run(['git','add','.'],cwd=checkout,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  subprocess.run(['git','-c','user.name=Benchmark','-c','user.email=benchmark@localhost','commit','-qm','Pristine public fixture'],cwd=checkout,check=True)
  report['arms'][arm]={'rounds':[],'success':False};save()
  # evaluator files are installed only AFTER each model call, then removed
  (folder/'task.txt').write_text(TASK,encoding='utf-8')
  if arm=='scip':
   context='\n'.join('### '+p+'\n'+(checkout/p).read_text(encoding='utf-8-sig') for p in selected if (checkout/p).is_file())
   (folder/'scip-reference.txt').write_text(context[:24000],encoding='utf-8')
  report['arms'][arm]['directory']=str(folder.relative_to(ROOT));save()
 # round-robin prevents a successful arm receiving an unfair early stop for others
 round_number=max((len(a['rounds']) for a in report['arms'].values()),default=0)
 while not all(v['success'] for v in report['arms'].values()):
  round_number+=1
  for arm,info in report['arms'].items():
   if info['success']:continue
   folder=base/arm;checkout=folder/'fixture';log(f'Multi-file {arm}, round {round_number}')
   if round_number >= 3:
    import xml.etree.ElementTree as APIXML
    package=Path.home()/'.nuget/packages/ardalis.smartenum/8.2.0/lib/net8.0/Ardalis.SmartEnum.xml'
    members=APIXML.parse(package).getroot().find('members')
    docs='\n'.join(APIXML.tostring(m,encoding='unicode') for m in members if m.get('name','').startswith('M:Ardalis.SmartEnum.SmartEnum`2.') and any('.'+name+'(' in m.get('name','') for name in ('FromName','TryFromName')))
    status_source=(checkout/'src/Clean.Architecture.Core/ContributorAggregate/ContributorStatus.cs').read_text(encoding='utf-8')
    (folder/'common-api-reference.txt').write_text(status_source+'\n'+docs,encoding='utf-8')
    info['additional_assistance_from_round_3']='Actual ContributorStatus source and installed SmartEnum XML API documentation; all arms receive identical reference.'
   args=[str(executable(AIDER_ENV,'aider')),'--model',os.environ.get('MULTI_PROVIDER','ollama/qwen2.5-coder:7b'),'--edit-format','whole','--map-tokens','2048' if arm=='aider' else '0','--llm-history-file',str(folder/f'round-{round_number}-llm-history.md'),'--model-settings-file',str(ROOT/'local-results/multi-model-settings.yml'),'--no-auto-commits','--no-auto-lint','--no-auto-test','--no-check-update','--no-show-model-warnings','--no-pretty','--yes','--message-file',str(folder/'task.txt')]
   if arm=='scip':args+=['--read',str(folder/'scip-reference.txt')]
   if round_number>=3:args+=['--read',str(folder/'common-api-reference.txt')]
   active_files=list(editable)
   if round_number>=4:
    import re
    prior=info['rounds'][-1]['round'] if info['rounds'] else 1
    priorlog=Path(info['best_feedback']) if info.get('best_passed',0)>int(info['rounds'][-1].get('counts',{}).get('passed',0)) else folder/f'round-{prior}-tests.log'
    if priorlog.exists():
     candidates=re.findall(r'src[\\/][^\r\n():]+?\.cs',priorlog.read_text(encoding='utf-8'))
     relevant=sorted({p.replace('\\','/') for p in candidates if (checkout/p.replace('\\','/')).is_file()})
     if relevant: active_files=relevant
     if 'Detailed TRX failures:' in priorlog.read_text(encoding='utf-8') or 'Superseding evaluator audit' in priorlog.read_text(encoding='utf-8'):
      active_files=sorted(set(active_files+editable+[str(p.relative_to(checkout)).replace('\\','/') for p in (checkout/'src/Clean.Architecture.Web/Contributors').glob('*Mapper*.cs')]))
    text=priorlog.read_text(encoding='utf-8').replace(str(checkout),'<FIXTURE>') if priorlog.exists() else (folder/'task.txt').read_text(encoding='utf-8')
    text=re.sub(r'https?://[^\s)]+','[documentation link omitted]',text)
    text='Verified type facts: ContributorStatus is a CLASS (SmartEnum), not an enum or struct. ContributorStatus? is a nullable reference. No HasValue exists; Value is an int id. The command already holds the status instance.\nCompiler/test diagnostics:\n'+text[-16000:]
    (folder/'task.txt').write_text('PRODUCTION REPAIR ONLY. Edit existing production src files in Core, UseCases, Infrastructure and Web. NEVER write or modify tests, test projects, build configuration or dependencies. A failing test specifies required behavior: fix the production implementation. Do not write replacement tests or mock examples. REPAIR MODE: Fix ONLY the specific current compiler/test errors below. The feature already exists. Do not regenerate the whole feature or unchanged files. Preserve existing APIs. Focus on error locations and actual dependency types.\n'+text,encoding='utf-8')
   if round_number>=10:
    from compiler_context import context_for_errors
    prior=info['rounds'][-1]['round'];priorlog=Path(info['best_feedback']) if info.get('best_passed',0)>int(info['rounds'][-1].get('counts',{}).get('passed',0)) else folder/f'round-{prior}-tests.log'
    dynamic,context_paths=context_for_errors(priorlog.read_text(encoding='utf-8'),checkout)
    (folder/'compiler-symbol-context.txt').write_text(dynamic,encoding='utf-8')
    args+=['--read',str(folder/'compiler-symbol-context.txt')]
    info['compiler_context_paths']=context_paths
   if round_number>=21:
    diagnostics=priorlog.read_text(encoding='utf-8')
    if 'RequestValidation' in diagnostics:
     active_files=['src/Clean.Architecture.Web/Contributors/Update.UpdateContributorValidator.cs']
    elif 'Original public UpdateContributorMapper API must remain available' in diagnostics:
     active_files=['src/Clean.Architecture.Web/Contributors/Update.UpdateContributorMapperImpl.cs']
    elif 'EndpointForwardsStatusAndCancellation' in diagnostics:
     active_files=['src/Clean.Architecture.Web/Contributors/Update.cs']
    elif 'GetMapperExposesActualStatus' in diagnostics:
     active_files=['src/Clean.Architecture.Web/Contributors/GetById.cs']
    elif len(active_files)>1:active_files=active_files[:1]
    text=(folder/'task.txt').read_text(encoding='utf-8')
    from repair_requirements import requirements
    (folder/'task.txt').write_text('This repair turn may edit ONLY '+active_files[0]+'. Changes to any other file will be discarded. Repair the production behavior specified by the failing tests, not the tests.\n'+text+'\nFINAL ACCEPTANCE CRITERIA FOR THIS FILE:\n'+requirements(active_files[0]),encoding='utf-8')
   args += [p for p in active_files if (checkout/p).is_file()]
   from code_checkpoints import snapshot,restore
   before=folder/f'round-{round_number}-before.zip';snapshot(checkout,before)
   start=__import__('time').monotonic()
   try:
    with (folder/f'round-{round_number}-editor.log').open('w',encoding='utf-8') as live:
     proc=subprocess.run(args,cwd=checkout,env=env,stdin=subprocess.DEVNULL,stdout=live,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=600)
    raw=(folder/f'round-{round_number}-editor.log').read_text(encoding='utf-8');editor_exit=proc.returncode
   except subprocess.TimeoutExpired as exc:raw=(exc.stdout or b'').decode('utf-8','replace') if isinstance(exc.stdout,bytes) else exc.stdout or '';editor_exit=None
   (folder/f'round-{round_number}-editor.log').write_text(raw,encoding='utf-8')
   duration=round(__import__('time').monotonic()-start,2)
   if round_number>=21:
    restore(checkout,before,except_paths=active_files)
   # prevent test/config edits from bypassing evaluation
   subprocess.run(['git','restore','--','tests','Directory.Build.props','Directory.Packages.props'],cwd=checkout,check=True)
   testproject=checkout/PROJECT;original_project=testproject.read_text(encoding='utf-8')
   testproject.write_text(original_project.replace('<PackageReference Include="Mediator.SourceGenerator" />','').replace('</Project>','<ItemGroup><ProjectReference Include="../../src/Clean.Architecture.Web/Clean.Architecture.Web.csproj" /></ItemGroup></Project>'),encoding='utf-8')
   testdir=checkout/'tests/Clean.Architecture.UnitTests/Core/ContributorAggregate';hidden=testdir/'BenchMultiStatus.cs';hidden.write_text(HIDDEN+ '\n',encoding='utf-8')
   webhidden=testdir/'BenchWebStatus.cs';webhidden.write_text(WEBTEST,encoding='utf-8')
   import multi_endpoint_checks, importlib
   importlib.reload(multi_endpoint_checks)
   from multi_endpoint_checks import EXTRA
   endpointtest=testdir/'BenchEndpointPropagation.cs';endpointtest.write_text(EXTRA,encoding='utf-8')
   import multi_database_checks
   importlib.reload(multi_database_checks)
   from multi_database_checks import EXTRA as DBEXTRA
   dbtest=testdir/'BenchStatusPersistence.cs';dbtest.write_text(DBEXTRA,encoding='utf-8')
   trx=folder/f'test-results-{round_number}'
   check=command(['dotnet','test',PROJECT,'--verbosity','quiet','--logger','trx;LogFileName=tests.trx','--results-directory',str(trx)],checkout,folder/f'round-{round_number}-tests.log',timeout=360)
   counts={}
   if (trx/'tests.trx').exists():
    xml=ET.parse(trx/'tests.trx').getroot();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};counts=xml.find('t:ResultSummary/t:Counters',ns).attrib
    failures=[]
    for case in xml.findall('t:Results/t:UnitTestResult',ns):
     if case.get('outcome')!='Passed':
      message=case.findtext('t:Output/t:ErrorInfo/t:Message','',ns)[:1200]
      stack=case.findtext('t:Output/t:ErrorInfo/t:StackTrace','',ns)
      frames='\n'.join(line for line in stack.splitlines() if str(checkout) in line and ('\\src\\' in line or '/src/' in line))
      failures.append(case.get('testName')+'\n'+message+'\n'+frames)
    if failures:
     failure_text='\n\n'.join(failures)
     logpath=folder/f'round-{round_number}-tests.log'
     logpath.write_text(logpath.read_text(encoding='utf-8')+'\n\nDetailed TRX failures:\n'+failure_text,encoding='utf-8')
   testproject.write_text(original_project,encoding='utf-8');hidden.unlink();webhidden.unlink();endpointtest.unlink();dbtest.unlink()
   diff=subprocess.check_output(['git','diff','--','src'],cwd=checkout,text=True,encoding='utf-8');(folder/f'round-{round_number}.diff').write_text(diff,encoding='utf-8')
   changed=subprocess.check_output(['git','diff','--name-only','--','src'],cwd=checkout,text=True).splitlines()
   success=check['exit_code']==0 and int(counts.get('passed',0))>=28 and len(changed)>=7
   candidate_passed=int(counts.get('passed',0))
   rejected=candidate_passed<info.get('best_passed',0)
   if rejected:restore(checkout,folder/'best-production.zip')
   elif candidate_passed>info.get('best_passed',0):
    snapshot(checkout,folder/'best-production.zip');info['best_passed']=candidate_passed;info['best_feedback']=str(folder/f'round-{round_number}-tests.log')
   info['rounds'].append({'rejected_regression':rejected,'editable_files':active_files,'round':round_number,'editor_exit':editor_exit,'editor_s':duration,'validation':check,'counts':counts,'changed_files':changed,'success':success});info['success']=success;save()
   log(f'{arm}: success={success}, changed_files={len(changed)}, passed={counts.get("passed",0)}')
   errors=(Path(info['best_feedback']) if rejected else folder/f'round-{round_number}-tests.log').read_text(encoding='utf-8').replace(str(checkout),'<FIXTURE>')
   (folder/'task.txt').write_text(TASK+'\nYour previous implementation failed independent checks. Fix your production code. Do not change tests. Compiler/test feedback:\n'+errors[-16000:],encoding='utf-8')
 report['status']='complete';save();log(f'Comparison completed: {out}')

if __name__=='__main__':run()
