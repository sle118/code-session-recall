import sqlite3, sys
from pathlib import Path
from env_paths import state_db_candidates

if len(sys.argv) > 1:
    p = Path(sys.argv[1])
else:
    p = next(state_db_candidates(), None)
    if p is None:
        print('usage: inspect_state_db.py <path-to-state.vscdb>')
        print('or set CSR_VSCODE_WORKSPACE_STORAGE to a workspaceStorage root')
        sys.exit(1)

print('DB:', p)
conn = sqlite3.connect(p)
c = conn.cursor()
try:
    rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print('tables:', rows)
    rows = c.execute("SELECT key FROM ItemTable LIMIT 1000").fetchall()
    print('total keys:', len(rows))
    for k, in rows:
        if 'copilot' in (k or '').lower() or 'chat' in (k or '').lower() or 'session' in (k or '').lower():
            print('key:', k)
except Exception as e:
    print('error:', e)
conn.close()
