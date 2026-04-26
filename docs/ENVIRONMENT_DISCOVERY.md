# Environment Discovery Notes

These notes capture what we learned from the seeded Copilot conversation
`Repository contents overview`. The purpose is to make future `csr` work derive
VS Code/Copilot storage locations and session ids from local state instead of
guessing usernames, database paths, or hard-coded chat ids.

Personal details in this document are intentionally anonymized. Preserve the
shape of paths, ids, and records, but use placeholders such as `<USER>`,
`<CHAT_SESSION_ID>`, and `<WORKSPACE_STORAGE_ID>` instead of real values.

## Seed Conversation

- Title: `Repository contents overview`
- Chat session id: `<CHAT_SESSION_ID>`
- Workspace storage id: `<WORKSPACE_STORAGE_ID>`
- Session JSONL:
  `%APPDATA%\Code - Insiders\User\workspaceStorage\<WORKSPACE_STORAGE_ID>\chatSessions\<CHAT_SESSION_ID>.jsonl`
- Session index DB:
  `%APPDATA%\Code - Insiders\User\workspaceStorage\<WORKSPACE_STORAGE_ID>\state.vscdb`

## Useful VS Code State Records

`state.vscdb` contains an `ItemTable` row with key:

```text
chat.ChatSessionStore.index
```

That JSON maps chat session ids to metadata including:

- `sessionId`
- `title`
- `lastMessageDate`
- `timing.created`
- `timing.lastRequestStarted`
- `timing.lastRequestEnded`
- `initialLocation`
- `hasPendingEdits`
- `stats.fileCount`
- `stats.added`
- `stats.removed`
- `permissionLevel`

The per-session JSONL file under `chatSessions/<session-id>.jsonl` contains
incremental state records:

- `kind: 0` - initial full state
- `kind: 1` - set a path in state
- `kind: 2` - append/update a path in state

Observed paths include:

- `customTitle`
- `responderUsername`
- `requests`
- `inputState.selectedModel`
- `requests[n].result`
- `requests[n].response`
- `requests[n].modelState`
- `requests[n].completionTokens`
- `requests[n].elapsedMs`

## Terminal Tool Records

Copilot terminal executions are stored inside `requests[n].response` as
`toolInvocationSerialized` records with `toolSpecificData.kind == "terminal"`.

Useful fields:

- `terminalToolSessionId`
- `terminalCommandId`
- `commandLine.original`
- `commandLine.forDisplay`
- `cwd.fsPath` or `cwd.path`
- `language`
- `terminalCommandState.exitCode`
- `terminalCommandState.timestamp`
- `terminalCommandState.duration`
- `terminalCommandUri.path`
- `terminalCommandUri.query`
- `terminalCommandOutput.text`
- `terminalCommandOutput.lineCount`

Example terminal command URI:

```text
vscode-terminal:/<WORKSPACE_STORAGE_ID>/2?command=<TERMINAL_COMMAND_ID>
```

The first path segment is the VS Code workspace storage id:

```text
<WORKSPACE_STORAGE_ID>
```

## Environment Variables That Reveal Storage

Copilot ran:

```powershell
Get-ChildItem env: | Format-Table -AutoSize
Get-ChildItem env: | ConvertTo-Json
```

`Format-Table -AutoSize` is human-readable but truncates long values with
`...`. `ConvertTo-Json` preserved full values, but VS Code captured the stored
terminal output starting mid-JSON, so the saved output was not parseable as a
complete JSON array. A tolerant `Key`/`Value` extractor still recovered the
important full values.

Recovered values:

```text
USERPROFILE=C:\Users\<USER>
USERNAME=<USER>
TERM_PROGRAM=vscode
TERM_PROGRAM_VERSION=1.117.0-insider
VSCODE_INJECTION=1
PYTHONSTARTUP=%APPDATA%\Code - Insiders\User\workspaceStorage\<WORKSPACE_STORAGE_ID>\ms-python.python\pythonrc.py
VSCODE_GIT_ASKPASS_MAIN=%APPDATA%\Code - Insiders\User\globalStorage\vscode.git\askpass\<ASKPASS_ID>\askpass-main.js
VSCODE_GIT_ASKPASS_NODE=%LOCALAPPDATA%\Programs\Microsoft VS Code Insiders\Code - Insiders.exe
VSCODE_DEBUGPY_ADAPTER_ENDPOINTS=%USERPROFILE%\.vscode-insiders\extensions\ms-python.debugpy-<VERSION>-win32-x64\.noConfigDebugAdapterEndpoints\<ENDPOINT_FILE>
TEMP=%LOCALAPPDATA%\Temp
TMP=%LOCALAPPDATA%\Temp
```

The strongest locator is `PYTHONSTARTUP`, because it directly embeds the active
workspace storage path:

```text
%APPDATA%\Code - Insiders\User\workspaceStorage\<WORKSPACE_STORAGE_ID>\ms-python.python\pythonrc.py
```

From that path, `csr` can infer:

- VS Code profile root:
  `%APPDATA%\Code - Insiders\User`
- Workspace storage root:
  `%APPDATA%\Code - Insiders\User\workspaceStorage`
- Workspace storage id:
  `<WORKSPACE_STORAGE_ID>`
- Workspace state DB:
  `...\workspaceStorage\<WORKSPACE_STORAGE_ID>\state.vscdb`
- Chat sessions directory:
  `...\workspaceStorage\<WORKSPACE_STORAGE_ID>\chatSessions`

## Discovery Strategy

Recommended implementation order:

1. Inspect current process environment for direct locators:
   `PYTHONSTARTUP`, `VSCODE_GIT_ASKPASS_MAIN`, `VSCODE_GIT_ASKPASS_NODE`,
   `TERM_PROGRAM_VERSION`, `APPDATA`, and `USERPROFILE`.
2. Parse any Copilot terminal/tool records already indexed. Use
   `terminalCommandUri.path`, `cwd`, command output, and environment dumps.
3. If `PYTHONSTARTUP` points inside `workspaceStorage/<id>/...`, derive the
   workspace storage id and use the sibling `state.vscdb` and `chatSessions`.
4. Otherwise scan likely roots:
   `%APPDATA%\Code\User\workspaceStorage`,
   `%APPDATA%\Code - Insiders\User\workspaceStorage`,
   and any user-supplied roots.
5. Use `chat.ChatSessionStore.index` to map session ids to titles and timings.
6. Prefer matching by current workspace path, conversation title, newest timing,
   and terminal command metadata over hard-coded constants.

## Better Future Probe Commands

To avoid truncation and partial JSON capture, prefer compact JSON with only the
fields needed:

```powershell
Get-ChildItem env: | Select-Object Name, Value | ConvertTo-Json -Compress
```

For a single-line map:

```powershell
Get-ChildItem env: | ForEach-Object { [pscustomobject]@{ Name = $_.Name; Value = $_.Value } } | ConvertTo-Json -Compress
```

For targeted values:

```powershell
'APPDATA','USERPROFILE','PYTHONSTARTUP','TERM_PROGRAM_VERSION','VSCODE_GIT_ASKPASS_MAIN','VSCODE_GIT_ASKPASS_NODE' |
  ForEach-Object { [pscustomobject]@{ Name = $_; Value = [Environment]::GetEnvironmentVariable($_) } } |
  ConvertTo-Json -Compress
```
