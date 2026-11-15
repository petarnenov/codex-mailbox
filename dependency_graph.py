"""Typed, read-only graph projection; completion is never inferred from edges."""


def build_graph(root, projects, epics, issues, tasks, raw_issues, external, read_json, warnings):
    nodes, edges = {}, {}
    epic_ids = {e['key'] for e in epics}
    issue_ids = {i['key'] for i in issues}

    def strings(value):
        return [value] if isinstance(value, str) else [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

    def node(key, label, kind, status='unknown', ready=False, **meta):
        result = dict(id=key, label=label, kind=kind, status=status, ready=ready,
                      projects=[], teams=[], epic_keys=[], evidence=[], source='',
                      updated_at=None, unmet_prerequisites=[])
        result.update(meta)
        nodes[key] = result
        return result

    def identity(key):
        return ('issue:' if key in issue_ids else 'epic:' if key in epic_ids else 'issue:') + key

    def endpoint(key, epic=None):
        if key not in nodes:
            kind = key.split(':', 1)[0]
            node(key, key.split(':', 1)[1], kind, 'unresolved', unresolved=True,
                 epic_keys=[epic] if epic else [])
            warnings.append(f'{key}: unresolved graph endpoint')
        return nodes[key]

    def edge(start, end, kind='membership', condition='', evidence=None, source='', epic=None):
        endpoint(start, epic)
        endpoint(end, epic)
        key = (start, end, kind)
        if key not in edges:
            edges[key] = dict(from_=start, to=end, kind=kind, condition=condition,
                              evidence=strings(evidence), source=source, unresolved=False)
            edges[key]['from'] = edges[key].pop('from_')
        else:
            previous = edges[key]
            previous['evidence'] = sorted(set(previous['evidence'] + strings(evidence)))
            if condition and condition not in previous['condition']:
                previous['condition'] = '; '.join(filter(None, [previous['condition'], condition]))

    for p in projects:
        node('project:' + p['id'], p['name'], 'project', projects=[p['id']], teams=p['teams'])
    for e in epics:
        node('epic:' + e['key'], e['key'], 'epic', epic_keys=[e['key']], updated_at=e['updated_at'],
             issue_type=e.get('issue_type'), source_status=e.get('source_status', 'Unknown'))
    for i in issues:
        node('issue:' + i['key'], i['key'], 'issue', i['local_status'], i['verified'] and bool(i['evidence']),
             detail=i['title'], issue_type=i.get('issue_type'), source_status=i['source_status'], projects=i['projects'], teams=i['teams'], epic_keys=i['epic_keys'],
             source=', '.join(i['sources']), evidence=i['evidence'], updated_at=i['updated_at'], unresolved=i['missing_record'])
    for t in tasks:
        node('task:' + t['id'], t['title'], 'task', t['status'], t['evidenced'] and bool(t['evidence']),
             issue_keys=t['issue_keys'], mapping_kind=t['mapping_kind'],
             projects=[t['project']], teams=t['teams'], epic_keys=t['epic_keys'],
             source=t['source'], evidence=t['evidence'], updated_at=t['updated_at'])

    parents = {}
    for raw in raw_issues:
        key = raw.get('key', raw.get('issue_key'))
        parent = raw.get('parent_key')
        if parent is None and isinstance(raw.get('parent'), dict):
            parent = raw['parent'].get('key')
        if isinstance(parent, str) and parent:
            parents.setdefault(key, set()).add(parent)
    for i in issues:
        key = 'issue:' + i['key']
        candidates = parents.get(i['key'], set())
        if len(candidates) > 1:
            nodes[key].update(ready=False, status='conflicting parents')
            warnings.append(f"{i['key']}: conflicting parents; hierarchy requires reconciliation")
        if candidates:
            for parent in sorted(candidates):
                edge(identity(parent), key, source=nodes[key]['source'])
        else:
            for epic in i['epic_keys']:
                edge('epic:' + epic, key, source=nodes[key]['source'])
        for p in i['projects']:
            for epic in i['epic_keys']:
                edge('project:' + p, 'epic:' + epic)
        for task in i['task_ids']:
            edge(key, 'task:' + task)
        for prerequisite in i['dependencies']:
            edge(identity(prerequisite), key, 'requires', source=nodes[key]['source'])
    for t in tasks:
        if not t['issue_keys']:
            if t['epic_keys']:
                for epic in t['epic_keys']:
                    edge('epic:' + epic, 'task:' + t['id'])
            else:
                edge('project:' + t['project'], 'task:' + t['id'])
        for epic in t['epic_keys']:
            edge('project:' + t['project'], 'epic:' + epic)
        for prerequisite in t['depends_on']:
            edge('task:' + prerequisite, 'task:' + t['id'], 'requires', source=t['source'])

    for raw in raw_issues:
        current = raw.get('key', raw.get('issue_key'))
        links = raw.get('jira_links', raw.get('issuelinks', raw.get('links', [])))
        if not isinstance(links, list):
            warnings.append(f'{current}: invalid Jira relationship list')
            continue
        for link in links:
            if not isinstance(link, dict):
                continue
            relationship = link.get('type')
            name = relationship.get('name') if isinstance(relationship, dict) else relationship
            if name != 'Blocks':
                continue
            for direction in ('inward', 'outward'):
                other = link.get(direction)
                if other is None and isinstance(link.get(direction + 'Issue'), dict):
                    other = link[direction + 'Issue'].get('key')
                if not isinstance(other, str) or not other:
                    continue
                a, b = (other, current) if direction == 'inward' else (current, other)
                edge(identity(a), identity(b), 'requires', condition='Jira Blocks',
                     source=raw.get('_source', ''), epic=raw.get('_epic'))
    for item in external:
        other = identity(item['key'])
        n = endpoint(other, item['epic'])
        if n.get('unresolved'):
            n['source'] = f"epics/{item['epic']}/scope.json"
            n['evidence'] = strings(item.get('evidence')) + strings(item.get('decision_path'))
        relation = item.get('relationship')
        name = relation.get('name') if isinstance(relation, dict) else relation
        direction = item.get('direction')
        if name == 'Blocks' and direction in ('inward', 'outward'):
            start, end = (other, 'epic:' + item['epic']) if direction == 'inward' else ('epic:' + item['epic'], other)
            edge(start, end, 'requires', condition='Jira Blocks',
                 source=f"epics/{item['epic']}/scope.json", epic=item['epic'])
        elif n.get('unresolved'):
            n['status'] = 'relationship direction unknown'
            n['contextual'] = True

    milestone_records = {}
    specifications = []
    for epic in epics:
        path = root / 'epics' / epic['key'] / 'dependencies.json'
        if not path.exists():
            continue
        source = str(path.relative_to(root))
        spec = read_json(root, path, warnings)
        if not isinstance(spec, dict):
            warnings.append(f'{source}: invalid dependency graph')
            continue
        for collection in ('nodes', 'edges'):
            if not isinstance(spec.get(collection, []), list):
                warnings.append(f'{source}: invalid graph {collection}')
                spec[collection] = []
        specifications.append((epic['key'], source, spec))
        for item in spec.get('nodes', []):
            if not isinstance(item, dict):
                warnings.append(f'{source}: invalid milestone node')
                continue
            key = item.get('id')
            valid_metadata = all(isinstance(item.get(k, []), list) and all(isinstance(v, str) for v in item.get(k, []))
                                 for k in ('projects', 'teams', 'evidence'))
            if not isinstance(key, str) or not key.startswith('milestone:') or not key[10:] or not valid_metadata:
                warnings.append(f'{source}: invalid milestone identity or metadata')
                continue
            if not isinstance(item.get('label', key), str) or not isinstance(item.get('status', 'unknown'), str):
                warnings.append(f'{source}: invalid milestone label/status')
                continue
            if key in milestone_records:
                if milestone_records[key] != item:
                    nodes[key].update(ready=False, status='conflicting snapshots')
                    warnings.append(f'{key}: conflicting milestone snapshots')
                nodes[key]['epic_keys'] = sorted(set(nodes[key]['epic_keys'] + [epic['key']]))
                continue
            milestone_records[key] = item
            refs = sorted({ref.strip() for ref in item.get('evidence', []) if ref.strip()})
            ready = item.get('status') == 'verified' and item.get('verification') == 'passed' and bool(refs)
            node(key, item.get('label', key), 'milestone', 'verified' if ready else 'unknown', ready,
                 projects=item.get('projects', []), teams=item.get('teams', []), epic_keys=[epic['key']],
                 evidence=refs, source=source, updated_at=item.get('updated_at', spec.get('updated_at')))
    for epic, source, spec in specifications:
        for item in spec.get('edges', []):
            if not isinstance(item, dict):
                warnings.append(f'{source}: invalid dependency edge')
                continue
            start, end = item.get('from'), item.get('to')
            canonical = lambda value: isinstance(value, str) and ':' in value and value.split(':', 1)[0] in ('project', 'epic', 'issue', 'task', 'milestone') and bool(value.split(':', 1)[1])
            if not canonical(start) or not canonical(end) or item.get('kind') != 'requires' or not isinstance(item.get('condition', ''), str) or not isinstance(item.get('evidence', []), list) or not all(isinstance(v, str) for v in item.get('evidence', [])):
                warnings.append(f'{source}: invalid dependency edge identity/kind/metadata')
                continue
            edge(start, end, 'requires', condition=item.get('condition', ''), evidence=item.get('evidence'), source=source, epic=epic)

    for e in edges.values():
        e['unresolved'] = bool(nodes[e['from']].get('unresolved') or nodes[e['to']].get('unresolved'))
        if e['kind'] == 'requires' and not nodes[e['from']]['ready']:
            nodes[e['to']]['unmet_prerequisites'].append(e['from'])
    for n in nodes.values():
        n['unmet_prerequisites'] = sorted(set(n['unmet_prerequisites']))
    return {'nodes': list(nodes.values()), 'edges': list(edges.values())}
