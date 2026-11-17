# Agent host adapters

The mailbox protocol is host-independent: JSON files, the dependency gate (`python3`) and Git are all it needs. This reference maps the host-specific parts for Codex, Claude Code and GitHub Copilot. Use only tools the current host actually exposes; when a capability below is absent, fall back to mailbox files and report `delivery_unconfirmed` instead of improvising another channel.

In the skills, "thread" means one host session or conversation, whatever the host calls it.

## Workspace entry points

| Concern | Codex | Claude Code | GitHub Copilot (CLI and VS Code) |
| --- | --- | --- | --- |
| Instructions | `AGENTS.md` | `CLAUDE.md`, which imports `AGENTS.md` | `AGENTS.md` |
| Skills | `.agents/skills/` | `.claude/skills/<skill>` links | `.github/skills/<skill>` links, `.agents/skills/` |
| Invoke a skill | `$<skill>` | `/<skill>` | `/<skill>` |

`AGENTS.md` and `.agents/skills/` are the single source. `.claude/skills/<skill>` and `.github/skills/<skill>` are per-skill symlinks to `.agents/skills/<skill>`; never copy a skill into them. When adding a skill, add both links. Skill directory names equal the frontmatter `name` (lowercase letters, digits, hyphens; at most 64 characters) and descriptions stay under 1024 characters, the strictest limits among the three hosts.

## Session identity

Register the ID the host itself reports as `session_id`; never derive one from a title, timestamp or file name. If the host gives none, set `session_id` to null as README.md prescribes.

The dependency gate delivers only to a non-null endpoint. A worker whose host reports no ID therefore generates one UUID, registers it as `agent_id` with `agent_id_source: self_assigned`, and reuses that same value for every later `validate`. This is a mailbox endpoint, not a claim about the host session: keep `session_id` null and never present the UUID as a host ID.

| Host | Where the session learns its own ID | `host` | `transport` |
| --- | --- | --- | --- |
| Codex | Its thread ID as reported by the host's thread tools | `Codex` | `codex_tui` |
| Claude Code | The expanded session ID line in either mailbox skill body; otherwise not exposed | `Claude Code` | `claude_sessions` |
| Copilot CLI | `/session id`, or `COPILOT_AGENT_SESSION_ID` in its shell commands | `GitHub Copilot` | `mailbox_files` |
| Copilot in VS Code | Not exposed: null `session_id` plus a self-assigned `agent_id` | `GitHub Copilot` | `mailbox_files` |

The dependency gate matches a worker by `session_id` or `agent_id` plus its project directory, so these values work the same for every host.

## Session messaging

| Operation | Codex | Claude Code | GitHub Copilot |
| --- | --- | --- | --- |
| List sessions | `list_threads` | `ListAgents` | not available |
| Send a message | `send_message_to_thread` | `SendMessage` | not available |
| Read a session | `read_thread` | not available | not available |
| Wait for replies | `wait_threads` | no blocking wait; replies arrive as new messages | not available |

- Codex thread tools are often exposed under `mcp__codex_tui`.
- Claude Code reaches other Claude Code sessions of the same user on the same machine. It cannot read another session's transcript, so confirm receipt through the mailbox reply or the session's direct answer.
- Copilot has no tool for messaging another independent session (verified on Copilot CLI 1.0.95). Its `list_agents`, `read_agent` and `write_agent` tools reach only background agents inside the current session. Treat every Copilot session as file-only: publish the mailbox message, report `delivery_unconfirmed` and give the user the exact message-file path to hand to that worker. If a later Copilot version exposes session tools, verify them by name and description before relying on them.
- No host lists or messages sessions of a different host. A mixed fleet (for example a Claude Code orchestrator with Codex workers) is coordinated through mailbox files, with the user relaying the message path where no shared transport exists. A session being invisible to your host is a visibility limit, not evidence that it is absent.
