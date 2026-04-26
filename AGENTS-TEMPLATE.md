# auto-memory — Copilot Instructions Template

> **Note:** For installation, use [`deploy/install.md`](deploy/install.md) — it handles everything including appending this template automatically.

This file contains the raw instruction block for manual reference. Copy the block below into `~/.copilot/copilot-instructions.md` if you prefer manual setup.

---

## Progressive Session Recall — RUN FIRST ON EVERY PROMPT

**Run `csr` FIRST on every prompt before doing anything else.** It costs very little and prevents expensive blind searches.

```bash
csr files --json --limit 10          # recently touched files
csr files --days 7 --json            # files touched in last 7 days
csr list --json --limit 5           # recent sessions
csr list --days 2 --json            # sessions from last 2 days
csr search '<term>' --json          # full-text search
csr search '<term>' --days 5        # search last 5 days only
csr checkpoints --days 3            # checkpoints from last 3 days
csr show <id> --json                # drill into one session
csr health --json                   # 8-dimension health check
csr schema-check                    # validate DB schema (run after csr/CLI upgrade)
```

**`--days N` works on all 4 query commands** (`list`, `files`, `checkpoints`, `search`) — filters to sessions/files/checkpoints from the last N days.

Only use filesystem tools (grep, glob, find) if `csr` returns nothing useful.
If `csr` errors, continue silently — it's a convenience, not a blocker.
