# Agent Notes

This repository contains `code-session-recall` (`csr`), a small local Python CLI
for recovering and searching VS Code/GitHub Copilot coding sessions. The main
entry point is `csr.py`.

## Read First

- `README.md` - project overview, current state, and roadmap.
- `docs/TOOL_DOCUMENTATION.md` - broader tool documentation and command notes.
- `docs/ENVIRONMENT_DISCOVERY.md` - high-signal notes about deriving VS Code
  storage roots, workspace ids, and Copilot chat session ids without guessing.
- `docs/HANDOFF_DESIGN.md` - roadmap for `csr handoff <query>` as a local
  extractor plus deterministic compressor for compact agent-ready context.
- `AGENTS-TEMPLATE.md` - the intended Copilot instruction template for using
  `csr` before broad repo searches.

## Current Priority

The project started on another machine/profile and contains some hard-coded
paths and session ids from that earlier work. The next important implementation
theme is environment-aware discovery:

- Detect VS Code Stable and VS Code Insiders storage roots.
- Derive workspace storage ids from environment variables and Copilot terminal
  tool records.
- Use `state.vscdb` and `chatSessions/*.jsonl` to discover chat session ids,
  titles, timings, terminal commands, and edited files.
- Expand formatters into typed rows and add deterministic handoff compression
  so agents can retrieve low-token context without broad grep.
- Avoid hard-coding usernames, workspace hashes, or current chat ids.

## Useful Commands

```powershell
python csr.py --help
python csr.py scan
python csr.py list --json -n 5
python csr.py search "keyword" --json
python csr.py health
python -m py_compile csr.py
```

## Working Notes

- The local index is stored at `~/.code-session-recall/index.sqlite`.
- The current machine uses VS Code Insiders, so useful state may live under
  `%APPDATA%\Code - Insiders\User\workspaceStorage`.
- Probe scripts in the repo may contain hard-coded paths from earlier
  investigation; treat them as historical helpers, not authoritative config.
- Anonymize personal details before committing docs or sample outputs. Use
  placeholders such as `<USER>`, `<CHAT_SESSION_ID>`,
  `<WORKSPACE_STORAGE_ID>`, and environment variables like `%APPDATA%`.
- Do not commit user- or domain-specific probe templates, expected-output files,
  chat extracts, or validation heuristics. Exploratory searches should take
  caller-provided terms rather than baking sensitive terms into the repo.
- Keep docs and CLI behavior aligned when adding commands or flags.
