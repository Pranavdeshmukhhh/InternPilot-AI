"""Redacted Gitleaks history scan with verified checksum-only false-positive triage."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def verified_checksum(repo,finding):
    if Path(finding['File']).name!='RELEASE_MANIFEST.json' or finding['RuleID']!='generic-api-key':return False
    commit=finding['Commit']
    if not re.fullmatch('[a-f0-9]{40,64}',commit):return False
    try:
        contents=subprocess.check_output(['git','show',commit+':'+finding['File']],cwd=repo,stderr=subprocess.DEVNULL)
        line=contents.decode().splitlines()[finding['StartLine']-1]
        match=re.fullmatch(r'\s*"([^"]+)": "([a-f0-9]{64})",?\s*',line)
        if not match:return False
        filename,value=match.groups()
        blob=subprocess.check_output(['git','show',commit+':'+filename],cwd=repo,stderr=subprocess.DEVNULL)
        return hashlib.sha256(blob).hexdigest()==value
    except (KeyError,ValueError,IndexError,subprocess.SubprocessError):return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',required=True);parser.add_argument('--repository',type=Path,default=ROOT)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='internpilot-secret-scan-') as temporary:
        report=Path(temporary)/'redacted.json'
        result=subprocess.run([args.binary,'git',str(args.repository.resolve()),'--redact=100','--gitleaks-ignore-path='+str(ROOT/'.gitleaksignore'),'--report-format=json','--report-path='+str(report)],capture_output=True,text=True)
        if result.returncode not in (0,1):raise SystemExit('Secret scan failed to execute; diagnostic values withheld')
        findings=json.loads(report.read_text()) if report.exists() else []
        verified=[item for item in findings if verified_checksum(args.repository,item)]
        unresolved=[{key:item.get(key) for key in ('RuleID','File','StartLine','Commit','Fingerprint')} for item in findings if item not in verified]
        summary={'scanner':'gitleaks 8.24.3','history':'reachable fetched refs','verified_checksums':len(verified),
                 'unresolved':unresolved,'passed':not unresolved,'redaction':'Secret and Match values intentionally excluded',
                 'limitation':'Pattern scanning does not prove absence of all secrets, personal data, deleted forks or unreachable refs'}
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'passed':summary['passed'],'unresolved':len(unresolved),'verified_checksums':len(verified)}))
        return 1 if unresolved else 0


if __name__=='__main__':raise SystemExit(main())
