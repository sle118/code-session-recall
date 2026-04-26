import sqlite3, os
from env_paths import csr_index_db

db = csr_index_db()
print('DB path:', db)
print('exists', os.path.exists(db))

conn = sqlite3.connect(db)
c = conn.cursor()

print('sqlite_master entries:')
for r in c.execute("SELECT name, sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"):
    print('-', r[0])
    print(r[1])

try:
    s = c.execute("SELECT count(*) FROM sessions").fetchone()
    m = c.execute("SELECT count(*) FROM messages").fetchone()
    print('sessions_count:', s)
    print('messages_count:', m)
except Exception as e:
    print('error querying tables:', e)

# print a few rows if present
try:
    for row in c.execute("SELECT id, source, path, created_at FROM sessions LIMIT 5"):
        print('session:', row)
except:
    pass

try:
    for row in c.execute("SELECT rowid, session_id, snippet(messages, 1, '\\n', '\\n', '...') FROM messages LIMIT 5"):
        print('message:', row)
except Exception as e:
    print('message query error:', e)

conn.close()
