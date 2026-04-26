import sqlite3, os
from env_paths import csr_index_db

db = csr_index_db()
conn = sqlite3.connect(db)
c = conn.cursor()

q = 'interface design'
print('\nFTS5 MATCH for:', q)
try:
    for r in c.execute("SELECT sessions.id, sessions.path FROM messages JOIN sessions ON sessions.id = messages.session_id WHERE messages MATCH ? LIMIT 20", (q,)):
        print('match', r)
except Exception as e:
    print('fts error', e)

q2 = 'interface'
print('\nLIKE search for:', q2)
for r in c.execute("SELECT sessions.id, sessions.path FROM messages JOIN sessions ON sessions.id = messages.session_id WHERE messages.content LIKE ? LIMIT 50", ('%'+q2+'%',)):
    print('like', r)

print('\nShow small snippets (lowercased search):')
for r in c.execute("SELECT sessions.id, substr(messages.content, max(1, instr(lower(messages.content), 'interface')-60), 140) FROM messages JOIN sessions ON sessions.id = messages.session_id WHERE lower(messages.content) LIKE ? LIMIT 10", ('%interface%',)):
    print(r)

conn.close()
