"""Create a readable, evidence-linked journal from retained benchmark results."""
import json
from pathlib import Path
from runner import ROOT

def write_report(run_id):
 source=ROOT/'results/runs'/(run_id+'.json');data=json.loads(source.read_text(encoding='utf-8'))
 lines=['# Vergleich: größere C#-Änderung mit lokalem Qwen','',f'Run: `{run_id}` · Status: **{data["status"]}**','',
 '## Ziel und unveränderte Anforderungen','',data['task'],'',
 '## Versuchsbedingungen','',f'- Modell: `{data["model"]}`',f'- Fixture-Commit: `{data["fixture_commit"]}`',
 '- Drei isolierte Projektkopien; derselbe Ausgangscode und dieselben Anforderungen.',
 '- Gleicher Aider-Editor: Baseline ohne Map, Aider mit Repository-Map, SCIP mit indexbasiertem Referenzkontext ohne Map.',
 '- Fehler-Rückkopplung pro Variante; Produktionscode wird vom lokalen Modell geändert.',
 '- Original-Fixture wird erhalten. Neue Versuche können vom ursprünglichen Commit starten.',
 '- Mehrere Schichten: Domäne, UseCase, DTO, Request, Validator, Endpunkt, Response.',
 '- Ein einzelner Versuch erlaubt keine allgemeine Rangfolge der Werkzeuge. Kontextmengen und interne Modellaufrufe sind nicht tokenidentisch.',
 '', '## Gegenüberstellung','', '| Variante | Abgeschlossene Runden | Erfolg laut erster Prüfstufe | Bester geprüfter Stand | Letzter Kandidat: Tests bestanden | Geänderte Dateien (Rohwert) |', '|---|---:|---|---:|---:|---:|']
 for arm,info in data['arms'].items():
  last=info['rounds'][-1] if info['rounds'] else {};counts=last.get('counts',{})
  lines.append(f'| {arm} | {len(info["rounds"])} | {"Ja" if info["success"] else "Noch nicht"} | {info.get("best_passed",0)} | {counts.get("passed","nicht ausgeführt / nicht kompiliert")} | {len(last.get("changed_files",[]))} |')
 lines+=['','## Korrekturen am Testrahmen','',data.get('evaluation_correction','Keine dokumentiert.'),
 '','Der reparierte Prüflauf ohne Modelländerung wurde separat geprüft: 12/12 bestehende Tests bestehen mit Web-Projektreferenz. Ein bestätigter Feature-Erfolg braucht zusätzliche fachliche Prüfungen; diese Baseline allein erfüllt die Aufgabe nicht.','',
 '## Änderungen der Versuchsbedingungen','', data.get('rescue_phase','Keine spätere Hilfestufe dokumentiert.')+'\n\n'+data.get('incremental_repair_phase','')+'\n\n'+data.get('compiler_guided_context_phase','')+'\n\n'+data.get('pending_evaluator_fix',''),'', 'Abgebrochene Aider-Runde: '+json.dumps(data.get('interrupted_aider_round_2',{}),ensure_ascii=False),'', '## Vollständiges Rundenjournal','']
 for arm,info in data['arms'].items():
  lines+=['### '+arm,'',info.get('additional_assistance_from_round_3',''), '']
  for rnd in info['rounds']:
   number=rnd['round'];folder=ROOT/info['directory'];prefix=f'round-{number}'
   lines += [f'#### Runde {number}','',f'- Editor: Exit `{rnd["editor_exit"]}`, {rnd["editor_s"]} s.',
    f'- Validierung: Exit `{rnd["validation"]["exit_code"]}`, {rnd["validation"]["duration_s"]} s.',
    f'- Testzähler: `{json.dumps(rnd["counts"],ensure_ascii=False)}`.',f'- Erfolg laut Prüfstufe: **{rnd["success"]}**.',
    '- Änderungen: '+', '.join('`'+p+'`' for p in rnd['changed_files'])+'.','']
   logfile=folder/(prefix+'-tests.log')
   preserved=folder/(prefix+'-tests-before-functional-audit.log')
   if preserved.exists():logfile=preserved
   if logfile.exists():
    raw=logfile.read_text(encoding='utf-8');errors=[s for s in raw.splitlines() if ': error ' in s or 'Failed ' in s or 'Error Message:' in s]
    lines+=['Fehlermeldungen (Auszug; vollständiges Protokoll verlinkt):','', '```text', '\n'.join(errors[:8]).replace(str(folder/'fixture'),'<FIXTURE>')[:5000] or 'Keine Compilerfehlermeldung in diesem Auszug.', '```','']
   for label,suffix in [('Editorprotokoll','-editor.log'),('Prüfprotokoll','-tests.log'),('Diff','.diff')]:
    path=folder/(prefix+suffix);lines.append(f'- [{label}]({path.as_posix()})')
   lines+=['']
 lines+=['## Letzter gesonderter Funktionsaudit','', '```json', json.dumps(data.get('functional_audit',{}),ensure_ascii=False,indent=2), '```','', 'Der gesonderte Audit ersetzt keine frühere Modellrunde. Er verwendet denselben Produktionscode nach Korrektur der Zusatzprüfungen. Die vollständige Fehlerdiagnose wurde als nächste Reparatureingabe verwendet.','', '## Vorversuche und Infrastrukturprüfungen','',
 '| Prüfung | Beobachtetes Ergebnis | Einordnung |',
 '|---|---|---|',
 '| Python-Regressionssuite | 8/8 bestanden | Prüft den Benchmark, nicht Qwens Programmierleistung |',
 '| Aider-Installation | erfolgreich mit Python 3.12.16 | Separater Projektordner, UTF-8-Ausgabe korrigiert |',
 '| Aider-Repository-Map | Exit 0, 15.853 Ausgabezeichen inklusive Diagnose | Kontextgenerator funktioniert |',
 '| SCIP-Index | 5.114 Vorkommen, 129 Dokumente | Indexdaten verfügbar |',
 '| Datei-/Symbolsuche ohne Kontext | UNKNOWN | Kein Coding-Test |',
 '| Datei-/Symbolsuche mit SCIP | Definitionsdatei erkannt | Ein Versuch, begrenzte Pfadbewertung |',
 '| Ein-Methoden-Codepilot: drei Erstvarianten | alle Compilerfehler | Zieldatei / allgemeine Map / passende Quellen |',
 '| Ein-Methoden-Pilot nach API-Dokumentation + Compilerfeedback | 21/21 bestanden, davon 9 neue Prüfungen | Erster kleiner Code-Erfolg; kein Beleg für große Aufgaben |',
 '| Originalprojekt mit reparierter Web-Testreferenz | 12/12 bestanden | Kontrollprüfung des neuen Testrahmens |','',
 'Die vollständigen Pilot-Messwerte liegen unter `results/runs/coding-20261106T152454Z*.json`; Rohlogs und erfolgreicher Modellcode unter `local-results/coding-20261106T152454Z/`.','']
 lines+=['## Bewertung und nächste Schritte','',
 'Der Vergleich läuft weiter, bis die größere Änderung nachweislich funktioniert. Ein positives Ergebnis wird zusätzlich darauf geprüft, dass Status und CancellationToken tatsächlich durch den Web-Endpunkt weitergegeben werden. Zusätzliche Hilfe oder Prüfänderungen werden ausgewiesen; fehlgeschlagene Runden bleiben erhalten.','',
 'Messwerte: ['+source.name+']('+source.as_posix()+'). Vollständige Modellantworten, Prompts und Diffs bleiben lokal.']
 text='\n'.join(lines)+'\n'
 start=text.index('## Vollständiges Rundenjournal')
 end=text.index('## Letzter gesonderter Funktionsaudit')
 journal=ROOT/'EXPERIMENT-RUNDEN.md'
 journal.write_text('# Vollständiges Rundenjournal\n\n'+text[start:end],encoding='utf-8')
 text=text[:start]+'## Vollständiges Rundenjournal\n\n[Alle Runden, Fehlermeldungen und Protokollverweise]('+journal.as_posix()+').\n\n'+text[end:]
 events=ROOT/'local-results'/run_id/'execution-interventions.jsonl'
 if events.exists():text+='\n## Weitere protokollierte Ausführungsänderungen\n\n```json\n'+events.read_text(encoding='utf-8')+'```\n'
 out=ROOT/'EXPERIMENT-ERGEBNISSE.md';out.write_text(text,encoding='utf-8');return out

if __name__=='__main__':
 import sys
 print(write_report(sys.argv[1]))
