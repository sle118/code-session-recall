# Privacy-Safe State Key Census

Use the key census before implementing new state formatters. The goal is to
measure which VS Code/Copilot persisted keys actually exist and which ones carry
useful recall signals, without committing raw local state.

Run from the repo root:

```powershell
python tools/exploratory/key_census.py --limit 40
```

The command prints only aggregate counts and signal flags. Raw row samples are
written to an ignored `unsanitized/key-census-*.json` file for local inspection.
Do not commit files from `unsanitized/`.

Useful follow-up command:

```powershell
python tools/exploratory/key_census.py --json > unsanitized/key-census-summary.json
```

The JSON summary is still intended as local discovery output unless it has been
reviewed and sanitized.

For targeted rechecks after creating Copilot todos, terminal activity, or
subagent activity, filter the summary by key family:

```powershell
python tools/exploratory/key_census.py --match todo --match chat --match agent --match terminal --limit 80
```

To show only matching keys that contain path, command, error, todo, or timestamp
signals:

```powershell
python tools/exploratory/key_census.py --match todo --match chat --match agent --match terminal --only-signal --limit 80
```

To inspect nested structure without printing raw values or dynamic session ids:

```powershell
python tools/exploratory/key_census.py --shape --match memento/chat-todo-list --match agentSessions --match chat.terminalSessions --limit 20
```

For Codex/OpenAI discovery, use a targeted privacy-safe census:

```powershell
python tools/exploratory/key_census.py --shape --match codex --match openai --match chatgpt --match agentSessions --limit 40
```

Update `docs/SOURCE_MATURITY_MATRIX.md` with sanitized findings before adding a
new formatter or source.

## What To Look For

Prioritize keys that are frequent or high-signal:

- `chat.ChatSessionStore.index` - session ids, titles, and timing metadata.
- `memento/interactive-session` - prompt history and resumable chat context.
- `memento/chat-todo-list` - likely next-step signal when present; now has a
  compact formatter and is indexed as `vscode-live`.
- `agentSessions.model.cache` - agent/subagent labels, status, timing, and
  change counts; now has a compact formatter and is indexed as `vscode-live`.
- `agentSessions.state.cache` - possible agent/session state; inspect with
  Codex/OpenAI census before indexing. Initial sanitized census showed mainly
  `resource` plus read-state markers.
- `memento/webviewView.chatgpt.sidebarSecondaryView` - possible ChatGPT/Codex
  webview state; initial sanitized census showed empty object state, so this is
  lower priority than agent session cache.
- `workbench.view.extension.codexSecondaryViewContainer.*` - Codex UI/view
  state; initial sanitized census showed visibility/layout state, so treat as
  low priority unless it links to useful session state.
- `terminal.integrated.bufferState` - possible terminal output and command
  recovery signal.
- `chat.terminalSessions` and `terminalChat.toolSessionMappings` - possible
  links between chat turns and terminals.
- `GitHub.copilot-chat` and related Copilot keys - extension-specific state.

Ignore or deprioritize keys that are mostly UI layout, view visibility,
booleans, or large editor MRU blobs with no command/error/todo/path signal.

## Creating Missing Keys

If an expected key is missing, create the relevant behavior in Copilot or VS
Code, then rerun the census. Examples:

- Open Copilot Chat and send a short prompt to refresh interactive-session
  state.
- Ask Copilot to run or explain a terminal command to refresh terminal/chat
  mappings.
- Create or complete Copilot TODO/plan items if testing todo-list storage.
- Open files, run searches, or trigger tasks only when testing those specific
  key families.

After the key appears, inspect the raw sample in `unsanitized/`, then implement
only the formatter fields that produce compact, sanitized recall value.
