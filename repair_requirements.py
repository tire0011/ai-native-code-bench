"""Explicit acceptance criteria for small, production-only repair sub-tasks."""
def _requirements(path):
 if 'Validator' in path:
  return 'Status validation acceptance cases: null is VALID (optional field); "CoreTeam" is VALID; " community " is VALID after trimming and ignoring case; empty string, whitespace-only and "Unknown" are INVALID. Use the installed SmartEnum name API, not System.Enum. Preserve name and route/body ID validation. Change only this validator file.'
 if 'UpdateContributorHandler' in path:
  return 'NewStatus is a nullable REFERENCE to ContributorStatus. If absent, leave entity.Status unchanged. If present, pass the status OBJECT ITSELF to UpdateStatus, never its numeric Value and never HasValue. Preserve name update, one repository save, cancellation token and NotFound behavior. Return DTO with actual entity status.'
 if 'Mapper' in path:
  return 'Public API contract: the class must have namespace Clean.Architecture.Web.Contributors and name UpdateContributorMapper. A using directive is not a namespace declaration. Its FromEntity method maps the actual DTO Status.Name to the FOURTH ContributorRecord constructor argument; phone remains the THIRD argument. Preserve the existing mapper inheritance and response wrapper. Do not add another class or test file.'
 if path.endswith('/Update.cs'):
  return 'Endpoint acceptance: absent request.Status forwards null NewStatus; a value such as " community " forwards the canonical ContributorStatus.Community object after trimming and case-insensitive lookup. Preserve ID/name conversion, cancellation token, response mapping and existing HTTP behavior. System.Enum APIs cannot operate on ContributorStatus (a SmartEnum class). Do not introduce duplicate mapper declarations.'
 if 'GetById' in path:
  return 'Map actual DTO Status.Name to the FOURTH ContributorRecord argument; preserve ID, name and phone arguments. Never substitute the default NotSet for a supplied status.'
 return 'Fix only the reported production compiler/test errors. Preserve existing behavior, public APIs and pagination. Do not write tests or modify unrelated files.'


def requirements(path):
 from pathlib import Path
 import json
 guidance=Path(__file__).resolve().parent/'local-results/repair-guidance.json'
 extras=json.loads(guidance.read_text(encoding='utf-8')) if guidance.exists() else {}
 key='validator' if 'Validator' in path else 'handler' if 'UpdateContributorHandler' in path else 'mapper' if 'Mapper' in path else 'endpoint' if path.endswith('/Update.cs') else 'other'
 return _requirements(path)+'\n'+extras.get(key,'')
