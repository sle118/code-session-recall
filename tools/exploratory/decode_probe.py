#!/usr/bin/env python3
import os, sqlite3, zlib, gzip, bz2, lzma, base64, json, binascii, re, sys
from pathlib import Path

APPDATA = os.getenv('APPDATA', '')
from env_paths import first_workspace_storage
BASE = first_workspace_storage()
TOKENS = ['chat', 'copilot', 'interactive-session', 'chat-session']
MAX_MATCHES = 80

def hexdump(data, width=16, maxlen=256):
    if not data:
        return ''
    show = data[:maxlen]
    lines = []
    for i in range(0, len(show), width):
        chunk = show[i:i+width]
        hexpart = ' '.join(f"{b:02x}" for b in chunk)
        asciipart = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f"{i:08x}  {hexpart:<{width*3}}  |{asciipart}|")
    return '\n'.join(lines)

# try common decompressors and decodings
def try_decode_bytes(b):
    results = []
    # direct decompressors
    try:
        dec = zlib.decompress(b)
        results.append(('zlib', dec))
    except Exception:
        pass
    try:
        dec = gzip.decompress(b)
        results.append(('gzip', dec))
    except Exception:
        pass
    try:
        dec = bz2.decompress(b)
        results.append(('bz2', dec))
    except Exception:
        pass
    try:
        dec = lzma.decompress(b)
        results.append(('lzma', dec))
    except Exception:
        pass

    # header-based scanning
    try:
        idx = b.find(b'\x78\x9c')
        if idx != -1:
            try:
                dec = zlib.decompress(b[idx:])
                results.append((f'zlib@{idx}', dec))
            except Exception:
                pass
    except Exception:
        pass
    try:
        idx = b.find(b'\x1f\x8b')
        if idx != -1:
            try:
                dec = gzip.decompress(b[idx:])
                results.append((f'gzip@{idx}', dec))
            except Exception:
                pass
    except Exception:
        pass

    # try interpreting as ascii/base64
    try:
        s = b.decode('ascii', errors='ignore')
        # find long base64-like substrings
        for m in re.findall(r'[A-Za-z0-9+/=]{40,}', s):
            try:
                bb = base64.b64decode(m)
                # try decompressors on decoded base64
                for name, dec in try_decode_bytes(bb):
                    results.append((f'base64->{name}', dec))
            except Exception:
                pass
    except Exception:
        pass

    # try common text decodings
    for enc in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'latin-1'):
        try:
            s = b.decode(enc, errors='ignore')
            results.append((f'text-{enc}', s.encode('utf-8')))
        except Exception:
            pass

    # return unique methods preserving order
    seen = set()
    out = []
    for name, dec in results:
        if name in seen:
            continue
        seen.add(name)
        out.append((name, dec))
    return out


def try_decode_value(value):
    # normalize memoryview
    try:
        if isinstance(value, memoryview):
            b = value.tobytes()
        elif isinstance(value, (bytes, bytearray)):
            b = bytes(value)
        else:
            # string-like
            s = str(value)
            s_strip = s.strip()
            # JSON string
            if s_strip.startswith('{') or s_strip.startswith('['):
                try:
                    return [('json', json.loads(s_strip))]
                except Exception:
                    pass
            # ascii data maybe base64
            try:
                b = s.encode('utf-8')
            except Exception:
                return []
    except Exception:
        return []

    return try_decode_bytes(b)


def main():
    if not BASE.exists():
        print('workspaceStorage not found at', BASE)
        return

    matches = 0
    for dbfile in BASE.rglob('state.vscdb'):
        try:
            conn = sqlite3.connect(str(dbfile))
            c = conn.cursor()
            rows = c.execute('SELECT key, value FROM ItemTable').fetchall()
        except Exception:
            continue

        for key, value in rows:
            if not key:
                continue
            lk = key.lower()
            if not any(tok in lk for tok in TOKENS):
                continue

            decoded_attempts = try_decode_value(value)
            print('\n--- FILE:', dbfile)
            print('KEY:', key)

            if decoded_attempts:
                for name, dec in decoded_attempts[:3]:
                    print('DECODED VIA:', name)
                    if isinstance(dec, (bytes, bytearray)):
                        try:
                            txt = dec.decode('utf-8', errors='ignore')
                            # show short sample
                            sample = txt[:1000]
                            print('SAMPLE_TEXT:', sample.replace('\n','\\n')[:500])
                        except Exception:
                            print('BINARY SAMPLE (hex/ascii):')
                            print(hexdump(dec, maxlen=256))
                    else:
                        try:
                            # JSON or structure
                            print('STRUCT SAMPLE:', json.dumps(dec, ensure_ascii=False)[:1000])
                        except Exception:
                            print('SAMPLE:', str(dec)[:1000])
            else:
                # can't decode anything: dump raw bytes as hex/ascii for first bytes
                try:
                    if isinstance(value, memoryview):
                        b = value.tobytes()
                    elif isinstance(value, (bytes, bytearray)):
                        b = bytes(value)
                    else:
                        b = str(value).encode('utf-8', errors='ignore')
                    print('NO DECODER. HEXDUMP:')
                    print(hexdump(b, maxlen=256))
                except Exception as e:
                    print('NO DECODER, and failed to hex-dump:', e)

            matches += 1
            if matches >= MAX_MATCHES:
                print('\nReached max matches', MAX_MATCHES)
                return

if __name__ == '__main__':
    main()
