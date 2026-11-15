# Mailbox dashboard

A local, read-only delivery dashboard for every project with statistics in `codex-mailbox`. Python standard-library backend, buildless HTML/CSS/JavaScript frontend, one Docker container. No runtime package dependencies and no Jira connection or writes.

## Start

Requirements: Docker with Compose. Clone this **application** into its own directory; keep your mailbox **data** in a separate existing directory.

```sh
git clone https://github.com/petarnenov/codex-mailbox.git
cd codex-mailbox
cp .env.example .env
```

Edit `.env` and set `MAILBOX_ROOT` to the absolute path of your mailbox data directory. It should contain `projects.json` and any `projects/`, `epics/` or `tasks/` snapshots. The application repository is not the mailbox data directory. Do not copy private data or session records into the repository.

```sh
docker compose up -d --build
```

Open **http://localhost:17171**. The service is published only on `127.0.0.1`, runs as an unprivileged user with a read-only root filesystem, and mounts the configured data directory at `/data:ro`. Compose requires an explicit `MAILBOX_ROOT`; it will not silently mount a guessed location.

Alternatively, set the path for a single invocation:

```sh
MAILBOX_ROOT=/absolute/path/to/mailbox-data docker compose up -d --build
```

To try the application without private mailbox data, use the shipped synthetic fixture:

```sh
MAILBOX_ROOT="$PWD/demo" docker compose up -d --build
```

Then check **Explore demo** in the interface for the explicitly labeled demo view. No credentials are needed. `.env` and local mailbox data directories are ignored by Git.

Refresh reads current files; no background watcher or Jira synchronization is installed. `docker compose down` stops the dashboard. It does not change mailbox data. Port conflicts are reported by Docker; do not stop unrelated services.

Dark theme is the default on a fresh visit. The header theme toggle offers light mode and remembers an explicit choice locally; a blocking head script selects it before the stylesheet paints.

The sticky header contains five page tabs: **Overview**, **Dependencies**, **Tasks**, **Estimates**, and **Sources**. Only the active page is displayed. Filters remain selected across tabs. URLs such as `/#dependencies` are shareable local deep links; browser back/forward restores the selected page. Arrow keys, Home and End navigate tabs. On narrow screens only the tab strip scrolls horizontally.

## What the dashboard shows

- Every registry project, plus unregistered projects discovered in project snapshots, task directories, issue project mappings, and aggregate per-project statistics.
- All available Epic/issue snapshots, local tasks even without Jira mapping, and aggregate-only reported statistics with provenance.
- Project → Epic → issue membership, task membership, and prerequisite → dependent arrows. Cycles, unresolved dependencies and nodes outside the selected filter stay visible. Long graphs scroll.
- Unique verified issue progress, separate Jira/local statuses, project allocations, total modeled and remaining effort, explicit estimates and known measured time.
- Empty scope remains **unavailable**, not 0% or 100%. No live data is invented. The checkbox **Explore demo** switches to isolated fixture files shipped in `demo/`; a prominent banner distinguishes them. It never writes or copies demo data to the mailbox.

## Agent compatibility

The dashboard is independent of the agent host. Claude Code, Codex, or another local tool can produce the same JSON snapshots using the contract below; the application only reads files. Codex-specific session discovery, messaging and orchestration adapters are not bundled with this repository. The displayed Codex effort model is a planning convention, not a connection to an agent or billing API.

## Snapshot contract

The backend reads only these JSON paths, with a 4 MB per-file bound. Paths outside the data root and symlink files are rejected. Malformed records produce data-quality warnings; valid sources continue to display. Unknown fields are not used to infer completion. Writers should publish snapshots atomically as required by the mailbox protocol.

`projects.json`:

```json
{"projects":[{"id":"backend","name":"Backend"}]}
```

`projects/<id>.json`: project metadata plus optional `statistics`, `metrics`, `progress`, `totals`, `counts`, `codex_estimate_hours` (`low`, `likely`, `high`) and `actual_machine_hours`. Aggregate stats are displayed as **reported**, never substituted for evidence-based issue metrics. `generated_at` or `updated_at` supplies provenance time.

`epics/<key>/scope.json`:

```json
{
  "epic_key":"EXAMPLE-1",
  "title":"An imported Epic",
  "enumeration_complete":true,
  "issue_keys":["EXAMPLE-2"],
  "external_dependencies":["OUTSIDE-1"],
  "latest_sync_at":"2026-11-15T00:00:00Z"
}
```

`epics/<key>/issues.json` accepts an array, `{"issues": [...]}`, or an object keyed by issue key. An issue:

```json
{
  "key":"EXAMPLE-2", "title":"Work item", "projects":["backend"],
  "source_status":"In Progress", "local_status":"in_progress",
  "task_ids":["task-uuid"], "depends_on":["OUTSIDE-1"],
  "verification":{"outcome":"passed"}, "evidence":["local/artifact/path"],
  "codex_estimate_hours":{"low":1,"likely":2,"high":4},
  "actual_machine_hours":1.3
}
```

