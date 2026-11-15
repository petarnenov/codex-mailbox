"""Read-only mailbox projection. No Jira access and no writes to mailbox data."""
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).parent
STATUSES = ('pending', 'in_progress', 'blocked', 'awaiting_verification', 'verified_done')


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def records(value, field):
    """Accept documented list, wrapped list or keyed-object snapshot formats."""
    if isinstance(value, dict):
        value = value.get(field, value)
        if isinstance(value, dict):
            return [dict(v, **({'key': k} if 'key' not in v else {})) for k, v in value.items() if isinstance(v, dict)]
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def strings(value):
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def read_json(root, path, warnings):
    try:
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError('symlink/outside data root')
        if path.stat().st_size > 4_000_000:
            raise ValueError('exceeds 4 MB limit')
        return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number: ' + value)))
    except (OSError, ValueError) as exc:
        warnings.append(f'{path.relative_to(root)}: {exc}')
        return None


def estimate_range(value):
    if isinstance(value, dict) and all(number(value.get(k)) for k in ('low', 'likely', 'high')):
        if value['low'] <= value['likely'] <= value['high']:
            return {k: value[k] for k in ('low', 'likely', 'high')}
    return None


def evidence(value):
    return bool(value.get('evidence') or value.get('acceptance_criterion_evidence') or value.get('acceptance_criteria_evidence'))


def verification_passed(value):
    verification = value.get('verification', value.get('verification_outcome'))
    if isinstance(verification, dict):
        verification = verification.get('outcome', verification.get('status'))
    return verification in ('passed', 'verified', 'pass') and evidence(value)


def metrics(issues, complete, model):
    counts = Counter(i['local_status'] for i in issues)
    total = len(issues)
    verified = sum(i['verified'] for i in issues)
    totals = {k: 0.0 for k in ('low', 'likely', 'high')}
    remaining = totals.copy()
    actuals = []
    for issue in issues:
        estimate = issue['estimate'] or {k: model[k] * model['review_multiplier'] for k in totals}
        for key in totals:
            totals[key] += estimate[key]
            if not issue['verified']:
                remaining[key] += estimate[key]
        if issue['actual_machine_hours'] is not None:
            actuals.append(issue['actual_machine_hours'])
    return {'known_issues': total, 'verified_issues': verified, 'status_counts': dict(counts),
            'scope_complete': complete, 'percent': round(100 * verified / total, 1) if complete and total else None,
            'estimate': {k: round(v, 2) for k, v in totals.items()} if total else None,
            'remaining_estimate': {k: round(v, 2) for k, v in remaining.items()} if total else None,
            'estimate_basis': 'Complete enumerated issue scope' if complete and total else 'Known issue subset only; full estimate unavailable',
            'explicit_estimates': sum(i['estimate'] is not None for i in issues),
            'actual_machine_hours': round(sum(actuals), 2) if actuals else None, 'measured_issues': len(actuals)}


