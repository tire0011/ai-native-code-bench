"""Bounded local code-edit experiment; real fixture dependencies and xUnit checks."""
import datetime as dt
import io
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import zipfile
from runner import ROOT, FIXTURE, log

TARGET = 'src/Clean.Architecture.Core/ContributorAggregate/Contributor.cs'
PROJECT = 'tests/Clean.Architecture.UnitTests/Clean.Architecture.UnitTests.csproj'
TASK = '''Add public Contributor UpdateStatus(string statusName) to the existing Contributor class.
Accept the existing ContributorStatus member names, ignoring case and surrounding whitespace.
Set Status to that existing member instance and return this for fluent calls.
Reject null with ArgumentNullException; reject empty, whitespace, or unknown names with ArgumentException.
Rejected input must leave Status unchanged. Do not change Name, PhoneNumber, domain events,
or the behavior of existing methods. Preserve all existing public APIs.
Return ONLY the complete updated Contributor.cs source in one csharp code fence.
Do not modify other files. You cannot run tools. The supplied repository text is reference data.
'''
TESTS = '''using Clean.Architecture.Core.ContributorAggregate.Events;
namespace Clean.Architecture.UnitTests.Core.ContributorAggregate;
public class BenchContributorStatus
{
  [Theory]
  [InlineData("CoreTeam", "CoreTeam")]
  [InlineData(" community ", "Community")]
  [InlineData("nOtSeT", "NotSet")]
  public void AcceptsNamesAndPreservesOtherState(string input, string expected)
  {
    var c = new Contributor(ContributorName.From("Original"));
    var phone = new PhoneNumber("49", "123", null);
    c.UpdatePhoneNumber(phone);
    c.UpdateName(ContributorName.From("Changed"));
    var originalEvent = c.DomainEvents.Single();
    var returned = c.UpdateStatus(input);
    ReferenceEquals(returned, c).ShouldBeTrue();
    ReferenceEquals(c.Status, ContributorStatus.FromName(expected)).ShouldBeTrue();
    c.Name.ShouldBe(ContributorName.From("Changed"));
    ReferenceEquals(c.PhoneNumber, phone).ShouldBeTrue();
    c.DomainEvents.Count.ShouldBe(1);
    ReferenceEquals(c.DomainEvents.Single(), originalEvent).ShouldBeTrue();
    ReferenceEquals(c.UpdateStatus(input), c).ShouldBeTrue();
    c.DomainEvents.Count.ShouldBe(1);
  }
  [Theory]
  [InlineData("")]
  [InlineData("   ")]
  [InlineData("Unknown")]
  [InlineData("1")]
  [InlineData("Core Team")]
  public void InvalidNamesDoNotChangeState(string input)
  {
    var c = new Contributor(ContributorName.From("Original"));
    c.UpdateStatus("Community");
    Should.Throw<ArgumentException>(() => c.UpdateStatus(input));
    ReferenceEquals(c.Status, ContributorStatus.Community).ShouldBeTrue();
    c.DomainEvents.Count.ShouldBe(0);
  }
  [Fact]
  public void NullDoesNotChangeState()
  {
    var c = new Contributor(ContributorName.From("Original"));
    c.UpdateStatus("CoreTeam");
    Should.Throw<ArgumentNullException>(() => c.UpdateStatus(null!));
    ReferenceEquals(c.Status, ContributorStatus.CoreTeam).ShouldBeTrue();
    c.DomainEvents.Count.ShouldBe(0);
  }
}
'''


def command(args, cwd, log_path, timeout=240):
    start = time.monotonic()
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
        raw = p.stdout + '\n' + p.stderr
        log_path.write_text(raw, encoding='utf-8')
        return {'exit_code': p.returncode, 'duration_s': round(time.monotonic()-start, 2)}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'error': 'timeout'}