Aliases: `issue_key`, `summary`, `affected_projects`, `local_task_ids`, `jira_status`, `verification_outcome`, `acceptance_criterion_evidence` / `acceptance_criteria_evidence`. `dependencies` is accepted as a string array equivalent to `depends_on`. Scope aliases: `key`, `scope_complete`, `in_scope_issue_keys`. External dependencies can also be objects with a `key`; these are Epic-level relationships, not automatically in-scope issues.

`tasks/<project>/<uuid>.json`: `id`, `project` (defaults to directory name), `title`, `status`, optional `issue_key`, `epic_key`, `depends_on` task IDs, `evidence`, `updated_at`. Task `done` plus nonempty evidence marks evidenced completion. A task alone does not establish an issue's acceptance criteria.

`epics/<key>/progress.json`: preserved reported fields `metrics`, `statistics`, `progress`, `totals`, `counts`, `percent`, status counts, scope completeness, `estimate`, `machine_hours`. Nested project aggregates may use `per_project`, `project_metrics`, or `projects` as an object keyed by project ID, or a list of objects with `project` / `id`. Project snapshots support the same fields. No estimate is inferred from story points or ordinary Jira hours.

### Verification and scope

An issue is verified only if:

1. `local_status` is `verified_done`;
2. verification is `passed`, `pass` or `verified` and evidence is nonempty;
3. every linked required local task exists, is `done`, and has evidence.

Otherwise `verified_done` is displayed as awaiting verification. Evidence references are treated as recorded assertions, not opened or executed by the dashboard; the orchestrator owns validating the underlying artifacts. Contradictory duplicate statuses, estimates or measurements produce a warning and suppress verified completion/explicit estimates/measurements until reconciled. Duplicate issues merge memberships and dependencies and count only once overall.

Progress = verified unique issues / known unique issues, only when scope enumeration is explicitly complete. Missing declared issue records remain visible as placeholders and invalidate scope completeness. Zero issues has no percentage. Overall completeness requires all imported Epics complete; unknown or unimported future scope is not invented. Reported aggregate figures are never merged into this denominator. Project memberships may overlap; do not add project issue counts into the portfolio total.

### Codex estimates

The editable model uses **low / likely / high hours per issue × review multiplier** (defaults 0.5 / 1.5 / 4 × 1.25). These are illustrative assumptions, not benchmark measurements or calibrated forecasts. Explicit `codex_estimate_hours` override the model for an issue. Shared issue estimates are allocated equally across affected projects; unmapped issues remain in the overall total. Low/likely/high are scenario bounds, not statistical confidence intervals.

Only known enumerated scope is modeled. Incomplete scope is labeled a known subset; task-only and aggregate-only projects have no inferred whole-project estimate. Explicit reported project estimates are displayed separately and are not added to issue estimates. The hypothetical issue-count calculator works before scope import and is clearly excluded from live statistics. Remaining estimates omit verified issues. Blocked/in-progress issues retain full modeled effort; there is no invented fractional completion.

`actual_machine_hours` must be explicitly recorded measurements. Unknown values remain unknown; a known subset sum includes a measurement coverage count and is never described as total actual time. Machine-hours sum agent execution time, so multiple parallel agents can exceed elapsed wall-clock hours. No token-to-time, message timestamp, or Jira-hour conversion is used.

## API

- `GET /healthz` → `{"status":"ok"}` (process health, not a claim that mailbox data is valid).
- `GET /api/dashboard?mode=live` → `generated_at`, `mode`, `warnings`, `projects`, `epics`, `issues`, `tasks`, `dependencies`, `task_dependencies`, `external_dependencies`, `reported_statistics`, `totals`, `estimate_method`.
- Optional numeric query fields: `low`, `likely`, `high`, `review_multiplier`. Require `0 ≤ low ≤ likely ≤ high ≤ 1000` and `1 ≤ review_multiplier ≤ 1000`.
- `mode=demo` selects the isolated demo fixture. Project/Epic filtering is browser-local; API returns the full snapshot.
- Errors: `{"error":{"code":"...","message":"..."}}`. Mutations return 405. Static assets are allowlisted. No arbitrary file-serving endpoint.

## Validation

```sh
python3 -m venv .venv
.venv/bin/pip install coverage
.venv/bin/python -m coverage run --branch --source=server -m unittest discover -s tests -v
.venv/bin/python -m coverage report -m
node --check static/app.js
docker compose config
docker compose up -d --build
curl --fail http://localhost:17171/healthz
```

Tests use temporary directories and the separate demo, never mutate live mailbox state. Browser verification covers live empty state, populated demo, filters, model edits, cycles, unresolved nodes, narrow viewport, source warnings and safe text rendering. Local development evidence is excluded from the public repository.

## License

[MIT](LICENSE) — copyright 2026 Petar Nenov.
