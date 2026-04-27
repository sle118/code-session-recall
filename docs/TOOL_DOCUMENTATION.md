# Code Session Recall (CSR) — Complete Documentation

## Overview

**Code Session Recall** (csr) is a lightweight, privacy-first CLI tool for recovering and searching past coding sessions and AI-assisted work. It scans your VS Code workspace and session stores, indexes session metadata and file activity, and provides fast, targeted lookups to help you rediscover prior work without expensive workspace-wide searches.

CSR is inspired by Desi Villanueva's
["I Wasted 68 Minutes a Day Re-Explaining My Code. Then I Built auto-memory."](https://devblogs.microsoft.com/all-things-azure/i-wasted-68-minutes-a-day-re-explaining-my-code-then-i-built-auto-memory/)
and the related [`auto-memory`](https://github.com/dezgit2025/auto-memory)
repository. The shared idea is progressive local recall before expensive
rediscovery. CSR is heavier because VS Code/GitHub Copilot does not expose a
single convenient session-store database like Copilot CLI; it has to recover and
compress context from workspace storage, `state.vscdb`, chat JSONL files, and
extension artifacts.

## Purpose & Use Cases

### Primary Goal
Make session context retrieval **cheap, fast, and local** so you can:
- Surface relevant code context before invoking large language models
- Keep AI prompts focused and reduce token usage
- Recover past commands, checkpoints, and file states
- Maintain full privacy with local-only data storage

### Typical Workflows
1. **Pre-LLM Context Gathering**: Run `csr search <keyword>` or `csr files` to extract targeted context before prompting Copilot
2. **Session Recovery**: Use `csr show <id>` to rehydrate a past session with exact commands, snippets, and state
3. **Periodic Snapshots**: Scheduled `csr scan` runs capture ongoing work for later retrieval
4. **Export & Sharing**: Export indexed sessions for collaboration or archival

## Core Concepts

### Sessions
The primary unit of organization. Each session represents a coding work period and contains:
- **id**: Stable session identifier
- **timestamps**: Start, end, and last-modified times
- **summary**: Natural-language description (if captured)
- **files**: Workspace-relative paths of touched files with small excerpts
- **commands**: Captured terminal commands and shell history
- **checkpoints**: Named snapshots within the session
- **tags/labels**: User or auto-generated categorization

### Files
File records track touched files with metadata:
- **path**: Workspace-relative path
- **last_touched**: Timestamp of last modification
- **diffs/snippets**: Small context excerpts or short diffs for quick review

### Checkpoints
Named snapshots created during a session:
- **checkpoint id/name**: Unique identifier
- **description**: Short note from checkpoint time
- **snapshot**: List of important files and their content hashes

### Index & Metadata
Database health and schema information:
- **schema version**: DB layout version for tracking migrations
- **index stats**: Record counts, last-scan timestamp, error logs

## Installation & Setup

### Basic Setup
1. Ensure Python 3.9+ is installed
2. Install the package once published: `python -m pip install code-session-recall`
3. Run commands via `csr`

For local development or pre-release testing from a clone:

```bash
python -m pip install -e .
csr --help
csr install-instructions
```

The repository-local compatibility form remains available:

```bash
python csr.py --help
```

### VS Code Integration (Optional)
For seamless integration with GitHub Copilot:
1. Copy the content of `AGENTS-TEMPLATE.md` from this repo
2. Add it to your VS Code settings:
   - Open `~/.copilot/copilot-instructions.md` (or `~/.vscode/copilot-instructions.md`)
   - Paste the template content
3. Alternatively, add the template to your workspace notes and reference it from your Copilot config

This teaches Copilot to invoke `csr` automatically when collecting context for responses.

## Command Reference

### scan
Index and catalog sessions from your workspace and VS Code session stores.

```bash
python csr.py scan
```

**What it does:**
- Crawls specified workspace folders
- Extracts session metadata from VS Code storage
- Identifies touched files and small content excerpts
- Indexes terminal history and commands
- Updates the local database with new records

### search
Full-text search across all indexed sessions and artifacts.

```bash
python csr.py search "keyword"
python csr.py search "function_name" --json
```

**Options:**
- `--json`: Output results in JSON format
- `--limit N`: Limit results to N records
- Search term: Any keyword, function name, file path, or phrase

**Returns:**
- Matching sessions with relevant snippets
- File records containing the keyword
- Command history entries

### show
Display detailed information about a specific session.

```bash
python csr.py show <session_id>
python csr.py show <session_id> --json
```

**Returns:**
- Complete session metadata
- All touched files with excerpts
- Captured commands and terminal history
- Checkpoints and snapshots
- Tags and labels

### export
Export sessions or slices for backup, sharing, or archival.

```bash
python csr.py export
python csr.py export --out sessions.ndjson
python csr.py export --session <id> --format json
```

**Options:**
- `--out <file>`: Output file path (default: sessions.ndjson)
- `--session <id>`: Export single session (default: all)
- `--format <format>`: json, ndjson, csv (default: ndjson)

## Roadmap

The tool is currently being moved from an earlier machine/user profile into a
new VS Code Insiders environment. The roadmap therefore starts with discovery:
`csr` should infer storage roots, workspace identity, and chat session ids from
local VS Code/Copilot state instead of hard-coded paths or usernames.

### Implemented Today

The CLI currently exposes:

```bash
python csr.py scan
python csr.py handoff "keyword"
python csr.py handoff
python csr.py ask "question" --json
python csr.py search "keyword" --json
python csr.py list --json --limit 5
python csr.py show <session_id> --json
python csr.py install-instructions
python csr.py export
python csr.py health
```

`health` is currently a lightweight check that reports the index DB path,
whether the default VS Code Stable workspace storage exists, and the current
workspace.

The Copilot chat formatter now performs a first pass of deterministic fact
extraction. For parsed `chatSessions/*.jsonl` sessions it surfaces compact
sections for files, edited files, commands, errors, decisions/next steps,
high-signal lines, and terminal/tool events before recent-turn previews. This is
the extraction layer used by `handoff`. Terminal/tool events that invoke `csr`
itself are filtered so `csr` command output does not get re-indexed as recall
context.

VS Code state scanning also indexes compact `vscode-live` records for
`memento/interactive-session`, `memento/chat-todo-list`, and
`agentSessions.model.cache`. These records expose prompt trails, Copilot todo
state, and agent/subagent session summaries without dumping raw persisted JSON.

`handoff` emits a capped markdown packet for direct agent prompt injection. With
a query it searches matching sessions; without a query it falls back to recent
high-signal indexed sessions.

By default, `handoff`, `search`, and `list` apply current-workspace affinity:
rows whose path or formatted content mention the current working directory are
preferred, and unrelated workspace sessions are hidden when current-workspace
records exist. Use `--all-workspaces` for intentional cross-workspace recall.

If the index is empty, `handoff`, `ask`, and `list` perform one silent local
scan and retry. This supports the intended "run recall first" workflow in fresh
agent sessions. If a `handoff`/`ask` query has no direct matches, it falls back
to recent high-signal sessions instead of returning an empty packet.

For handoff ranking, chat/session sources are preferred over markdown docs when
both match. Docs explain what exists; chat/session sources better capture what
happened.

### Highest Priority

- **VS Code storage discovery**: support Stable (`Code`), Insiders (`Code - Insiders`), and user-supplied roots. Discovery should use environment-derived paths such as `APPDATA`, `TERM_PROGRAM_VERSION`, `VSCODE_*`, and terminal/tool metadata captured in Copilot sessions.
- **Session discovery**: continue improving active workspace/session data from `chat.ChatSessionStore.index`, `chatSessions/*.jsonl`, terminal command metadata, and conversation titles rather than hard-coded `WORKSPACE_CURRENT_CHAT_SESSION_ID` values. A first-pass current-workspace affinity filter now exists for query commands.
- **Environment-aware recall**: index Copilot terminal/tool records, including command, cwd, language, exit code, command URI, terminal output, and useful environment variables. This helps future scans locate the right database/session without guessing.
- **Deterministic handoff compression**: continue refining `csr handoff <query>` as a local extractor plus heuristic compressor. It emits compact agent-ready markdown from matched sessions, files, commands, errors, decisions, and next steps. See `docs/HANDOFF_DESIGN.md`.
- **Documentation parity**: keep README, this file, `AGENTS-TEMPLATE.md`, and `csr --help` aligned with actual behavior.

## Roadmap Commands (In Development)

These commands and flags are documented in templates or implied by the current
data model, but are not fully implemented yet:

### handoff
Produce a compact markdown packet for a new agent from persisted local state.

```bash
python csr.py handoff "packet 007"
python csr.py handoff
python csr.py ask "packet 007"
python csr.py handoff "packet 007" --json
python csr.py handoff "packet 007" --limit 20
python csr.py handoff "packet 007" --source vscode-copilot
```

The handoff command scores and extracts high-signal rows: headings, file paths,
commands, errors, decisions, TODO/next-step sentences, terminal tool records,
edited files, and related context. If no query is provided, it uses recent
high-signal indexed sessions.

`ask` is a compatibility alias for `handoff`. It exists because agents often
try natural command names during recall. It does not add LLM behavior or a new
provider; it emits the same deterministic packet.

### install-instructions
Print a ready-to-paste bootstrap prompt and AGENTS.md snippet for activating CSR
in another workspace.

```bash
csr install-instructions
python csr.py install-instructions
```

### files (Planned)
List recently touched files with metadata.

```bash
python csr.py files --json --limit 10
python csr.py files --days 7
```

### checkpoints (Planned)
Search or list named checkpoints across all sessions.

```bash
python csr.py checkpoints --search "deploy"
python csr.py checkpoints --session <id>
```

### enhanced health (Planned)
Run an 8-dimension health check on the local datastore and index.

```bash
python csr.py health
python csr.py health --verbose
```

### schema-check (Planned)
Validate database schema and guide migrations after upgrades.

```bash
python csr.py schema-check
python csr.py schema-check --validate
python csr.py schema-check --migrate
```

### --days (Planned)
Add convenient time filtering across query commands.

```bash
python csr.py search "database" --days 5
python csr.py list --days 3 --json
python csr.py files --days 7
python csr.py checkpoints --days 3
```

## Architecture & Design

### Storage
- **Local-first**: All data stored locally in your workspace
- **Privacy-focused**: No remote sync or cloud uploads by default
- **Raw discovery quarantine**: unsanitized local captures should go under ignored `unsanitized/`; commit only sanitized derivatives
- **Indexing**: SQLite or similar lightweight database for fast queries
- **Session stores**: Integrates with VS Code's local session storage

### Extractors & Extensibility
The csr architecture supports modular extractors for different data sources:
- VS Code session extractors
- Workspace file monitors
- Terminal history collectors
- Custom checkpoint handlers

New extractors and exporters can be added as plugins without modifying core code.

### Data Flow
```
Workspace/Sessions → Extractors → Database → Indexer → Query Interface
                                      ↓
                              Full-text Search
                                      ↓
                              Results & Export
```

## Usage Examples

### Example 1: Find Recent Work on Authentication
```bash
python csr.py search "auth"
```

Returns all sessions and files mentioning "auth" with relevant snippets.

### Example 2: Recover a Specific Session
```bash
python csr.py show abc123def456 --json
```

Displays full details of session `abc123def456` in JSON format.

### Example 3: Pre-Copilot Context Gathering
```bash
python csr.py files --limit 5 --json
python csr.py search "database" --json
```

Run these, review the results, then include relevant snippets in your Copilot prompt.

### Example 4: Backup & Export
```bash
python csr.py export --out my_sessions_backup.ndjson
```

Exports all indexed sessions to an NDJSON file for backup or sharing.

### Example 5: Scheduled Scanning
(Set up as a cron job or Windows Task Scheduler)

```bash
python csr.py scan
```

Run periodically (e.g., hourly or daily) to keep the index fresh with recent work.

## Best Practices

### Indexing
- Run `scan` regularly (daily or after focused work sessions) to keep the index current
- Use `--limit` flags to reduce output when searching for quick context
- Leverage `--json` output for programmatic processing
- Keep raw captures in `unsanitized/` and sanitize before moving useful notes into tracked docs

### Searching
- Use specific keywords to narrow results (e.g., function names, file paths)
- Start with focused searches rather than broad queries
- Review search results before passing to LLMs

### Session Management
- Use checkpoints to create named snapshots during work on complex features
- Tag sessions for easier retrieval later
- Export completed sessions for archival before clearing local data

### VS Code Integration
- Install the Copilot template in your workspace to automate context collection
- Run `csr search` before each Copilot prompt to surface relevant prior work
- Use exported sessions as supplementary context for offline analysis

## Limitations & Constraints

- **Local only**: No built-in cloud sync; export manually for remote backup
- **Workspace-scoped**: Primarily designed for single-workspace indexing (multi-workspace support in roadmap)
- **Privacy trade-offs**: Full-text search on code means searching is local but data is comprehensive

## Contributing & Extensions

The csr codebase is intentionally minimal to encourage extensions:
- Add new extractors for additional data sources
- Create custom exporters for different formats
- Build plugins for tighter IDE integration
- Contribute improvements via pull requests

For formatter discovery, use the privacy-safe key census before adding support
for new VS Code/Copilot persisted-state keys:

```bash
python tools/exploratory/key_census.py --limit 40
```

The command prints sanitized aggregate counts and writes raw samples only under
ignored `unsanitized/`. See `docs/KEY_CENSUS.md`.

## File Structure

```
code-session-recall/
├── csr.py                    # Main CLI entry point
├── README.md                 # Quick start guide
├── AGENTS-TEMPLATE.md        # Copilot integration template
├── AGENTS.md                 # Agent orientation notes
├── docs/
│   ├── TOOL_DOCUMENTATION.md # This file
│   ├── ENVIRONMENT_DISCOVERY.md
│   ├── HANDOFF_DESIGN.md
│   └── INSTALL.md
└── tools/
    └── exploratory/          # Historical local investigation probes
        ├── search_copilot_chats.py
        ├── search_workspace_storage.py
        ├── inspect_db.py
        ├── query_db.py
        ├── inspect_state_db.py
        ├── list_state_dbs.py
        ├── find_in_db.py
        └── decode_probe.py
```

## Troubleshooting

### Index is Stale
Run `python csr.py scan` to re-index recent work.

### Search Returns No Results
- Verify the workspace path is correct
- Run `scan` to ensure data is indexed
- Try broader search terms
- Use `--json` to see raw query results

### Database Issues
Use `inspect_db.py` to examine database state and integrity.

### Performance Issues
- Limit search results with `--limit`
- Run scans during off-peak times
- Consider exporting and archiving old sessions

## FAQ

**Q: Is my code uploaded to the cloud?**
A: No. csr is local-only by default. Data never leaves your machine unless you explicitly export it.

**Q: How often should I run `scan`?**
A: After focused work sessions, or set up a scheduled daily scan for continuous coverage.

**Q: Can I search across multiple workspaces?**
A: Currently designed for single-workspace scanning. Multi-workspace support is on the roadmap.

**Q: How do I integrate this with my editor?**
A: Use the `AGENTS-TEMPLATE.md` content in your VS Code/Copilot configuration to automate context retrieval.

**Q: What if I want to delete old sessions?**
A: Export important sessions first, then manually remove them from the database using `inspect_db.py`.

## License & Attribution

(License and contributor information to be added)

## Related Documentation

- [VS Code Session Storage](https://code.visualstudio.com/docs/editor/settings-sync)
- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
