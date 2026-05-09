# Source and Maturity Matrix

CSR is evolving from deep Copilot recall into a broader VS Code AI session
recall layer. This matrix tracks extraction coverage separately from product
maturity so new parsers do not outrun speed, safety, diagnostics, and agent
usability.

## Source Coverage

Legend: `yes` implemented, `partial` useful first pass, `planned` tracked but
not implemented, `n/a` not expected for that source.

| Source | Discovered | Scanned | Formatted | Indexed | Handoff | Tested |
| --- | --- | --- | --- | --- | --- | --- |
| `chatSessions/*.jsonl` | yes | yes | yes | yes | yes | partial |
| `GitHub.copilot-chat/transcripts/*.jsonl` | yes | yes | yes | yes | yes | partial |
| `state.vscdb` selected keys | yes | yes | partial | yes | yes | partial |
| `memento/chat-todo-list` | yes | yes | yes | yes | yes | partial |
| `agentSessions.model.cache` | yes | yes | yes | yes | yes | partial |
| `agentSessions.state.cache` | yes | planned | planned | planned | planned | planned |
| Codex/ChatGPT webview state | yes | planned | planned | planned | planned | planned |
| Markdown docs | yes | opt-in | n/a | opt-in | opt-in | partial |

## Fact Coverage

Track whether each source can emit normalized facts for `handoff` and future
typed rows.

| Source | Sessions | Prompts | Assistant | Files | Edited | Commands | Errors | Decisions | Todos | Agents | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `chatSessions/*.jsonl` | yes | yes | yes | yes | yes | yes | yes | yes | partial | partial | yes |
| `GitHub.copilot-chat/transcripts/*.jsonl` | yes | yes | yes | yes | partial | yes | yes | yes | yes | partial | yes |
| `memento/chat-todo-list` | partial | n/a | n/a | n/a | n/a | n/a | n/a | yes | yes | n/a | n/a |
| `agentSessions.model.cache` | yes | n/a | n/a | partial | partial | n/a | n/a | n/a | n/a | yes | yes |
| `agentSessions.state.cache` | planned | planned | planned | planned | planned | planned | planned | planned | planned | yes | planned |
| Codex/ChatGPT webview state | planned | planned | planned | planned | planned | planned | planned | planned | planned | planned | planned |

## Codex/OpenAI Discovery

Use privacy-safe census before adding formatters. Candidate keys observed in VS
Code state include:

- `agentSessions.model.cache` - high priority; may already carry Codex/OpenAI
  session labels, provider metadata, timing, and changes.
- `agentSessions.state.cache` - high priority; inspect structure before
  indexing.
- `memento/webviewView.chatgpt.sidebarSecondaryView` - medium priority; likely
  extension/webview state.
- `workbench.view.extension.codexSecondaryViewContainer.*` - low priority unless
  it references session state.

Initial sanitized census findings:

- `agentSessions.model.cache` appears as a list of entries with
  `providerType`, `providerLabel`, `resource`, `label`, `status`, `timing`, and
  sometimes `changes`. This remains the first Codex/OpenAI source to mature.
- `agentSessions.state.cache` appears as a list of `resource` plus read-state
  markers. Treat it as secondary until a recall-bearing shape is observed.
- `memento/webviewView.chatgpt.sidebarSecondaryView` has appeared as empty
  object state in observed workspaces.
- `workbench.view.extension.codexSecondaryViewContainer.*` has appeared as view
  visibility/layout state. Keep it low priority unless future census shows
  session-bearing fields.

Run targeted discovery with:

```powershell
python tools/exploratory/key_census.py --shape --match codex --match openai --match chatgpt --match agentSessions --limit 40
```

Raw output belongs only in `unsanitized/`. Commit sanitized summaries or fixture
derivatives only after local review.

## Product Maturity Track

| Area | Status | Target |
| --- | --- | --- |
| `files` command | planned | Recent file recall before broad search |
| `--days` filters | planned | Bounded list/search/files/checkpoints queries |
| Enhanced `health` | partial | Source diagnostics implemented; parser coverage still maturing |
| `schema-check` | planned | Safe DB/index evolution |
| Trust fencing | planned | Mark file-backed/untrusted content in agent output |
| Sanitized fixtures | planned | Real observed VS Code shapes without local leaks |
| Performance budgets | partial | Keep `handoff`, `ask`, `list`, and bootstrap scans fast enough to run first |
| Path/noise cleanup | partial | Compact operational handoff output |

Treat "fast enough for agents to run first" as a release criterion for every
recall-facing change.
