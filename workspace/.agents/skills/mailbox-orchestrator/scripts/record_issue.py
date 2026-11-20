#!/usr/bin/env python3
"""Record Epic issue prerequisites and verification in the shape the dashboard reads.

Usage:
  record_issue.py --epic <KEY> --issue <KEY> depends-on <KEY>...
  record_issue.py --epic <KEY> --issue <KEY> verified --evidence <ref>... [--verifier <who>]

The dashboard counts an issue as verified only when `local_status` is
`verified_done`, `verification.status` is `passed` and `evidence` is non-empty.
It draws execution prerequisites only from `depends_on`; free-text blockers such
as "depends on GEO-1" create no graph edge, so unmet prerequisites show as zero.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MAILBOX = Path(__file__).resolve().parents[4]


def issues_path(root, epic):
    return root / 'epics' / epic / 'issues.json'


def find_issue(document, key):
    for issue in document['issues']:
        if issue.get('key') == key:
            return issue
    raise ValueError(f'Issue {key} is not in the Epic snapshot')


def set_prerequisites(issue, prerequisites, now):
    if issue['key'] in prerequisites:
        raise ValueError('An issue cannot depend on itself')
    issue['depends_on'] = sorted(set(prerequisites))
    issue['blockers'] = [b for b in issue.get('blockers') or [] if not b.lower().startswith('depends on')]
    issue['updated_at'] = now


def set_verified(issue, evidence, verifier, now):
    references = [ref.strip() for ref in evidence if ref.strip()]
    if not references:
        raise ValueError('Verified issues need at least one evidence reference')
    issue['local_status'] = 'verified_done'
    issue['verification'] = {'status': 'passed', 'verifier': verifier, 'evidence': references, 'verified_at': now}
    issue['evidence'] = references
    issue['blockers'] = []
    issue['updated_at'] = now


def record(root, epic, key, apply):
    path = issues_path(root, epic)
    document = json.loads(path.read_text())
    apply(find_issue(document, key))
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False))
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=MAILBOX)
    parser.add_argument('--epic', required=True)
    parser.add_argument('--issue', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    depends = commands.add_parser('depends-on')
    depends.add_argument('prerequisites', nargs='+')
    verified = commands.add_parser('verified')
    verified.add_argument('--evidence', nargs='+', required=True)
    verified.add_argument('--verifier', default='orchestrator')
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc).isoformat()
    if args.command == 'depends-on':
        record(args.root, args.epic, args.issue, lambda issue: set_prerequisites(issue, args.prerequisites, now))
    else:
        record(args.root, args.epic, args.issue, lambda issue: set_verified(issue, args.evidence, args.verifier, now))
    print(json.dumps({'epic': args.epic, 'issue': args.issue, 'recorded': args.command}))


if __name__ == '__main__':
    main()
