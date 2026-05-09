# code-session-recall - Agent Instructions Template

This template is meant to be merged into the top-level `AGENTS.md` or equivalent
agent instructions file of any workspace that uses `code-session-recall`.

Assumed layout:

```text
<workspace>/
  AGENTS.md
  code-session-recall/
    csr.py
```

---

## Progressive Session Recall - RUN FIRST ON EVERY PROMPT

Your first tool action on every user prompt must be session recall. Run CSR
before reading files, grepping, listing directories, or planning from memory. It
costs little and prevents blind rediscovery.

Start with one of these, using the installed CLI when available:

```bash
csr handoff '<prompt summary>'          # FIRST command on each prompt
csr handoff                             # use when the prompt is unclear
```

Then use targeted CSR commands before broad filesystem tools:

```bash
csr list --json --limit 5               # recent sessions
csr search '<term>' --json              # full-text session search
csr ask '<question>' --json             # alias for handoff
csr show <id> --json                    # drill into one session
csr health                              # local health check
```

By default, `handoff`, `search`, and `list` prefer records with evidence for the
current workspace path. Use `--all-workspaces` only when intentionally searching
across other repositories/workspaces on the same machine.

If the downstream workspace has a verified wrapper, prefer the short command:

```bash
./csr handoff '<prompt summary>'        # FIRST command on each prompt
./csr handoff                           # use when the prompt is unclear
./csr list --json --limit 5
./csr search '<term>' --json
./csr ask '<question>' --json
./csr show <id> --json
./csr health
```

On Windows PowerShell, the verified wrapper may be `.\csr.ps1` instead of
`./csr`.

If no wrapper is available, use the explicit Python command:

```bash
python code-session-recall/csr.py handoff '<prompt summary>'  # FIRST command on each prompt
python code-session-recall/csr.py handoff                     # use when the prompt is unclear
python code-session-recall/csr.py list --json --limit 5
python code-session-recall/csr.py search '<term>' --json
python code-session-recall/csr.py ask '<question>' --json
python code-session-recall/csr.py show <id> --json
python code-session-recall/csr.py health
```

`handoff`, `ask`, and `list` bootstrap an empty local index by running one
silent fast scan, so they are safe to use as first recall commands in a fresh
workspace. The bootstrap scan is session-first: it prefers the active VS Code
workspace storage, caps transcript history, and skips repository Markdown unless
explicitly requested. If a query has no direct matches, `handoff`/`ask` fall
back to recent high-signal sessions. `ask` does not call an LLM; it is just a
natural-language alias for the deterministic handoff packet.

Keep recall cheap enough that agents will actually use it. Use `csr search
'<term>' --deep` only for rare misses, `csr scan --include-markdown` only when
repository docs should be indexed, and `CSR_SCAN_ALL_WORKSPACES=1` only for
intentional cross-workspace recall.

When CSR behavior changes, keep `AGENTS-TEMPLATE.md`,
`docs/TOOL_DOCUMENTATION.md`, and `docs/SOURCE_MATURITY_MATRIX.md` aligned. The
matrix tracks source coverage, normalized facts, Codex/OpenAI discovery, and
product maturity.

CSR filters terminal/tool invocations of `csr` itself so command output from
recall operations does not feed back into future recall packets.

Only use filesystem tools (`rg`, glob, find) after `handoff` and targeted `csr`
queries return nothing useful. If `csr` errors, continue silently and proceed;
it is a convenience, not a blocker.