def build_dashboard(root, model=None, mode='live'):
    root = Path(root)
    model = model or {'low': 0.5, 'likely': 1.5, 'high': 4.0, 'review_multiplier': 1.25}
    warnings, projects, tasks, epics, raw_issues, reported, external = [], {}, [], [], [], [], []

    def project(pid, name=None, registered=False):
        if not isinstance(pid, str) or not pid:
            warnings.append('Invalid project identifier ignored')
            return
        name = name if isinstance(name, str) else pid
        if pid == 'orchestrator':
            name = 'Mailbox coordination'
        entry = projects.setdefault(pid, {'id': pid, 'name': name or pid, 'registered': False, 'kind': 'coordination' if pid == 'orchestrator' else 'project',
                                         'reported_estimate': None, 'reported_actual_machine_hours': None})
        if registered:
            entry.update(name=name or pid, registered=True)
        return entry

    def reported_stats(data, source, project_id=None, epic_key=None):
        if not isinstance(data, dict):
            return
        stats = {k: data[k] for k in ('metrics', 'statistics', 'progress', 'totals', 'counts', 'percent',
                 'total_issues', 'verified_done', 'pending', 'in_progress', 'blocked', 'awaiting_verification',
                 'completion_percentage', 'scope_complete', 'enumeration_complete', 'estimate', 'machine_hours') if k in data}
        if stats:
            reported.append({'source': source, 'project': project_id, 'epic': epic_key,
                             'updated_at': data.get('generated_at', data.get('updated_at')), 'values': stats})
        for field in ('per_project', 'project_metrics', 'projects'):
            children = data.get(field)
            if isinstance(children, dict):
                for pid, child in children.items():
                    project(pid)
                    reported_stats(child, source, pid, epic_key)
            elif isinstance(children, list):
                for child in children:
                    if isinstance(child, dict) and isinstance(child.get('project', child.get('id')), str):
                        pid = child.get('project', child.get('id'))
                        project(pid)
                        reported_stats(child, source, pid, epic_key)
        if project_id and (p := project(project_id)):
            p['reported_estimate'] = estimate_range(data.get('codex_estimate_hours')) or p['reported_estimate']
            actual = data.get('actual_machine_hours')
            if number(actual):
                p['reported_actual_machine_hours'] = actual

    inventory = read_json(root, root / 'projects.json', warnings)
    for item in records(inventory, 'projects'):
        project(item.get('id'), item.get('name'), True)
    for path in sorted((root / 'projects').glob('*.json')):
        data = read_json(root, path, warnings)
        if isinstance(data, dict):
            pid = data.get('id', path.stem)
            if not isinstance(pid, str) or not pid:
                warnings.append(f'{path.name}: invalid project id')
                continue
            project(pid, data.get('name'))
            reported_stats(data, str(path.relative_to(root)), pid)
    for path in sorted((root / 'tasks').glob('*/*.json')):
        data = read_json(root, path, warnings)
        if not isinstance(data, dict):
            continue
        pid = data.get('project', path.parent.name)
        if not isinstance(pid, str) or not pid or not isinstance(data.get('id', path.stem), str):
            warnings.append(f'{path.name}: invalid task identity')
            continue
        project(pid)
        tasks.append({'id': data.get('id', path.stem), 'project': pid, 'title': data.get('title', path.stem),
                      'status': data.get('status', 'pending'), 'issue_key': data.get('issue_key'),
                      'epic_key': data.get('epic_key'), 'depends_on': strings(data.get('depends_on')),
                      'evidenced': data.get('status') == 'done' and evidence(data),
                      'updated_at': data.get('updated_at')})
    task_map = {t['id']: t for t in tasks}
    for folder in sorted((root / 'epics').glob('*')):
        if not folder.is_dir():
            continue
        scope = read_json(root, folder / 'scope.json', warnings) if (folder / 'scope.json').exists() else {}
        scope = scope if isinstance(scope, dict) else {}
        key = scope.get('epic_key', scope.get('key', folder.name))
        if not isinstance(key, str):
            warnings.append(f'{folder.name}: invalid epic key')
            key = folder.name
        dependencies = scope.get('external_dependencies', [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if isinstance(dependency, str):
                    external.append({'key': dependency, 'epic': key})
                elif isinstance(dependency, dict) and isinstance(dependency.get('key'), str):
                    external.append({'key': dependency['key'], 'epic': key})
        complete = scope.get('enumeration_complete', scope.get('scope_complete')) is True
        declared = strings(scope.get('issue_keys', scope.get('in_scope_issue_keys', scope.get('issues'))))
        issue_path = folder / 'issues.json'
        items = read_json(root, issue_path, warnings) if issue_path.exists() else None
        shape = items.get('issues', items) if isinstance(items, dict) else items
        if not isinstance(shape, (list, dict)) or any(not isinstance(v, dict) for v in (shape.values() if isinstance(shape, dict) else shape or [])):
            warnings.append(f'{key}: missing, unreadable or malformed issue snapshot; scope incomplete')
            complete = False
        items = records(items, 'issues')
        valid_items = [i for i in items if isinstance(i.get('key', i.get('issue_key')), str)]
        if len(valid_items) != len(items):
            warnings.append(f'{key}: issue records with invalid keys ignored')
            complete = False
        items = valid_items
        actual_keys = [i.get('key', i.get('issue_key')) for i in items]
        missing = set(declared) - set(actual_keys)
        if missing:
            warnings.append(f'{key}: missing issue records: {", ".join(sorted(missing))}')
            complete = False
        epics.append({'key': key, 'title': scope.get('title', scope.get('summary', key)),
                      'scope_complete': complete, 'issue_keys': sorted(set(actual_keys + declared) - {None}),
                      'updated_at': scope.get('latest_sync_at', scope.get('updated_at'))})
        for item in items:
            item = dict(item)
            item['_epic'] = key
            raw_issues.append(item)
        for missing_key in missing:
            raw_issues.append({'key': missing_key, '_epic': key, '_missing': True})
        progress_path = folder / 'progress.json'
        if progress_path.exists():
            reported_stats(read_json(root, progress_path, warnings), str(progress_path.relative_to(root)), epic_key=key)
    issues = {}
    for item in raw_issues:
        key = item.get('key', item.get('issue_key'))
        if not isinstance(key, str):
            warnings.append('Issue without a string key ignored')
            continue
        pids = sorted(set(strings(item.get('projects', item.get('affected_projects')))))
        for pid in pids:
            project(pid)
        linked = strings(item.get('task_ids', item.get('local_task_ids')))
        status = item.get('local_status', 'pending')
        if status not in STATUSES:
            status = 'pending'
        verified = status == 'verified_done' and verification_passed(item) and all(t in task_map and task_map[t]['evidenced'] for t in linked)
        if status == 'verified_done' and not verified:
            status = 'awaiting_verification'
        source_status = item.get('source_status', item.get('jira_status', 'Unknown'))
        if isinstance(source_status, dict):
            source_status = source_status.get('name', 'Unknown')
        normalized = {'key': key, 'title': item.get('title', item.get('summary', key)), 'epic_keys': [item['_epic']],
                      'projects': pids, 'local_status': status, 'source_status': str(source_status), 'verified': verified,
                      'dependencies': strings(item.get('depends_on', item.get('dependencies'))), 'task_ids': linked,
                      'estimate': estimate_range(item.get('codex_estimate_hours')),
                      'actual_machine_hours': item.get('actual_machine_hours') if number(item.get('actual_machine_hours')) else None,
                      'missing_record': item.get('_missing', False), 'conflict': False}
        if key not in issues:
            issues[key] = normalized
        else:
            previous = issues[key]
            for field in ('projects', 'epic_keys', 'dependencies', 'task_ids'):
                previous[field] = sorted(set(previous[field] + normalized[field]))
            if any(previous[k] != normalized[k] for k in ('local_status', 'verified', 'estimate', 'actual_machine_hours')):
                previous.update(verified=False, local_status='awaiting_verification', conflict=True, estimate=None, actual_machine_hours=None)
                warnings.append(f'{key}: conflicting snapshots; verification and estimates require reconciliation')
    issue_list = list(issues.values())
    complete = bool(epics) and all(e['scope_complete'] for e in epics) and not any(i['missing_record'] for i in issue_list)
    for e in epics:
        selected = [i for i in issue_list if e['key'] in i['epic_keys']]
        e['progress'] = metrics(selected, e['scope_complete'], model)
    for p in projects.values():
        selected = [i for i in issue_list if p['id'] in i['projects']]
        p['issue_keys'] = [i['key'] for i in selected]
        p['task_ids'] = [t['id'] for t in tasks if t['project'] == p['id']]
        p['progress'] = metrics(selected, complete, model)
        # Project allocation prevents double-counting multi-project work.
        allocated = {k: 0.0 for k in ('low', 'likely', 'high')}
        for i in selected:
            estimate = i['estimate'] or {k: model[k] * model['review_multiplier'] for k in allocated}
            for k in allocated:
                allocated[k] += estimate[k] / len(i['projects'])
        p['allocated_estimate'] = {k: round(v, 2) for k, v in allocated.items()} if selected else None
    dependencies = [{'from': dep, 'to': i['key'], 'kind': 'depends_on', 'unresolved': dep not in issues}
                    for i in issue_list for dep in i['dependencies']]
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'mode': mode, 'warnings': warnings,
            'projects': sorted(projects.values(), key=lambda p: p['name']), 'epics': epics, 'issues': issue_list,
            'tasks': tasks, 'dependencies': dependencies, 'external_dependencies': external,
            'task_dependencies': [{'from': dep, 'to': t['id'], 'kind': 'task_dependency', 'unresolved': dep not in task_map} for t in tasks for dep in t['depends_on']],
            'reported_statistics': reported,
            'totals': metrics(issue_list, complete, model), 'estimate_method': model}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        payload = json.dumps(data, allow_nan=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/healthz':
            return self.reply(200, {'status': 'ok'})
        if parsed.path == '/api/dashboard':
            query = parse_qs(parsed.query)
            try:
                model = {k: float(query.get(k, [v])[0]) for k, v in {'low': .5, 'likely': 1.5, 'high': 4, 'review_multiplier': 1.25}.items()}
                if not all(number(v) and v <= 1000 for v in model.values()) or not model['low'] <= model['likely'] <= model['high'] or model['review_multiplier'] < 1:
                    raise ValueError('Model requires 0 ≤ low ≤ likely ≤ high ≤ 1000 and 1 ≤ review multiplier ≤ 1000')
                mode = query.get('mode', ['live'])[0]
                if mode not in ('live', 'demo'):
                    raise ValueError('Unknown mode')
                root = ROOT / 'demo' if mode == 'demo' else Path(os.environ.get('MAILBOX_ROOT', '/data'))
                return self.reply(200, build_dashboard(root, model, mode))
            except (ValueError, TypeError) as exc:
                return self.reply(400, {'error': {'code': 'invalid_request', 'message': str(exc)}})
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/theme.js': ('theme.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if parsed.path in files:
            filename, mime = files[parsed.path]
            return self.reply(200, (ROOT / 'static' / filename).read_bytes(), mime)
        return self.reply(404, {'error': {'code': 'not_found', 'message': 'Not found'}})

    def reject_mutation(self):
        self.reply(405, {'error': {'code': 'read_only', 'message': 'This dashboard is read-only'}})
    do_POST = do_PUT = do_PATCH = do_DELETE = reject_mutation


def main():
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()


if __name__ == '__main__':
    main()