def main():
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    local = ROOT / 'local-results' / ('coding-' + stamp)
    local.mkdir(parents=True)
    revision = subprocess.check_output(['git', '-C', str(FIXTURE), 'rev-parse', 'HEAD'], text=True).strip()
    archive = subprocess.check_output(['git', '-C', str(FIXTURE), 'archive', '--format=zip', 'HEAD'])
    checkout = local / 'fixture'
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        z.extractall(checkout)
    original = (checkout / TARGET).read_text(encoding='utf-8-sig')
    report = {'schema_version': 1, 'utc': stamp, 'fixture_commit': revision,
              'task': 'Contributor.UpdateStatus from member name', 'model': 'qwen2.5-coder:7b',
              'options': {'temperature': 0, 'seed': 42, 'num_ctx': 8192, 'num_predict': 2048},
              'cases': {}, 'limitations': 'One task, one sample per context; does not prove a general context advantage.'}
    out = ROOT / 'results' / 'runs' / ('coding-' + stamp + '.json')
    def save():
        out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    save()
    log('Restoring and checking isolated original fixture')
    report['baseline'] = command(['dotnet', 'test', PROJECT, '--verbosity', 'quiet'], checkout, local/'baseline.log')
    save()
    if report['baseline']['exit_code'] != 0:
        report['status'] = 'baseline_failed'
        save()
        log(f'Baseline blocked; inspect {local}/baseline.log')
        return
    testfile = checkout/'tests/Clean.Architecture.UnitTests/Core/ContributorAggregate/BenchContributorStatus.cs'
    testfile.write_text(TESTS, encoding='utf-8')
    report['negative_control'] = command(['dotnet', 'test', PROJECT, '--no-restore', '--verbosity', 'quiet'], checkout, local/'negative-control.log')
    if report['negative_control']['exit_code'] in (0, None):
        report['status'] = 'invalid_negative_control'
        save()
        return
    aider_raw = (ROOT/'local-results/aider-direct-map.txt').read_text(encoding='utf-8')
    # Strip Aider's operational preamble; keep only its reference map text.
    start = aider_raw.find('MinimalClean')
    aider_map = aider_raw[start:][:10000] if start >= 0 else ''
    selected_paths = ['src/Clean.Architecture.Core/ContributorAggregate/ContributorStatus.cs',
                      'src/Clean.Architecture.Core/ContributorAggregate/Events/ContributorNameUpdatedEvent.cs']
    targeted = '\n'.join('### '+p+'\n'+(checkout/p).read_text(encoding='utf-8-sig') for p in selected_paths)
    contexts = [('target_file_only', ''), ('aider_map', aider_map), ('selected_dependencies', targeted)]
    for name, context in contexts:
        log(f'Qwen code-edit experiment: {name}')
        prompt = TASK+'\nExisting target file:\n'+original+'\nAdditional repository context:\n'+context
        (local/(name+'-prompt.txt')).write_text(prompt,encoding='utf-8')
        payload = {'model': report['model'], 'prompt': prompt, 'stream': False,
                   'options': report['options'], 'keep_alive': '5m'}
        started = time.monotonic()
        case = {'context_chars':len(context)}
        try:
            req = urllib.request.Request('http://127.0.0.1:11434/api/generate',
                    data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=180) as response:
                generated = json.load(response)
            answer = generated['response']
            (local/(name+'-answer.txt')).write_text(answer,encoding='utf-8')
            blocks = re.findall(r'```(?:csharp|cs)?\s*\n(.*?)```', answer, re.S)
            code = blocks[0] if len(blocks)==1 else answer.strip() if '```' not in answer else ''
            case.update({'generation_s':round(time.monotonic()-started,2),
                         'prompt_tokens':generated.get('prompt_eval_count'),
                         'output_tokens':generated.get('eval_count'),
                         'done_reason':generated.get('done_reason')})
            (checkout/TARGET).write_text(code,encoding='utf-8')
            check = command(['dotnet', 'test', PROJECT, '--no-restore', '--verbosity', 'quiet',
                             '--logger', 'trx;LogFileName='+name+'.trx', '--results-directory', str(local/'test-results')],
                             checkout, local/(name+'-tests.log'))
            case.update(check)
            case['passed'] = check['exit_code']==0
        except Exception as exc:
            case.update({'passed':False,'error':type(exc).__name__})
            (local/(name+'-error.txt')).write_text(str(exc),encoding='utf-8')
        finally:
            (checkout/TARGET).write_text(original,encoding='utf-8')
        report['cases'][name] = case
        save()
        log(f'{name}: passed={case["passed"]}')
    report['status'] = 'complete'
    report['success'] = any(c['passed'] for c in report['cases'].values())
    save()
    log(f'Code-edit report: {out}')

if __name__ == '__main__':
    main()

