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

Run `code-session-recall` before broad filesystem searches or fresh reasoning.
It costs little and reduces blind rediscovery.

Prefer the installed CLI when available:

```bash
csr handoff '<term or prompt summary>'  # compact context packet; run this first
csr handoff                             # fallback to recent/high-signal sessions
csr ask '<question>' --json             # compatibility alias for handoff
csr list --json --limit 5               # recent sessions
csr search '<term>' --json              # full-text search
csr show <id> --json                    # drill into one session
csr health                              # local health check
```

If the downstream workspace has a verified wrapper, prefer the short command:

```bash
./csr handoff '<term or prompt summary>'  # compact context packet; run this first
./csr handoff                             # fallback to recent/high-signal sessions
./csr ask '<question>' --json             # compatibility alias for handoff
./csr list --json --limit 5               # recent sessions
./csr search '<term>' --json              # full-text search
./csr show <id> --json                    # drill into one session
./csr health                              # local health check
```

On Windows PowerShell, the verified wrapper may be `.\csr.ps1` instead of
`./csr`.

If no wrapper is available, use the explicit Python command:

```bash
python code-session-recall/csr.py handoff '<term or prompt summary>'  # compact context packet; run this first
python code-session-recall/csr.py handoff                             # fallback to recent/high-signal sessions
python code-session-recall/csr.py ask '<question>' --json             # compatibility alias for handoff
python code-session-recall/csr.py list --json --limit 5               # recent sessions
python code-session-recall/csr.py search '<term>' --json              # full-text search
python code-session-recall/csr.py show <id> --json                    # drill into one session
python code-session-recall/csr.py health                              # local health check
```

`handoff`, `ask`, and `list` bootstrap an empty local index by running one
silent scan, so they are safe to use as first recall commands in a fresh
workspace. If a query has no direct matches, `handoff`/`ask` fall back to recent
high-signal sessions. `ask` does not call an LLM; it is just a natural-language
alias for the deterministic handoff packet.

Only use filesystem tools (`rg`, glob, find) if `handoff` and targeted `csr`
queries return nothing useful. If `csr` errors, continue silently; it is a
convenience, not a blocker.
