import os
import sys
from pathlib import Path
from env_paths import first_workspace_storage

tokens = [arg.lower() for arg in sys.argv[1:]]
if not tokens:
    print('usage: search_copilot_chats.py <term> [term...]')
    raise SystemExit(2)

base = first_workspace_storage()
if not base.exists():
    print('workspaceStorage not found')
    raise SystemExit(1)

matches = []
for sub in base.iterdir():
    gh = sub / 'GitHub.copilot-chat' / 'chat-session-resources'
    if not gh.exists():
        continue
    for sid in gh.iterdir():
        for call in sid.iterdir():
            content = call / 'content.txt'
            if not content.exists():
                continue
            try:
                txt = content.read_text(errors='ignore')
            except:
                continue
            t = txt.lower()
            found = [tok for tok in tokens if tok in t]
            if found:
                matches.append((str(content), found))

for m in matches:
    print(m[0], 'tokens=', ', '.join(m[1]))

print('found', len(matches), 'matches')
