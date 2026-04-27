# code-session-recall

Minimal tool to recover past coding/AI sessions.

State of the union
-------------------

`code-session-recall` (csr) is a small, local CLI that helps you rediscover past coding work and AI-assisted sessions. It scans your workspace and local session stores, indexes recent activity, and provides quick lookups so you can run `csr` before asking large-context tools to search your repo. The goal is to make context retrieval cheap, targeted, and privacy-friendly.

Inspiration: CSR is inspired by Desi Villanueva's article
["I Wasted 68 Minutes a Day Re-Explaining My Code. Then I Built auto-memory."](https://devblogs.microsoft.com/all-things-azure/i-wasted-68-minutes-a-day-re-explaining-my-code-then-i-built-auto-memory/)
and the related [`auto-memory`](https://github.com/dezgit2025/auto-memory)
project. `auto-memory` targets Copilot CLI's local session database. CSR applies
the same recall-first idea to VS Code/GitHub Copilot, where useful state is
spread across VS Code workspace storage, chat session JSONL files, extension
artifacts, and state databases rather than one easy-to-query CLI database.

Core capabilities
- Scan and index: crawl specified folders and extract session metadata and touched files.
- Search: full-text search across indexed sessions and extracted text artifacts.
- Show: present a single session's details (checkpoints, files, commands, snippets).
- Export: dump sessions or indexes for backup or sharing.
- Workspace affinity: query commands prefer the current workspace by default,
  deriving active VS Code `workspaceStorage/<id>` from `PYTHONSTARTUP` when
  available, with `--all-workspaces` available for intentional global recall.

Intended usage
- Run `csr scan` after a focused work session (or let it be scheduled) to capture a session snapshot.
- Run `csr` commands before using an expensive workspace-wide search or an LLM prompt to surface recent, relevant context.
- Use `csr show <id>` to rehydrate a prior session when you need the exact commands, files, or checkpoints.
- Use `csr list --json --limit 5` to inventory recent session/live records;
  pass `--source markdown` only when you want indexed repository docs.

Installation
------------

Once published to PyPI:

```bash
python -m pip install code-session-recall
csr --version
csr handoff
csr install-instructions
```

For local development or pre-release testing from a clone:

```bash
python -m pip install -e .
csr --help
csr --version
csr install-instructions
```

The repository-local entry point remains available:

```bash
python csr.py handoff
python csr.py install-instructions
python csr.py --version
```

`csr install-instructions` prints the exact bootstrap prompt and AGENTS.md
snippet to give another coding agent so CSR becomes the first recall step in a
workspace.

Release and publishing
----------------------

GitHub Actions builds and checks the package on every push to `main` and every
pull request. PyPI publishing is intentionally tag-driven: bump
`pyproject.toml`, push the commit, then push a matching tag such as `v0.1.1`.
See `docs/RELEASE.md` for the Trusted Publishing setup and release checklist.

VS Code + GitHub Copilot integration
- This tool is designed to complement the GitHub Copilot extension in Visual Studio Code. Use `csr` to surface local session context before invoking Copilot so prompts sent to Copilot are focused and cheaper.
- Installation pattern: place the `AGENTS-TEMPLATE.md` content into `~/.copilot/copilot-instructions.md` (or append it) to teach Copilot to run `csr` first on each prompt. Alternately, copy the template into your workspace notes and reference it from your Copilot config.
- Recommended flow: run `csr files`/`csr list` (or `csr search`) to collect context, then paste or include the relevant snippets in the Copilot prompt.

Key record types and what they provide
- Session (primary unit)
	- id: stable session identifier
	- times: start / end / last-modified timestamps
	- summary: short natural-language summary (if available)
	- files: list of file paths touched and small excerpts
	- commands: captured commands and terminal history snippets
	- checkpoints: named snapshots within the session
	- tags/labels: user or auto-generated tags

- File record
	- path: workspace-relative path
	- last_touched: timestamp
	- diffs/snippets: small context snippets or a short diff for quick review

- Checkpoint
	- checkpoint id/name
	- description: short note captured at checkpoint time
	- snapshot: list of important files and their short hashes

- Health / Index metadata
	- schema version: DB layout version
	- index stats: counts, last-scan, errors

Usage (examples)

python csr.py scan
python csr.py handoff "keyword"
python csr.py handoff
python csr.py ask "question" --json
python csr.py handoff "keyword" --json
python csr.py search "keyword"
python csr.py show <id> --json
python csr.py install-instructions
python csr.py export --out sessions.ndjson

Roadmap
-------

The code and docs are mid-migration from an earlier machine/user profile. The
near-term goal is to make `csr` discover the active VS Code/Copilot environment
from local state instead of relying on hard-coded usernames, storage folders, or
session ids.

- Implemented / present in this repo
	- `scan` - crawl and index workspace and session stores
	- `search` - full-text search across indexed records
	- `list` - list recent indexed sessions
	- `show` - display a single session
	- `export` - export sessions or slices
	- `health` - basic DB/workspaceStorage/workspace check
	- formatter fact extraction - Copilot chat formatting now extracts compact `files`, `commands`, `errors`, `nextSteps`, `editedFiles`, and `toolEvents` facts before recent-turn previews
	- `handoff` - produce compact agent-ready markdown from matched or recent sessions
	- `ask` - compatibility alias for `handoff` so natural agent recall commands work

- Highest priority
	- VS Code storage discovery - support Stable (`Code`), Insiders (`Code - Insiders`), and user-supplied roots; prefer environment-derived paths such as `APPDATA`, `TERM_PROGRAM_VERSION`, `VSCODE_*`, and terminal/tool metadata captured in Copilot sessions.
	- Session discovery - infer the active workspace/session from `chat.ChatSessionStore.index`, `chatSessions/*.jsonl`, terminal command metadata, and conversation titles instead of hard-coded `WORKSPACE_CURRENT_CHAT_SESSION_ID`.
	- Environment-aware recall - index Copilot terminal/tool records, including command, cwd, language, exit code, command URI, and useful environment variables, so future scans can locate the right database/session without guessing.
	- Improve deterministic handoff compression - continue refining `csr handoff <query>` scoring, workspace affinity, and typed fact ranking; see `docs/HANDOFF_DESIGN.md`.
	- Docs parity - keep README, `docs/TOOL_DOCUMENTATION.md`, `AGENTS-TEMPLATE.md`, and `csr --help` aligned with actual CLI behavior.

- Roadmap / desirable commands and flags
	- `files` - list recently touched files with metadata (useful for quick context): `csr files --json --limit 10`
	- `checkpoints` - list or search named checkpoints across sessions
	- enhanced `health` - 8-dimension health check report for the local datastore, VS Code storage discovery, current workspace/session, parser coverage, and index freshness
	- `schema-check` - validate DB schema and guide migrations after upgrades
	- finer `--days N` filtering for `list`, `files`, `search`, `checkpoints` (convenience flag)

Notes and conventions
- We intentionally keep sample data and temporary investigation outputs out of version control by default; see `.gitignore`.
- Raw discovery outputs belong in ignored `unsanitized/`; only sanitized derivatives should be committed to `docs/` or code.
- The intended downstream install pattern is a local `code-session-recall/` subdirectory inside each workspace; see `docs/INSTALL.md` for `.gitignore` entries, optional wrapper commands, and merging `AGENTS-TEMPLATE.md` into that workspace's top-level agent instructions.
- Sessions are meant to be local by default; export if you need to share or archive them.

Contributing and extensions
- The `csr` architecture is intentionally small — new extractors and exporters can be added as modules. If you want a tighter IDE integration or a remote sync feature, add it as an optional plugin.

License / attribution
- Inspired by Desi Villanueva's Auto Memory article and the
  `dezgit2025/auto-memory` repository:
  https://devblogs.microsoft.com/all-things-azure/i-wasted-68-minutes-a-day-re-explaining-my-code-then-i-built-auto-memory/
  and https://github.com/dezgit2025/auto-memory.
- (add license and contributor notes here)

