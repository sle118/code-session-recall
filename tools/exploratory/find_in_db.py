import sqlite3, sys, os
from env_paths import csr_index_db

if len(sys.argv) < 2:
    print('usage: find_in_db.py <term>')
    sys.exit(1)

term = sys.argv[1]
term_l = term.lower()

db = csr_index_db()
if not os.path.exists(db):
    print('DB not found:', db)
    sys.exit(2)

conn = sqlite3.connect(db)
c = conn.cursor()

q = "SELECT sessions.id, sessions.path, substr(messages.content, max(1, instr(lower(messages.content), ?)-80), 160) FROM messages JOIN sessions ON sessions.id = messages.session_id WHERE lower(messages.content) LIKE ? LIMIT 50"
params = (term_l, '%'+term_l+'%')
try:
    for r in c.execute(q, params):
        sid, path, snippet = r
        print('---')
        print('session:', sid)
        print('path:', path)
        print('snippet:')
        print(snippet.replace('\n','\\n'))
except Exception as e:
    print('query error:', e)

conn.close()
