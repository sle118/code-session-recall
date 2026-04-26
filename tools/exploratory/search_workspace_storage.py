#!/usr/bin/env python3
import os, sqlite3, zlib, json, sys, binascii
from pathlib import Path
from env_paths import first_workspace_storage

base = first_workspace_storage()
if not base.exists():
    print("No workspaceStorage at:", base)
    sys.exit(0)

tokens = [arg.lower() for arg in sys.argv[1:]]
if not tokens:
    print("usage: search_workspace_storage.py <term> [term...]")
    sys.exit(2)

matches = []
count_db = 0
for dbfile in base.rglob("state.vscdb"):
    count_db += 1
    try:
        conn = sqlite3.connect(str(dbfile))
        c = conn.cursor()
        rows = c.execute("SELECT key, value FROM ItemTable").fetchall()

        for key, value in rows:
            try:
                blob = value
                if isinstance(blob, memoryview):
                    blob = blob.tobytes()

                text = None
                if isinstance(blob, (bytes, bytearray)):
                    # try as UTF-8
                    try:
                        text = blob.decode("utf-8", errors="ignore")
                    except:
                        text = None

                    # try zlib decompress
                    if not text:
                        try:
                            dec = zlib.decompress(blob)
                            text = dec.decode("utf-8", errors="ignore")
                        except Exception:
                            text = text or None

                    # last resort: hex
                    if not text:
                        try:
                            text = binascii.hexlify(blob).decode()
                        except:
                            text = None
                else:
                    text = str(blob)

                tl = (text or "").lower()
                for tok in tokens:
                    if tok in tl:
                        # capture a small snippet showing the token
                        lines = [ln for ln in tl.splitlines() if tok in ln]
                        snippet = lines[0][:500] if lines else (tl[:200])
                        matches.append((str(dbfile), key, tok, snippet))
                        break
            except Exception as e:
                # ignore row errors
                continue
    except Exception as e:
        # ignore DB open errors
        continue

print(f"scanned {count_db} state.vscdb files, found {len(matches)} matches")
for m in matches:
    print("FILE:", m[0])
    print("KEY:", m[1])
    print("TOKEN:", m[2])
    print("SNIPPET:", m[3])
    print("---")

print("done")
