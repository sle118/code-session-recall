import os
from pathlib import Path
from env_paths import first_workspace_storage
base = first_workspace_storage()
print('base:', base)
if not base.exists():
    print('not found')
else:
    for p in base.rglob('state.vscdb'):
        print(p)
