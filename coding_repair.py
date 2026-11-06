"""One bounded compiler-feedback repair with installed dependency documentation."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from coding_bench import TARGET, PROJECT, TASK, command
from runner import ROOT, log


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run_id')
    args=parser.parse_args()
    local=ROOT/'local-results'/args.run_id
    checkout=local/'fixture'
    previous=json.loads((ROOT/'results/runs'/(args.run_id+'.json')).read_text())
    original=(checkout/TARGET).read_text(encoding='utf-8')
    package=Path.home()/'.nuget/packages/ardalis.smartenum/8.2.0/lib/net8.0/Ardalis.SmartEnum.xml'
    members=ET.parse(package).getroot().find('members')
    docs='\n'.join(ET.tostring(m,encoding='unicode') for m in members
                   if m.get('name','').startswith('M:Ardalis.SmartEnum.SmartEnum`2.')
                   and any('.'+name+'(' in m.get('name','') for name in ('FromName','TryFromName')))
    dependencies=(checkout/'src/Clean.Architecture.Core/ContributorAggregate/ContributorStatus.cs').read_text(encoding='utf-8')
    answer=(local/'selected_dependencies-answer.txt').read_text(encoding='utf-8')
    error=(local/'selected_dependencies-tests.log').read_text(encoding='utf-8').replace(str(checkout),'<FIXTURE>')
    prompt=TASK+'\nOriginal file:\n'+original+'\nDependency:\n'+dependencies+'\nInstalled Ardalis.SmartEnum 8.2.0 XML API documentation:\n'+docs+'\nPrevious attempt:\n'+answer+'\nCompiler feedback:\n'+error+'\nCorrect the previous attempt using the actual documented API. Return the full file only.'
    label='dependency_api_and_feedback'
    (local/(label+'-prompt.txt')).write_text(prompt,encoding='utf-8')
    payload={'model':previous['model'],'prompt':prompt,'stream':False,'options':previous['options']}
    log('Qwen repair with dependency API and compiler feedback')
    started=time.monotonic()
    req=urllib.request.Request('http://127.0.0.1:11434/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as response:
        generated=json.load(response)
    text=generated['response']
    (local/(label+'-answer.txt')).write_text(text,encoding='utf-8')
    blocks=re.findall(r'```(?:csharp|cs)?\s*\n(.*?)```',text,re.S)
    code=blocks[0] if len(blocks)==1 else text.strip() if '```' not in text else ''
    report={'schema_version':1,'parent_run':args.run_id,'model':previous['model'],
            'fixture_commit':previous['fixture_commit'],'method':label,'options':previous['options'],
            'api_source':'installed Ardalis.SmartEnum 8.2.0 XML documentation',
            'generation_s':round(time.monotonic()-started,2),
            'prompt_tokens':generated.get('prompt_eval_count'),'output_tokens':generated.get('eval_count'),
            'limitations':'Adaptive retry, one task, API docs and feedback added together; causal contributions not separated.'}
    try:
        (checkout/TARGET).write_text(code,encoding='utf-8')
        report.update(command(['dotnet','test',PROJECT,'--no-restore','--verbosity','quiet',
                    '--logger','trx;LogFileName='+label+'.trx','--results-directory',str(local/'test-results')],
                    checkout,local/(label+'-tests.log')))
        trx=local/'test-results'/(label+'.trx')
        if trx.exists():
            root=ET.parse(trx).getroot()
            ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
            report['test_counts']=root.find('t:ResultSummary/t:Counters',ns).attrib
            results=root.findall('t:Results/t:UnitTestResult',ns)
            report['task_tests_passed']=sum('BenchContributorStatus' in r.get('testName','') and r.get('outcome')=='Passed' for r in results)
        report['success']=report.get('exit_code')==0 and report.get('task_tests_passed')==9
        if report['success']:
            (local/'successful-Contributor.cs').write_text(code,encoding='utf-8')
    finally:
        (checkout/TARGET).write_text(original,encoding='utf-8')
    report['status']='complete'
    output=ROOT/'results/runs'/(args.run_id+'-repair.json')
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    log(f'Repair success={report["success"]}; report={output}')

if __name__=='__main__':
    main()
