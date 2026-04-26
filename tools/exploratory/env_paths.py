import os
from pathlib import Path


def csr_index_db():
    return Path(os.getenv("CSR_DB", Path.home() / ".code-session-recall" / "index.sqlite"))


def workspace_storage_candidates():
    roots = []
    explicit = os.getenv("CSR_VSCODE_WORKSPACE_STORAGE")
    if explicit:
        roots.append(Path(explicit))

    appdata = os.getenv("APPDATA")
    if appdata:
        appdata_path = Path(appdata)
        roots.extend([
            appdata_path / "Code" / "User" / "workspaceStorage",
            appdata_path / "Code - Insiders" / "User" / "workspaceStorage",
            appdata_path / "VSCodium" / "User" / "workspaceStorage",
        ])

    seen = set()
    out = []
    for path in roots:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def first_workspace_storage():
    for path in workspace_storage_candidates():
        if path.exists():
            return path
    candidates = workspace_storage_candidates()
    return candidates[0] if candidates else Path("workspaceStorage")


def state_db_candidates():
    for base in workspace_storage_candidates():
        if base.exists():
            yield from base.rglob("state.vscdb")
