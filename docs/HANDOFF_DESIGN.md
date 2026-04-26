# Deterministic Handoff Design

This document captures the next architectural direction for `csr`: provide
agents with compact, high-signal context from persisted VS Code/Copilot state
without requiring another expensive round of broad grep/search.

## Design Summary

```text
csr = extractor + deterministic compressor
Copilot Chat = consumer
```

`csr` should stay local and boring:

- No API.
- No extension.
- No network.
- No extra install.
- No LLM call inside `csr`.

The tool reads persisted local state, extracts structured records, scores useful
lines with deterministic heuristics, and emits compact markdown that can be
pasted into Copilot Chat or another coding agent.

## Target Command

```powershell
python csr.py handoff "packet 007"
```

The command should:

1. Read VS Code/Copilot persisted state.
2. Search relevant indexed sessions and workspace artifacts.
3. Extract high-signal rows and lines.
4. Compress them with deterministic heuristics.
5. Produce a compact handoff markdown packet.

Example shape:

```markdown
# Agent Handoff

## Query
packet 007

## Likely context
- Packet 007: formats, strings, dates, regex, numeric, built-ins
- Related file: skills/delegation/packet-007-formats-dates-regex-numeric-builtins.md
- Related issue: Copilot worker JS heap out of memory

## Files mentioned
- skills/delegation/packet-007-formats-dates-regex-numeric-builtins.md
- skills/delegation/packet-008-performance-release-released-classes.md

## Commands mentioned
- python csr.py search "packet 007" --json

## Errors mentioned
- Worker terminated due to reaching memory limit: JS heap out of memory

## Suggested next step
Ask the new agent to inspect packet files and continue from the recovered state.
```

## Why This Fits This Repo

`csr.py` already has several of the raw ingredients:

- It can scan VS Code/Copilot chat state.
- It can reconstruct `chatSessions/*.jsonl` state from incremental JSONL rows.
- It can parse `chat.ChatSessionStore.index` from `state.vscdb`.
- It can format chat transcripts into readable content.
- It has SQLite FTS search over session content.
- It has command surfaces for `scan`, `search`, `list`, `show`, `export`, and
  `health`.

The next step is not a smarter model. It is a better local extraction and
compression layer.

## Row Types To Expose

Current indexing largely treats each session as a single text blob. For low-token
agent recall, `csr` should expose smaller typed rows for a given Copilot session.

Useful row types:

- `session` - title, ids, source, path, created/last timestamps.
- `request` - user prompt, request id, model id, timestamp.
- `assistant_text` - assistant markdown/text response chunks.
- `tool_call` - tool name, arguments, cwd, confirmation state.
- `terminal_command` - command line, shell/language, cwd, exit code, duration.
- `terminal_output` - command output, ideally split into scored lines.
- `file_reference` - paths mentioned in prompts, responses, tool records, and
  edit events.
- `edited_file` - files created/modified by Copilot, from `editedFileEvents`
  and tool invocation records.
- `code_block` - fenced code blocks and inline code-heavy snippets.
- `heading` - markdown headings from prompts/responses/docs.
- `error` - error, exception, traceback, failed command, memory limit, denied
  permission, missing file, schema failure.
- `decision` - sentences containing decision, chosen approach, rationale,
  tradeoff, or "we will".
- `next_step` - TODO, next, follow-up, roadmap, planned, blocked, issue.
- `environment` - selected env vars and VS Code/Copilot storage locator facts.

These rows can live in SQLite as separate tables later, but the first pass can
derive them at scan or handoff time from the existing session content and parsed
JSONL structures.

## Compression Heuristics

The compressor should score lines higher when they contain:

- File paths or path-like strings.
- Filenames with useful extensions: `.py`, `.md`, `.json`, `.jsonl`, `.sqlite`,
  `.vscdb`, `.ts`, `.tsx`, `.js`, `.ps1`, `.sh`.
- Commands: `python`, `git`, `rg`, `Get-ChildItem`, `Select-String`, `npm`,
  `pytest`, `pip`, `uv`, `csr`.
- Errors and failure words: `error`, `exception`, `traceback`, `failed`,
  `denied`, `missing`, `timeout`, `out of memory`, `heap`.
- Planning words: `TODO`, `next`, `issue`, `decision`, `roadmap`, `blocked`,
  `follow-up`, `planned`, `highest priority`.
- Markdown headings.
- Git hashes, UUIDs, workspace storage ids, session ids.
- Quoted symbols and code identifiers.
- Lines near a matched query term.

It should score lines lower when they are:

- Generic assistant filler.
- Long repeated JSON metadata.
- Repeated path lists already captured elsewhere.
- Huge terminal output with no query/error/path signal.
- Markdown boilerplate from generated docs unless the query matches it.

## Handoff Output Sections

Suggested default sections:

- `Query`
- `Likely context`
- `Sessions matched`
- `Files mentioned`
- `Commands mentioned`
- `Errors mentioned`
- `Decisions / next steps`
- `Environment / storage clues`
- `Suggested next step`

The output should be short by default. Prefer a handful of specific bullets over
full transcripts.

Potential flags:

```powershell
python csr.py handoff "packet 007" --limit 20
python csr.py handoff "packet 007" --session <chat-session-id>
python csr.py handoff "packet 007" --current-session
python csr.py handoff "packet 007" --json
python csr.py handoff "packet 007" --include-terminal-output
```

## Formatter Expansion

Formatter work should move from "make this blob readable" toward "extract
typed, compact facts." Existing formatter functions in `csr.py` are still useful,
but they should feed structured rows.

Near-term formatter targets:

- Copilot `chatSessions/*.jsonl` request/response state.
- `toolInvocationSerialized` records.
- Terminal command metadata and output.
- `editedFileEvents`.
- Inline file references in VS Code URI objects.
- `chat.ChatSessionStore.index` timing/title/session metadata.
- Environment dump command outputs, especially `Name`/`Value` or `Key`/`Value`
  pairs.

## Success Criteria

`csr handoff <query>` is successful when a new agent can continue work from the
handoff without first running broad `rg`, manually opening SQLite DBs, or
reading complete Copilot transcripts.

Good output should answer:

- What was the user trying to do?
- Which session(s) probably matter?
- Which files matter?
- Which commands were already run?
- What failed?
- What decisions were made?
- What is the next useful action?

This keeps token cost low while preserving enough context for an agent to act.
