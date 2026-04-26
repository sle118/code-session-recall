# Installing Code Session Recall

This document tells agents how to install or update `code-session-recall` inside
a downstream workspace and then merge the reusable recall instructions.

`AGENTS-TEMPLATE.md` is the instruction block to merge into workspaces that use
`code-session-recall`.

The intended downstream layout is:

```text
<workspace>/
  AGENTS.md
  code-session-recall/
    csr.py
```

When installing `code-session-recall` into a workspace, first make sure the
installed tool folder and wrapper commands are excluded from the downstream
project's Git history, then try to install a workspace-local `csr` command, then
merge the contents of
`code-session-recall/AGENTS-TEMPLATE.md` into the workspace's top-level
`AGENTS.md` or equivalent agent instructions file.

When updating `code-session-recall`, compare the current
`AGENTS-TEMPLATE.md` with the downstream workspace instructions and refresh the
recall block if command behavior changed.

## Bootstrap Flow

From the downstream workspace root:

1. Confirm `code-session-recall/csr.py` exists.
2. Add ignore rules for the installed tool folder and local wrapper command.
3. Try to create or update a workspace-local wrapper command.
4. Verify the wrapper with `./csr --help` or `./csr.ps1 --help`.
5. Merge `code-session-recall/AGENTS-TEMPLATE.md` into the top-level
   instructions.
6. If the wrapper works, write the merged instructions with short `csr`
   commands. If wrapper installation fails, keep the explicit
   `python code-session-recall/csr.py` commands.

Do not overwrite an unrelated existing `csr`, `csr.ps1`, or project command.
Inspect first; if there is a conflict, skip wrapper installation and use the
explicit Python command form in agent instructions.

## Git Exclusion

By default, a downstream workspace should treat `code-session-recall` as a local
tool install, not as project source. Before creating or updating wrappers, add
these entries to the downstream workspace's `.gitignore` unless that project has
intentionally decided to vendor the tool:

```gitignore
# Local Code Session Recall install
/code-session-recall/
/csr
/csr.ps1
```

If `.gitignore` does not exist, create it. If an entry already exists, do not
duplicate it. If the downstream project intentionally vendors
`code-session-recall`, do not add the `/code-session-recall/` ignore rule; still
ignore local wrapper commands unless the project explicitly wants to track them.

### POSIX / Dev Container Wrapper

Create `./csr` in the downstream workspace root:

```sh
#!/usr/bin/env sh
exec python3 "$(dirname "$0")/code-session-recall/csr.py" "$@"
```

Then run:

```sh
chmod +x ./csr
./csr --help
```

If `python3` is unavailable but `python` works, update the wrapper to use
`python`.

### Windows PowerShell Wrapper

Create `./csr.ps1` in the downstream workspace root:

```powershell
& python "$PSScriptRoot\code-session-recall\csr.py" @args
```

Then run:

```powershell
.\csr.ps1 --help
```

If the PowerShell execution policy blocks local scripts, skip the wrapper and
use the explicit Python command form in agent instructions.

## Instruction Merge

If wrapper installation succeeded, downstream instructions should tell agents to
run:

```powershell
./csr handoff "<term or prompt summary>"
```

or on Windows PowerShell:

```powershell
.\csr.ps1 handoff "<term or prompt summary>"
```

before broad filesystem searches. Agents may also use:

```powershell
./csr ask "<question>"
```

as a natural-language alias for the same deterministic handoff behavior. If the
query is unclear, agents should run:

```powershell
./csr handoff
```

If wrapper installation did not succeed, downstream instructions should instead
use the explicit command form:

```powershell
python code-session-recall/csr.py handoff "<term or prompt summary>"
```

Agents may also use:

```powershell
python code-session-recall/csr.py ask "<question>"
```

as a natural-language alias for the same deterministic handoff behavior. If the
query is unclear, agents should run:

```powershell
python code-session-recall/csr.py handoff
```

This no-query form falls back to recent/high-signal indexed sessions.
`handoff`, `ask`, and `list` bootstrap an empty index with one silent local scan.
If a handoff query has no direct matches, it also falls back to recent
high-signal sessions so first-pass recall still provides orientation.

Do not copy raw discovery output, environment dumps, chat extracts, tokens, or
personal paths into downstream instructions. Keep raw captures in an ignored
local folder and copy only sanitized guidance.
