#!/usr/bin/env python3
import os, sys, sqlite3, json, hashlib, zlib, argparse, gzip, re
from pathlib import Path
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

DB_PATH = Path.home() / ".code-session-recall" / "index.sqlite"
CHAT_SESSION_INDEX_CACHE = {}

# Workspace-local session filtering. Remove or update this block when switching workspaces.
WORKSPACE_CURRENT_CHAT_SESSION_ID = "fcc80cf8-31e2-41a8-9243-fdf5e4c6070b"
WORKSPACE_EXCLUDED_CHAT_SESSION_IDS = {
    # This session was used to build/validate csr.py and pollutes recall searches.
    WORKSPACE_CURRENT_CHAT_SESSION_ID,
}

# ----------------------------
# DB (cache only)
# ----------------------------
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions(
        id TEXT PRIMARY KEY,
        source TEXT,
        path TEXT,
        chat_session_id TEXT,
        title TEXT,
        created_at TEXT,
        display_content TEXT
    )
    """)

    cols = {row[1] for row in c.execute("PRAGMA table_info(sessions)").fetchall()}
    if 'chat_session_id' not in cols:
        c.execute("ALTER TABLE sessions ADD COLUMN chat_session_id TEXT")
    if 'title' not in cols:
        c.execute("ALTER TABLE sessions ADD COLUMN title TEXT")
    if 'display_content' not in cols:
        c.execute("ALTER TABLE sessions ADD COLUMN display_content TEXT")

    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
        session_id, content
    )
    """)

    conn.commit()
    return conn


def hid(s): return hashlib.sha1(s.encode()).hexdigest()[:12]


def load_chat_session_index(state_db_path):
    key = str(state_db_path)
    if key in CHAT_SESSION_INDEX_CACHE:
        return CHAT_SESSION_INDEX_CACHE[key]

    entries = {}
    try:
        con = sqlite3.connect(state_db_path)
        cur = con.cursor()
        row = cur.execute("SELECT value FROM ItemTable WHERE key='chat.ChatSessionStore.index'").fetchone()
        if row:
            data = json.loads(row[0])
            entries = data.get('entries') or {}
    except Exception:
        entries = {}

    CHAT_SESSION_INDEX_CACHE[key] = entries
    return entries


def chat_entry_sort_key(entry):
    if not isinstance(entry, dict):
        return 0
    timing = entry.get('timing') or {}
    for key in ('lastrequestended', 'lastrequeststarted', 'created'):
        parsed = parse_timestamp(timing.get(key))
        if parsed:
            return parsed.timestamp()
    parsed = parse_timestamp(entry.get('lastmessagedate'))
    if parsed:
        return parsed.timestamp()
    return 0


def infer_title_from_state_db(state_db_path):
    entries = load_chat_session_index(state_db_path)
    titled_entries = [entry for entry in entries.values() if isinstance(entry, dict) and entry.get('title')]
    if not titled_entries:
        return None
    titled_entries.sort(key=chat_entry_sort_key, reverse=True)
    return titled_entries[0].get('title')


def infer_current_chat_session_id_from_state_db(state_db_path):
    entries = load_chat_session_index(state_db_path)
    titled_entries = [(sid, entry) for sid, entry in entries.items() if isinstance(entry, dict)]
    if not titled_entries:
        return None
    titled_entries.sort(key=lambda item: chat_entry_sort_key(item[1]), reverse=True)
    return titled_entries[0][0]


def lookup_title_for_chat_resource(chat_file_path):
    path = Path(chat_file_path)
    session_id = path.parent.parent.name
    state_db_path = path.parents[3] / 'state.vscdb'
    entries = load_chat_session_index(state_db_path)
    entry = entries.get(session_id)
    if isinstance(entry, dict):
        return entry.get('title')
    return None


def lookup_chat_session_id_for_chat_resource(chat_file_path):
    path = Path(chat_file_path)
    return path.parent.parent.name


def should_include_chat_session(chat_session_id, current_session_only=False, exclude_current_session=False, include_excluded=False, extra_excluded_ids=None):
    excluded_ids = set(extra_excluded_ids or [])
    if exclude_current_session and WORKSPACE_CURRENT_CHAT_SESSION_ID:
        excluded_ids.add(WORKSPACE_CURRENT_CHAT_SESSION_ID)

    if not include_excluded and not current_session_only:
        excluded_ids.update(WORKSPACE_EXCLUDED_CHAT_SESSION_IDS)

    if current_session_only:
        return bool(chat_session_id) and chat_session_id == WORKSPACE_CURRENT_CHAT_SESSION_ID

    if chat_session_id and chat_session_id in excluded_ids:
        return False

    return True


# ----------------------------
# VS CODE / COPILOT EXTRACTION
# ----------------------------
def try_decode(value):
    """Best effort decode of VS Code blob"""
    try:
        # handle sqlite memoryview blobs
        if isinstance(value, memoryview):
            value = value.tobytes()

        # If bytes, try common decompression first (zlib/gzip), then fall back to text
        if isinstance(value, (bytes, bytearray)):
            b = bytes(value)

            # 1) try direct zlib
            try:
                dec = zlib.decompress(b)
                s = dec.decode('utf-8', errors='ignore')
                if s and (s.strip().startswith('{') or s.strip().startswith('[')):
                    return json.loads(s)
                return s
            except Exception:
                pass

            # 2) try gzip
            try:
                dec = gzip.decompress(b)
                s = dec.decode('utf-8', errors='ignore')
                if s and (s.strip().startswith('{') or s.strip().startswith('[')):
                    return json.loads(s)
                return s
            except Exception:
                pass

            # 3) try to find compressed header inside blob and decompress from there
            try:
                idx = b.find(b'\x78\x9c')
                if idx != -1:
                    dec = zlib.decompress(b[idx:])
                    s = dec.decode('utf-8', errors='ignore')
                    if s and (s.strip().startswith('{') or s.strip().startswith('[')):
                        return json.loads(s)
                    return s
            except Exception:
                pass

            try:
                idx = b.find(b'\x1f\x8b')
                if idx != -1:
                    dec = gzip.decompress(b[idx:])
                    s = dec.decode('utf-8', errors='ignore')
                    if s and (s.strip().startswith('{') or s.strip().startswith('[')):
                        return json.loads(s)
                    return s
            except Exception:
                pass

            # 4) fallback to plain utf-8 decode
            try:
                s = b.decode('utf-8', errors='ignore')
                if s and (s.strip().startswith('{') or s.strip().startswith('[')):
                    try:
                        return json.loads(s)
                    except Exception:
                        return s
                return s
            except Exception:
                return None

        # If string, try parse JSON then return string
        if isinstance(value, str):
            s = value.strip()
            if s.startswith('{') or s.startswith('['):
                try:
                    return json.loads(s)
                except Exception:
                    return s
            return s
    except Exception:
        pass
    return None


def extract_messages(obj):
    """Recursively find chat-like structures"""
    results = []

    if isinstance(obj, dict):
        if "role" in obj and "content" in obj:
            results.append(obj["content"])

        for v in obj.values():
            results += extract_messages(v)

    elif isinstance(obj, list):
        for v in obj:
            results += extract_messages(v)

    return results


# ----------------------------
# Timestamp helpers and text extraction
# ----------------------------
def parse_timestamp(v):
    """Parse various timestamp formats into a timezone-aware UTC datetime."""
    try:
        if v is None:
            return None
        # Numeric epoch (seconds or milliseconds)
        if isinstance(v, (int, float)):
            ts = float(v)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(v, str):
            s = v.strip()
            # pure digits (epoch)
            if re.fullmatch(r'\d{10,13}', s):
                ts = float(s)
                if ts > 1e12:
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts, tz=timezone.utc)

            # look for epoch-like number embedded in string (/Date(1600000000000)/)
            m = re.search(r'(\d{10,13})', s)
            if m:
                ts = float(m.group(1))
                if ts > 1e12:
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts, tz=timezone.utc)

            # Try ISO formats (allow trailing Z)
            try:
                t = s.replace('Z', '+00:00')
                dt = datetime.fromisoformat(t)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                return None
    except Exception:
        pass
    return None


def extract_timestamps_from_text(text):
    """Find ISO-like timestamps in free text and return list of UTC datetimes."""
    if not text:
        return []
    candidates = []
    # ISO-like patterns: 2023-01-02T03:04:05Z or with offset or space
    iso_re = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})?')
    for m in iso_re.findall(text):
        dt = parse_timestamp(m)
        if dt:
            candidates.append(dt)

    # fallback: find epoch-like numbers (10-13 digits)
    if not candidates:
        for m in re.findall(r'\b\d{10,13}\b', text):
            dt = parse_timestamp(m)
            if dt:
                candidates.append(dt)

    return candidates


# ----------------------------
# Per-key formatting handlers (scaffolding)
# ----------------------------
def format_raw_payload(val):
    try:
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False, indent=2)
        return str(val)
    except Exception:
        return str(val)


def clip_text(text, max_len=220):
    text = ' '.join(str(text or '').split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + '...'


def unique_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def stringify_text(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def append_unique_text(target, text):
    text = stringify_text(text).strip()
    if not text:
        return
    if text not in target:
        target.append(text)


PATH_RE = re.compile(
    r'(?i)(?:[A-Z]:\\[^\s"<>|]+|/(?:home|users|mnt|var|tmp|etc|opt|workspace|workspaces)/[^\s"<>|]+|/[a-z]/[^\s"<>|]+|[\w./\\-]+\.(?:py|md|json|jsonl|sqlite|vscdb|txt|ps1|sh|ts|tsx|js|jsx|yaml|yml))'
)
COMMAND_RE = re.compile(r'(?i)\b(?:python|py|git|rg|grep|find|Get-ChildItem|Select-String|npm|pnpm|yarn|pytest|pip|uv|csr)\b')
COMMAND_LINE_RE = re.compile(r'(?i)^\s*(?:[-*]\s*)?`?(?:(?:python|py|git|rg|grep|find|Get-ChildItem|Select-String|npm|pnpm|yarn|pytest|pip|uv)\b|csr\s+[a-z][\w-]*)')
ERROR_RE = re.compile(r'(?i)\b(?:error|exception|traceback|failed|denied|missing|timeout|out of memory|heap|not found|exit code [1-9])\b')
NEXT_RE = re.compile(r'(?i)\b(?:todo|next|follow-?up|roadmap|planned|blocked|issue|fixme|later)\b')
DECISION_RE = re.compile(r'(?i)\b(?:decision|decided|choose|chosen|approach|rationale|tradeoff|trade-off|we will|should)\b')


def add_unique_limited(target, value, limit=20):
    value = stringify_text(value).strip()
    if not value or value in target:
        return
    if len(target) < limit:
        target.append(value)


def uri_to_path(value):
    if not isinstance(value, dict):
        return None
    path = value.get('fsPath') or value.get('path') or value.get('external')
    if not path:
        return None
    path = str(path)
    if path.startswith('file:///'):
        path = path.replace('file:///', '', 1)
    return path


def collect_uri_paths(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 8:
        return out
    if isinstance(obj, dict):
        path = uri_to_path(obj)
        if path:
            add_unique_limited(out, path, limit=50)
        for value in obj.values():
            collect_uri_paths(value, out=out, depth=depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            collect_uri_paths(item, out=out, depth=depth + 1)
    return out


def extract_paths_from_text(text, limit=30):
    out = []
    for match in PATH_RE.findall(stringify_text(text)):
        cleaned = match.rstrip('.,;:)')
        add_unique_limited(out, cleaned, limit=limit)
    return out


def high_signal_lines(text, query=None, limit=12):
    query_l = (query or '').lower().strip()
    scored = []
    for line in stringify_text(text).splitlines():
        original = line.strip()
        if not original:
            continue
        line_l = original.lower()
        score = 0
        if query_l and query_l in line_l:
            score += 8
        if original.startswith('#'):
            score += 4
        if PATH_RE.search(original):
            score += 5
        if COMMAND_LINE_RE.search(original):
            score += 4
        if ERROR_RE.search(original):
            score += 7
        if NEXT_RE.search(original):
            score += 5
        if DECISION_RE.search(original):
            score += 3
        if '`' in original or re.search(r'\b[A-Za-z_][A-Za-z0-9_]{3,}\b', original):
            score += 1
        if score:
            scored.append((score, len(scored), clip_text(original, 260)))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return unique_preserve_order([item[2] for item in scored[:limit]])


def classify_fact_line(line):
    if ERROR_RE.search(line):
        return 'errors'
    if COMMAND_LINE_RE.search(line):
        return 'commands'
    if NEXT_RE.search(line) or DECISION_RE.search(line):
        return 'nextSteps'
    return 'highlights'


def extract_facts_from_text(text, query=None):
    facts = {
        'files': extract_paths_from_text(text),
        'commands': [],
        'errors': [],
        'nextSteps': [],
        'highlights': [],
    }
    for line in high_signal_lines(text, query=query, limit=20):
        add_unique_limited(facts[classify_fact_line(line)], line, limit=12)
    return facts


def merge_facts(target, source, limit=20):
    for key, values in (source or {}).items():
        if key not in target:
            target[key] = []
        for value in values or []:
            if key == 'toolEvents' and isinstance(value, dict):
                marker = json.dumps(value, sort_keys=True, ensure_ascii=False)
                existing = {
                    json.dumps(item, sort_keys=True, ensure_ascii=False)
                    for item in target[key]
                    if isinstance(item, dict)
                }
                if marker not in existing and len(target[key]) < limit:
                    target[key].append(value)
            else:
                add_unique_limited(target[key], value, limit=limit)
    return target


def summarize_tool_invocation(part):
    if not isinstance(part, dict):
        return None
    data = part.get('toolSpecificData') or {}
    command_line = data.get('commandLine') or {}
    state = data.get('terminalCommandState') or {}
    cwd = uri_to_path(data.get('cwd')) or stringify_text(data.get('cwd')).strip()
    event = {
        'kind': data.get('kind') or part.get('toolId') or 'tool',
        'toolId': part.get('toolId'),
        'command': command_line.get('original') or command_line.get('forDisplay'),
        'cwd': cwd or None,
        'language': data.get('language'),
        'exitCode': state.get('exitCode'),
        'durationMs': state.get('duration'),
        'uri': data.get('terminalCommandUri'),
    }
    output = (data.get('terminalCommandOutput') or {}).get('text')
    if output:
        event['outputHighlights'] = high_signal_lines(output, limit=8)
        event['outputLineCount'] = (data.get('terminalCommandOutput') or {}).get('lineCount')
    return {k: v for k, v in event.items() if v not in (None, '', [], {})}


def entry_timestamp_iso(entry):
    if not isinstance(entry, dict):
        return None
    timing = entry.get('timing') or {}
    for key in ('lastrequestended', 'lastrequeststarted', 'created'):
        parsed = parse_timestamp(timing.get(key))
        if parsed:
            return parsed.isoformat()
    parsed = parse_timestamp(entry.get('lastmessagedate') or entry.get('lastMessageDate'))
    if parsed:
        return parsed.isoformat()
    return None


def lookup_chat_session_entry(session_id, state_db_path):
    if not session_id:
        return {}
    entries = load_chat_session_index(state_db_path)
    entry = entries.get(session_id)
    return entry if isinstance(entry, dict) else {}


def set_path_value(container, path, value, append=False):
    if container is None:
        return False

    current = container
    for idx, key in enumerate(path):
        is_last = idx == len(path) - 1
        next_key = None if is_last else path[idx + 1]

        if isinstance(key, int):
            if not isinstance(current, list):
                return False
            while len(current) <= key:
                current.append({} if isinstance(next_key, str) else [])

            if is_last:
                if append and isinstance(current[key], list) and isinstance(value, list):
                    current[key].extend(value)
                elif append and current[key] is None and isinstance(value, list):
                    current[key] = list(value)
                else:
                    current[key] = value
                return True

            if not isinstance(current[key], (dict, list)):
                current[key] = {} if isinstance(next_key, str) else []
            current = current[key]
            continue

        if not isinstance(current, dict):
            return False

        if is_last:
            if append and isinstance(current.get(key), list) and isinstance(value, list):
                current[key].extend(value)
            elif append and isinstance(value, list):
                current[key] = list(value)
            else:
                current[key] = value
            return True

        if key not in current or not isinstance(current[key], (dict, list)):
            current[key] = {} if isinstance(next_key, str) else []
        current = current[key]

    return False


def load_chat_session_state(jsonl_path):
    state = None
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                kind = record.get('kind')

                if kind == 0:
                    state = record.get('v')
                    continue

                if state is None:
                    continue

                path = record.get('k') or []
                if not path:
                    continue

                if kind == 1:
                    set_path_value(state, path, record.get('v'), append=False)
                elif kind == 2:
                    set_path_value(state, path, record.get('v'), append=True)
    except Exception:
        return None

    return state


def extract_response_parts(response_parts):
    assistant_texts = []
    tool_texts = []
    tool_events = []

    for part in response_parts or []:
        if not isinstance(part, dict):
            append_unique_text(assistant_texts, part)
            continue

        kind = part.get('kind')
        if kind == 'thinking':
            continue

        if kind == 'toolInvocationSerialized':
            invocation_message = part.get('invocationMessage')
            past_tense_message = part.get('pastTenseMessage')
            invocation = invocation_message.get('value') if isinstance(invocation_message, dict) else invocation_message
            past = past_tense_message.get('value') if isinstance(past_tense_message, dict) else past_tense_message
            append_unique_text(tool_texts, past or invocation)
            event = summarize_tool_invocation(part)
            if event:
                tool_events.append(event)
            continue

        append_unique_text(assistant_texts, part.get('value'))

    return assistant_texts, tool_texts, tool_events


def parse_chat_session_state(state, entry=None):
    if not isinstance(state, dict):
        return None

    requests = state.get('requests') or []
    if not isinstance(requests, list) or not requests:
        return None

    normalized_requests = []
    all_models = []
    timestamps = []
    search_chunks = []
    facts = {
        'files': [],
        'commands': [],
        'errors': [],
        'nextSteps': [],
        'highlights': [],
        'editedFiles': [],
        'toolEvents': [],
    }

    for i, request in enumerate(requests):
        if not isinstance(request, dict):
            continue

        message = request.get('message') or {}
        user_text = stringify_text(message.get('text')).strip()
        result = request.get('result') or {}
        assistant_texts, tool_texts, tool_events = extract_response_parts(request.get('response') or [])
        append_unique_text(assistant_texts, result.get('response'))

        if not user_text and not assistant_texts and not tool_texts:
            continue

        request_facts = {
            'files': [],
            'commands': [],
            'errors': [],
            'nextSteps': [],
            'highlights': [],
            'editedFiles': [],
            'toolEvents': [],
        }
        merge_facts(request_facts, extract_facts_from_text(user_text), limit=12)
        for text in assistant_texts:
            merge_facts(request_facts, extract_facts_from_text(text), limit=12)
        for text in tool_texts:
            merge_facts(request_facts, extract_facts_from_text(text), limit=12)

        edited_files = []
        for event in request.get('editedFileEvents') or []:
            if isinstance(event, dict):
                path = uri_to_path(event.get('uri'))
                if path:
                    add_unique_limited(edited_files, path, limit=20)
        for path in collect_uri_paths(request.get('contentReferences') or []):
            add_unique_limited(request_facts['files'], path, limit=20)
        for path in edited_files:
            add_unique_limited(request_facts['editedFiles'], path, limit=20)
            add_unique_limited(request_facts['files'], path, limit=20)

        for event in tool_events:
            request_facts['toolEvents'].append(event)
            if event.get('command'):
                add_unique_limited(request_facts['commands'], event.get('command'), limit=20)
            if event.get('cwd'):
                add_unique_limited(request_facts['files'], event.get('cwd'), limit=20)
            for line in event.get('outputHighlights') or []:
                add_unique_limited(request_facts[classify_fact_line(line)], line, limit=12)

        model_id = request.get('modelId') or (state.get('inputState') or {}).get('selectedModel', {}).get('identifier')
        if model_id:
            all_models.append(model_id)

        ts = parse_timestamp(request.get('timestamp'))
        if ts:
            timestamps.append(ts)

        entry_data = {
            'i': i,
            'requestId': request.get('requestId'),
            'userText': user_text,
            'userPreview': clip_text(user_text, 240),
            'assistantTexts': assistant_texts,
            'assistantPreview': clip_text(' '.join(assistant_texts), 240) if assistant_texts else '',
            'toolEventCount': len(tool_texts),
            'toolEvents': tool_events[:8],
            'facts': {k: v for k, v in request_facts.items() if v},
            'modelId': model_id,
        }

        if ts:
            entry_data['ts'] = ts.isoformat().replace('+00:00', 'Z')
            entry_data['ts_human'] = ts.strftime('%Y-%m-%d %H:%M:%S UTC')

        normalized_requests.append(entry_data)

        if user_text:
            search_chunks.append(f"USER\n{user_text}")
        for text in assistant_texts:
            search_chunks.append(f"ASSISTANT\n{text}")
        for text in tool_texts:
            search_chunks.append(f"TOOL\n{text}")
        for event in tool_events:
            if event.get('command'):
                search_chunks.append(f"COMMAND\n{event.get('command')}")
            for line in event.get('outputHighlights') or []:
                search_chunks.append(f"TOOL_OUTPUT\n{line}")
        merge_facts(facts, request_facts, limit=30)

    if not normalized_requests:
        return None

    if entry:
        created = parse_timestamp((entry.get('timing') or {}).get('created'))
        ended = parse_timestamp((entry.get('timing') or {}).get('lastRequestEnded'))
        if created:
            timestamps.append(created)
        if ended:
            timestamps.append(ended)

    summary = {
        'requestCount': len(normalized_requests),
        'assistantTurnCount': sum(1 for item in normalized_requests if item.get('assistantTexts')),
        'toolEventCount': sum(item.get('toolEventCount') or 0 for item in normalized_requests),
        'models': unique_preserve_order([item for item in all_models if item]),
        'lastUserPrompt': normalized_requests[-1].get('userPreview') or None,
        'lastAssistantReply': next((item.get('assistantPreview') for item in reversed(normalized_requests) if item.get('assistantPreview')), None),
    }

    if timestamps:
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        summary['firstTimestamp'] = first_ts.isoformat().replace('+00:00', 'Z')
        summary['lastTimestamp'] = last_ts.isoformat().replace('+00:00', 'Z')
        summary['timeRangeHuman'] = f"{first_ts.strftime('%Y-%m-%d %H:%M:%S UTC')} -> {last_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}"

    return {
        'summary': summary,
        'facts': {k: v for k, v in facts.items() if v},
        'recentRequests': normalized_requests[-8:],
        'requests': normalized_requests,
        'searchText': '\n\n'.join(search_chunks),
    }


def format_chat_session_transcript(state, title=None, entry=None):
    envelope = parse_chat_session_state(state, entry=entry)
    if not envelope:
        return format_raw_payload(state)

    summary = envelope.get('summary') or {}
    facts = envelope.get('facts') or {}
    lines = []
    lines.append('# CHAT SESSION')
    if title:
        lines.append(f'Title: {title}')
    lines.append(f"Requests: {summary.get('requestCount')} | assistant replies: {summary.get('assistantTurnCount')} | tool events: {summary.get('toolEventCount')}")
    if summary.get('timeRangeHuman'):
        lines.append(f"Time range: {summary.get('timeRangeHuman')}")
    if summary.get('models'):
        lines.append(f"Models: {', '.join(summary.get('models'))}")
    if summary.get('lastUserPrompt'):
        lines.append(f"Last user prompt: {summary.get('lastUserPrompt')}")
    if summary.get('lastAssistantReply'):
        lines.append(f"Last assistant reply: {summary.get('lastAssistantReply')}")
    lines.append('')

    def add_section(label, values, limit=10):
        values = values or []
        if not values:
            return
        lines.append(f'{label}:')
        for value in values[:limit]:
            lines.append(f'- {value}')
        lines.append('')

    add_section('Files mentioned', facts.get('files'), limit=12)
    add_section('Edited files', facts.get('editedFiles'), limit=12)
    add_section('Commands mentioned', facts.get('commands'), limit=10)
    add_section('Errors mentioned', facts.get('errors'), limit=8)
    add_section('Decisions / next steps', facts.get('nextSteps'), limit=10)
    add_section('Other high-signal lines', facts.get('highlights'), limit=8)

    if facts.get('toolEvents'):
        lines.append('Tool events:')
        for event in facts.get('toolEvents', [])[:8]:
            bits = []
            if event.get('kind'):
                bits.append(str(event.get('kind')))
            if event.get('command'):
                bits.append(f"command={event.get('command')}")
            if event.get('exitCode') is not None:
                bits.append(f"exit={event.get('exitCode')}")
            if event.get('durationMs') is not None:
                bits.append(f"durationMs={event.get('durationMs')}")
            if event.get('cwd'):
                bits.append(f"cwd={event.get('cwd')}")
            lines.append(f"- {' | '.join(bits)}")
            for line in event.get('outputHighlights') or []:
                lines.append(f"  output: {line}")
        lines.append('')

    lines.append('Recent turns:')
    for item in envelope.get('recentRequests') or []:
        ts_iso = item.get('ts') or 'unknown-time'
        lines.append(f"- {ts_iso} | turn={item.get('i')} | model={item.get('modelId') or '-'}")
        if item.get('userPreview'):
            lines.append(f"  USER: {item.get('userPreview')}")
        if item.get('assistantPreview'):
            lines.append(f"  ASSISTANT: {item.get('assistantPreview')}")
        turn_facts = item.get('facts') or {}
        for label, key in (
            ('files', 'files'),
            ('commands', 'commands'),
            ('errors', 'errors'),
            ('next', 'nextSteps'),
        ):
            values = turn_facts.get(key) or []
            if values:
                lines.append(f"  {label}: {'; '.join(values[:3])}")
        lines.append('')

    json_payload = {
        'summary': summary,
        'facts': {
            'files': (facts.get('files') or [])[:20],
            'editedFiles': (facts.get('editedFiles') or [])[:20],
            'commands': (facts.get('commands') or [])[:20],
            'errors': (facts.get('errors') or [])[:20],
            'nextSteps': (facts.get('nextSteps') or [])[:20],
            'highlights': (facts.get('highlights') or [])[:20],
            'toolEvents': (facts.get('toolEvents') or [])[:12],
        },
        'recentRequests': [
            {
                'i': item.get('i'),
                'requestId': item.get('requestId'),
                'ts': item.get('ts'),
                'ts_human': item.get('ts_human'),
                'userPreview': item.get('userPreview'),
                'assistantPreview': item.get('assistantPreview'),
                'toolEventCount': item.get('toolEventCount'),
                'facts': item.get('facts'),
                'modelId': item.get('modelId'),
            }
            for item in envelope.get('recentRequests') or []
        ],
    }
    lines.append('----- JSON -----')
    lines.append(json.dumps(json_payload, ensure_ascii=False, indent=2))
    return '\n'.join(lines)


def is_self_generated_artifact(path_str, raw_text=None, parsed_json=None):
    path_lower = str(path_str or '').lower()

    # Skip terminal/tool capture artifacts produced while validating this tool.
    if 'github.copilot-chat\\chat-session-resources' in path_lower:
        if isinstance(parsed_json, list) and parsed_json:
            if all(isinstance(item, dict) and {'id', 'source', 'path', 'content'}.issubset(item.keys()) for item in parsed_json):
                return True
        if isinstance(parsed_json, dict) and {'id', 'content'}.issubset(parsed_json.keys()) and len(parsed_json) <= 3:
            return True

    text = raw_text or ''
    normalized = text.lstrip()
    if normalized.startswith('PS ') or normalized.startswith('session-recall>'):
        return True
    if normalized.startswith('# SESSION') or normalized.startswith('# INTERACTIVE SESSION'):
        return True
    if 'Large tool result' in text and 'written to file' in text:
        return True

    return False


def path_mtime_iso(path_str):
    try:
        ts = Path(path_str).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return None


def envelope_last_timestamp_iso(decoded):
    envelope = parse_interactive_session(decoded)
    if not envelope:
        return None
    summary = envelope.get('summary') or {}
    return summary.get('lastTimestamp') or summary.get('firstTimestamp')


def collect_candidate_timestamps(obj, found=None, depth=0, max_found=16):
    if found is None:
        found = []
    if depth > 6 or len(found) >= max_found:
        return found

    timestamp_keys = {
        'timestamp', 'time', 'createdat', 'created_at', 'created', 'date', 'ts',
        'createdtime', 'createdutc', 'mtime', 'updatedat', 'lastmessagedate',
        'lastrequeststarted', 'lastrequestended'
    }

    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in timestamp_keys:
                parsed = parse_timestamp(value)
                if parsed:
                    found.append(parsed)
                    if len(found) >= max_found:
                        return found
            collect_candidate_timestamps(value, found=found, depth=depth + 1, max_found=max_found)
            if len(found) >= max_found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            collect_candidate_timestamps(item, found=found, depth=depth + 1, max_found=max_found)
            if len(found) >= max_found:
                return found

    return found


def parse_interactive_session(decoded):
    """Normalize `memento/interactive-session` into a resume-oriented envelope."""
    # If we were given a JSON string, attempt to parse it
    if isinstance(decoded, str):
        s = decoded.strip()
        if s.startswith('{') or s.startswith('['):
            try:
                decoded = json.loads(s)
            except Exception:
                return None

    # If decoded contains an inner 'content' field that's a JSON string, try to parse it
    if isinstance(decoded, dict) and 'content' in decoded and isinstance(decoded['content'], str):
        inner = decoded['content'].strip()
        if inner.startswith('{') or inner.startswith('['):
            try:
                decoded = json.loads(inner)
            except Exception:
                pass

    # Locate the copilot message list
    messages = []
    if isinstance(decoded, dict):
        if 'history' in decoded and isinstance(decoded.get('history'), dict) and isinstance(decoded['history'].get('copilot'), list):
            messages = decoded['history']['copilot']
        elif isinstance(decoded.get('copilot'), list):
            messages = decoded.get('copilot')
        else:
            def find_copilot(obj):
                if isinstance(obj, dict):
                    if 'copilot' in obj and isinstance(obj['copilot'], list):
                        return obj['copilot']
                    for value in obj.values():
                        found = find_copilot(value)
                        if found:
                            return found
                elif isinstance(obj, list):
                    for item in obj:
                        found = find_copilot(item)
                        if found:
                            return found
                return None

            found = find_copilot(decoded)
            if found:
                messages = found

    if not messages:
        return None

    def extract_attachments(message):
        attachments = []
        for attachment in (message.get('attachments') or []):
            if isinstance(attachment, dict):
                value = attachment.get('value') or attachment
                if isinstance(value, dict):
                    path = value.get('fsPath') or value.get('path') or value.get('external') or value.get('id') or value.get('name')
                    if path:
                        attachments.append(path)
                    else:
                        try:
                            attachments.append(json.dumps(value, ensure_ascii=False))
                        except Exception:
                            attachments.append(str(value))
                else:
                    attachments.append(str(value))
            else:
                attachments.append(str(attachment))
        return unique_preserve_order([item for item in attachments if item])

    def extract_message_timestamp(message):
        if not isinstance(message, dict):
            return None
        for key in ('timestamp', 'time', 'createdAt', 'created_at', 'created', 'date', 'ts', 'createdTime', 'createdUtc', 'mtime', 'updatedAt'):
            parsed = parse_timestamp(message.get(key))
            if parsed:
                return parsed
        for meta_key in ('meta', 'metadata'):
            meta = message.get(meta_key)
            if isinstance(meta, dict):
                for key in ('timestamp', 'time', 'createdAt', 'created_at', 'created', 'date', 'ts'):
                    parsed = parse_timestamp(meta.get(key))
                    if parsed:
                        return parsed
        return None

    root_timestamps = collect_candidate_timestamps(decoded)

    normalized_messages = []
    all_models = []
    all_attachments = []
    timestamps = []

    for i, message in enumerate(messages):
        if not isinstance(message, dict):
            continue

        text = (message.get('inputText') or message.get('inputtext') or message.get('text') or '').strip()
        attachments = extract_attachments(message)
        mode = message.get('mode') or {}
        selected_model = message.get('selectedModel') or {}
        model_id = None
        model_name = None
        if isinstance(selected_model, dict):
            model_id = selected_model.get('identifier') or selected_model.get('id')
            metadata = selected_model.get('metadata') or {}
            if isinstance(metadata, dict):
                model_name = metadata.get('name')
        elif selected_model:
            model_id = str(selected_model)

        timestamp = extract_message_timestamp(message)
        if timestamp:
            timestamps.append(timestamp)

        model_label = model_name or model_id
        if model_label:
            all_models.append(model_label)
        all_attachments.extend(attachments)

        # Skip low-value entries that carry no resumable content.
        if not text and not attachments:
            continue

        normalized_entry = {
            'i': i,
            'inputText': text,
            'inputPreview': clip_text(text, 240),
            'attachments': attachments,
            'mode': {
                'id': mode.get('id') if isinstance(mode, dict) else mode,
                'kind': mode.get('kind') if isinstance(mode, dict) else None,
            },
            'selectedModel': {
                'identifier': model_id,
                'name': model_name,
            },
            'permissionLevel': message.get('permissionLevel'),
        }

        if timestamp:
            normalized_entry['ts'] = timestamp.isoformat().replace('+00:00', 'Z')
            normalized_entry['ts_human'] = timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')

        if attachments:
            normalized_entry['attachmentCount'] = len(attachments)

        normalized_messages.append(normalized_entry)

    if not normalized_messages:
        return None

    if root_timestamps:
        timestamps.extend(root_timestamps)

    all_models = unique_preserve_order([item for item in all_models if item])
    all_attachments = unique_preserve_order([item for item in all_attachments if item])
    meaningful_prompts = [entry for entry in normalized_messages if entry.get('inputText')]
    recent_messages = normalized_messages[-8:]
    recent_prompts = [entry.get('inputPreview') for entry in meaningful_prompts[-5:] if entry.get('inputPreview')]

    summary = {
        'messageCount': len(normalized_messages),
        'meaningfulPromptCount': len(meaningful_prompts),
        'attachmentCount': len(all_attachments),
        'models': all_models,
        'recentAttachments': all_attachments[:8],
        'recentPrompts': recent_prompts,
        'lastMeaningfulPrompt': meaningful_prompts[-1]['inputPreview'] if meaningful_prompts else None,
    }

    if timestamps:
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        summary['firstTimestamp'] = first_ts.isoformat().replace('+00:00', 'Z')
        summary['lastTimestamp'] = last_ts.isoformat().replace('+00:00', 'Z')
        summary['timeRangeHuman'] = f"{first_ts.strftime('%Y-%m-%d %H:%M:%S UTC')} -> {last_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}"

        if meaningful_prompts:
            last_meaningful = meaningful_prompts[-1]
            if 'ts' not in last_meaningful:
                last_meaningful['ts_inferred'] = summary['lastTimestamp']
                last_meaningful['ts_human_inferred'] = last_ts.strftime('%Y-%m-%d %H:%M:%S UTC')

    return {
        'summary': summary,
        'recentMessages': recent_messages,
        'searchText': '\n'.join(entry.get('inputText') for entry in normalized_messages if entry.get('inputText')),
        'searchPrompts': [entry.get('inputPreview') for entry in normalized_messages if entry.get('inputPreview')],
    }


def format_memento_interactive_session(decoded):
    """Format `memento/interactive-session` payloads into a resume-oriented handoff view."""
    try:
        envelope = parse_interactive_session(decoded)
        if not envelope:
            return format_raw_payload(decoded)

        summary = envelope['summary']
        lines = []
        lines.append("# INTERACTIVE SESSION")
        lines.append(f"Messages: {summary.get('messageCount')} total, {summary.get('meaningfulPromptCount')} with resumable prompt text")
        if summary.get('timeRangeHuman'):
            lines.append(f"Time range: {summary.get('timeRangeHuman')}")
        if summary.get('models'):
            lines.append(f"Models: {', '.join(summary.get('models'))}")
        if summary.get('recentAttachments'):
            lines.append(f"Recent files: {', '.join(summary.get('recentAttachments'))}")
        if summary.get('lastMeaningfulPrompt'):
            lines.append(f"Last prompt: {summary.get('lastMeaningfulPrompt')}")
        if summary.get('recentPrompts'):
            lines.append("Recent prompt trail:")
            for idx, prompt in enumerate(summary.get('recentPrompts'), start=1):
                lines.append(f"  {idx}. {prompt}")
        lines.append("")

        lines.append("Recent meaningful turns:")
        for entry in envelope['recentMessages']:
            ts_iso = entry.get('ts') or (('~' + entry.get('ts_inferred')) if entry.get('ts_inferred') else 'unknown-time')
            model_id = entry.get('selectedModel', {}).get('identifier') or '-'
            permission = entry.get('permissionLevel') or '-'
            lines.append(f"- {ts_iso} | i={entry.get('i')} | model={model_id} | permission={permission}")
            if entry.get('inputPreview'):
                lines.append(f"  {entry.get('inputPreview')}")
            if entry.get('attachments'):
                lines.append(f"  Attachments: {', '.join(entry.get('attachments'))}")
            lines.append("")

        if envelope.get('searchPrompts'):
            lines.append("----- SEARCH PROMPTS -----")
            for prompt in envelope['searchPrompts']:
                lines.append(prompt)
            lines.append("")

        try:
            json_payload = {
                'summary': envelope.get('summary'),
                'recentMessages': envelope.get('recentMessages'),
                'searchPrompts': envelope.get('searchPrompts', [])[-12:],
            }
            json_block = json.dumps(json_payload, ensure_ascii=False, indent=2)
            lines.append("----- JSON -----")
            lines.append(json_block)
        except Exception:
            pass

        return "\n".join(lines)
    except Exception:
        return format_raw_payload(decoded)


def format_chat_chatsessionstore_index(decoded):
    return format_raw_payload(decoded)


def format_memento_chat_todo_list(decoded):
    return format_raw_payload(decoded)


def format_chat_customModes(decoded):
    return format_raw_payload(decoded)


def format_copilot_chat_file(raw_text, parsed_json=None):
    # If parsed JSON contains a nested `content` that represents the chat history,
    # attempt to format it using the memento/interactice-session formatter.
    if parsed_json is not None:
        try:
            if isinstance(parsed_json, dict):
                # Some content.json files have the shape { id: ..., content: "{...}" }
                if 'content' in parsed_json:
                    inner = parsed_json['content']
                    if isinstance(inner, str) and (inner.strip().startswith('{') or inner.strip().startswith('[')):
                        try:
                            inner_parsed = json.loads(inner)
                            return format_memento_interactive_session(inner_parsed)
                        except Exception:
                            pass
                    elif isinstance(inner, (dict, list)):
                        return format_memento_interactive_session(inner)

                # Direct history object
                if 'history' in parsed_json and isinstance(parsed_json.get('history'), dict) and isinstance(parsed_json['history'].get('copilot'), list):
                    return format_memento_interactive_session(parsed_json)
        except Exception:
            pass

        return format_raw_payload(parsed_json)

    return str(raw_text)


def format_payload_for_key(key, decoded, raw=None):
    """Dispatch to key-specific formatter. Returns formatted string or None to fallback."""
    lk = (key or "").lower()

    # memento/interactive-session stores the full chat history JSON
    if 'memento/interactive-session' in lk or 'interactive-session' in lk:
        return format_memento_interactive_session(decoded)

    # chat.ChatSessionStore.index -> session metadata
    if 'chat.chatsessionstore.index' in lk or 'chat.chatsessionstore' in lk:
        return format_chat_chatsessionstore_index(decoded)

    # todo lists per session
    if 'memento/chat-todo-list' in lk or 'chat-todo-list' in lk:
        return format_memento_chat_todo_list(decoded)

    # custom modes definitions
    if 'chat.custommodes' in lk or 'custommodes' in lk:
        return format_chat_customModes(decoded)

    # file-based copilot chat content
    if 'content' in lk or 'content.txt' in lk or 'content.json' in lk or 'copilot-chat' in lk:
        return format_copilot_chat_file(raw, decoded if isinstance(decoded, (dict, list)) else None)

    # generic chat keys
    if 'chat' in lk:
        return format_raw_payload(decoded)

    return None


def scan_vscode():
    base = Path(os.getenv("APPDATA", "")) / "Code" / "User" / "workspaceStorage"
    if not base.exists():
        return []

    sessions = []

    for dbfile in base.rglob("state.vscdb"):
        try:
            conn = sqlite3.connect(dbfile)
            c = conn.cursor()

            rows = c.execute("SELECT key, value FROM ItemTable").fetchall()

            # Current closure target: focus on the interactive-session key path only.
            for key, value in rows:
                if not key:
                    continue

                lk = key.lower()
                if 'memento/interactive-session' not in lk:
                    continue
                raw_value = value
                decoded = try_decode(value)
                if decoded is None:
                    continue

                # Try key-specific formatter first; formatter returns full string or None to fallback
                formatted = format_payload_for_key(key, decoded, raw_value)
                if formatted is not None:
                    content = formatted
                else:
                    msgs = []
                    if isinstance(decoded, (dict, list)):
                        msgs = extract_messages(decoded)
                    elif isinstance(decoded, str):
                        try:
                            parsed = json.loads(decoded)
                            msgs = extract_messages(parsed)
                        except Exception:
                            msgs = [decoded]

                    if not msgs:
                        continue

                    content = "\n".join(msgs)

                sid = hid(str(dbfile) + key)

                sessions.append({
                    "id": sid,
                    "source": "vscode-live",
                    "path": f"{dbfile}::{key}",
                    "chat_session_id": infer_current_chat_session_id_from_state_db(dbfile),
                    "title": infer_title_from_state_db(dbfile),
                    "created_at": envelope_last_timestamp_iso(decoded) or path_mtime_iso(dbfile),
                    "content": content,
                    "display_content": content,
                })

        except:
            continue

    return sessions


def scan_copilot_chat_dirs():
    """Scan VS Code workspaceStorage for GitHub.copilot-chat session files.
    Returns list of session dicts {id, source, path, content}
    """
    base = Path(os.getenv("APPDATA", "")) / "Code" / "User" / "workspaceStorage"
    if not base.exists():
        return []

    sessions = []

    for ws in base.iterdir():
        chat_dir = ws / "GitHub.copilot-chat" / "chat-session-resources"
        if not chat_dir.exists():
            continue

        for session_dir in chat_dir.iterdir():
            if not session_dir.is_dir():
                continue

            for call_dir in session_dir.iterdir():
                if not call_dir.is_dir():
                    continue

                # content may be in content.txt or content.json (or similar)
                for f in call_dir.iterdir():
                    if not f.is_file():
                        continue
                    name = f.name.lower()
                    if 'content' not in name and f.suffix.lower() not in ('.txt', '.json'):
                        continue

                    try:
                        raw = f.read_text(errors='ignore')
                    except:
                        continue

                    parsed = None
                    try:
                        parsed = json.loads(raw)
                    except:
                        parsed = None

                    if is_self_generated_artifact(f, raw_text=raw, parsed_json=parsed):
                        continue

                    # Current closure target: only index file-backed payloads that normalize
                    # to the same interactive-session shape.
                    if parsed is None or parse_interactive_session(parsed) is None:
                        continue

                    # prefer file-specific formatter (returns full payload) or fallback to previous behavior
                    formatted = format_payload_for_key(f.name, parsed, raw)
                    if formatted is not None:
                        content = formatted
                    else:
                        msgs = []
                        if parsed:
                            msgs = extract_messages(parsed)
                            if not msgs:
                                try:
                                    msgs = [json.dumps(parsed, ensure_ascii=False)]
                                except:
                                    msgs = [str(parsed)]
                        else:
                            msgs = [raw]

                        content = "\n\n".join(m for m in msgs if m)

                    sid = hid(str(f))
                    sessions.append({
                        "id": sid,
                        "source": "copilot-artifact",
                        "path": str(f),
                        "chat_session_id": lookup_chat_session_id_for_chat_resource(f),
                        "title": lookup_title_for_chat_resource(f),
                        "created_at": envelope_last_timestamp_iso(parsed) or path_mtime_iso(f),
                        "content": content,
                        "display_content": content,
                    })

    return sessions


def scan_chat_sessions():
    base = Path(os.getenv('APPDATA', '')) / 'Code' / 'User' / 'workspaceStorage'
    if not base.exists():
        return []

    sessions = []
    for ws in base.iterdir():
        chat_dir = ws / 'chatSessions'
        state_db_path = ws / 'state.vscdb'
        if not chat_dir.exists():
            continue

        for jsonl_file in chat_dir.glob('*.jsonl'):
            session_id = jsonl_file.stem
            state = load_chat_session_state(jsonl_file)
            if not state:
                continue

            entry = lookup_chat_session_entry(session_id, state_db_path)
            title = state.get('customTitle') or entry.get('title')
            envelope = parse_chat_session_state(state, entry=entry)
            formatted = format_chat_session_transcript(state, title=title, entry=entry)
            created_at = envelope_last_timestamp_iso(state) or entry_timestamp_iso(entry) or path_mtime_iso(jsonl_file)
            search_parts = []
            if title:
                search_parts.append(title)
            if envelope and envelope.get('searchText'):
                search_parts.append(envelope['searchText'])

            sessions.append({
                'id': hid(str(jsonl_file)),
                'source': 'vscode-copilot',
                'path': str(jsonl_file),
                'chat_session_id': session_id,
                'title': title,
                'created_at': created_at,
                'content': '\n\n'.join(search_parts) or formatted,
                'display_content': formatted,
            })

    return sessions


# ----------------------------
# FALLBACK (markdown)
# ----------------------------
def scan_md(root):
    out = []
    for p in Path(root).rglob("*.md"):
        try:
            txt = p.read_text(errors="ignore")
            if len(txt.strip()) < 100:
                continue

            out.append({
                "id": hid(str(p)),
                "source": "markdown",
                "path": str(p),
                "content": txt[:20000],
                "display_content": txt[:20000]
            })
        except:
            pass
    return out


# ----------------------------
# COMMANDS
# ----------------------------
def cmd_scan(verbose=True):
    conn = db()
    c = conn.cursor()

    # Rebuild the cache from the current scan target surface.
    c.execute("DELETE FROM messages")
    c.execute("DELETE FROM sessions")

    sessions = []

    # scan various local sources: historical chat sessions, current-session data, and local markdown
    sessions += scan_chat_sessions()
    sessions += scan_vscode()
    sessions += scan_md(os.getcwd())

    inserted = 0
    seen = set()

    for s in sessions:
        sid = s.get("id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        try:
            c.execute("INSERT OR IGNORE INTO sessions(id,source,path,chat_session_id,title,created_at,display_content) VALUES (?,?,?,?,?,?,?)",
                      (sid, s.get("source"), s.get("path"), s.get("chat_session_id"), s.get("title"), s.get("created_at") or datetime.now(timezone.utc).isoformat(), s.get("display_content") or s.get("content") or ''))

            c.execute("INSERT INTO messages(session_id, content) VALUES (?,?)",
                      (sid, s.get("content")))

            inserted += 1
        except Exception:
            pass

    conn.commit()
    if verbose:
        print(f"[scan] {inserted} sessions indexed ({len(sessions)} found)")
    return inserted, len(sessions)


def cmd_search(q, limit=10, sources=None, json_out=False, exact=False, since=None, until=None,
               current_session_only=False, exclude_current_session=False, include_excluded=False,
               exclude_sessions=None):
    """Search sessions for query `q`.
    - limit: max results
    - sources: list of source strings to filter (or None)
    - json_out: if True, print JSON array with metadata+snippet
    - exact: if True, prefer phrase match in FTS
    """
    conn = db()
    c = conn.cursor()

    # Default to chat-history sources. This tool's main job is session recall,
    # and including markdown/workspace artifacts by default clogs results.
    if sources is None:
        sources = ['vscode-copilot']

    rows = []
    seen_session_ids = set()

    qlike = '%' + q.lower() + '%'
    try:
        params = [qlike]
        sql = """
        SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
        FROM sessions
        JOIN messages ON sessions.id = messages.session_id
        WHERE lower(coalesce(sessions.title, '')) LIKE ?
        """
        if sources:
            placeholders = ','.join('?' for _ in sources)
            sql += f" AND sessions.source IN ({placeholders})"
            params.extend(sources)
        sql += " ORDER BY sessions.created_at DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(sql, tuple(params)).fetchall()
        seen_session_ids.update(r[0] for r in rows)
    except Exception:
        rows = []

    # Try full-text MATCH first (fast, tokenized)
    try:
        match_q = ('"' + q.replace('"', '') + '"') if exact else q
        params = [match_q]
        sql = """
        SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
        FROM messages
        JOIN sessions ON sessions.id = messages.session_id
        WHERE messages MATCH ?
        """
        if sources:
            placeholders = ','.join('?' for _ in sources)
            sql += f" AND sessions.source IN ({placeholders})"
            params.extend(sources)
        sql += " LIMIT ?"
        params.append(limit)
        match_rows = c.execute(sql, tuple(params)).fetchall()
        for row in match_rows:
            if row[0] in seen_session_ids:
                continue
            rows.append(row)
            seen_session_ids.add(row[0])
            if len(rows) >= limit:
                break
    except Exception:
        pass

    # Fallback to a case-insensitive LIKE search on the content column
    if len(rows) < limit:
        try:
            params = [qlike]
            sql = """
            SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
            FROM messages
            JOIN sessions ON sessions.id = messages.session_id
            WHERE lower(messages.content) LIKE ?
            """
            if sources:
                placeholders = ','.join('?' for _ in sources)
                sql += f" AND sessions.source IN ({placeholders})"
                params.extend(sources)
            sql += " LIMIT ?"
            params.append(limit)
            like_rows = c.execute(sql, tuple(params)).fetchall()
            for row in like_rows:
                if row[0] in seen_session_ids:
                    continue
                rows.append(row)
                seen_session_ids.add(row[0])
                if len(rows) >= limit:
                    break
        except Exception:
            pass

    filtered_by_session = []
    for r in rows:
        chat_session_id = r[3]
        if should_include_chat_session(
            chat_session_id,
            current_session_only=current_session_only,
            exclude_current_session=exclude_current_session,
            include_excluded=include_excluded,
            extra_excluded_ids=exclude_sessions,
        ):
            filtered_by_session.append(r)
    rows = filtered_by_session

    # If the user requested time filtering, apply it to the candidate rows.
    if since or until:
        since_dt = parse_timestamp(since) if since else None
        until_dt = parse_timestamp(until) if until else None
        filtered = []
        for r in rows:
            content = r[6] or ''
            tss = extract_timestamps_from_text(content)
            accepted = False
            if tss:
                for ts in tss:
                    ok = True
                    if since_dt and ts < since_dt:
                        ok = False
                    if until_dt and ts > until_dt:
                        ok = False
                    if ok:
                        accepted = True
                        break
            else:
                # fallback to session created_at (r[3])
                try:
                    created_dt = parse_timestamp(r[5]) if r[5] else None
                    ok = True
                    if since_dt and created_dt and created_dt < since_dt:
                        ok = False
                    if until_dt and created_dt and created_dt > until_dt:
                        ok = False
                    if ok and created_dt:
                        accepted = True
                except Exception:
                    accepted = False

            if accepted:
                filtered.append(r)

        rows = filtered

    rows = rows[:limit]

    # Output
    if json_out:
        out = []
        for r in rows:
            out.append({
                "id": r[0],
                "source": r[1],
                "path": r[2],
                "chat_session_id": r[3],
                "title": r[4],
                "created_at": r[5],
                "content": r[6] or ""
            })
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    for r in rows:
        sid, src, path, chat_session_id, title, created_at, content = r[0], r[1], r[2], r[3], r[4], r[5], r[6] or ""
        print("# SESSION")
        print(f"id: {sid} | source: {src} | chat_session_id: {chat_session_id or '-'} | title: {title or '-'} | path: {path} | created_at: {created_at}")
        print("-" * 60)
        print(content)
        print("")


def sanitize_handoff_text(value):
    text = stringify_text(value)
    replacements = []
    for name in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        env_value = os.getenv(name)
        if env_value:
            replacements.append((env_value, f'%{name}%'))
            replacements.append((env_value.replace('\\', '/'), f'%{name}%'))
    username = os.getenv('USERNAME')
    if username:
        replacements.append((f'\\Users\\{username}\\', '\\Users\\<USER>\\'))
        replacements.append((f'/Users/{username}/', '/Users/<USER>/'))
    computer = os.getenv('COMPUTERNAME')
    if computer:
        replacements.append((computer, '<COMPUTER>'))

    for old, new in replacements:
        text = text.replace(old, new)
    return text


def get_handoff_candidate_rows(query=None, limit=8, sources=None):
    conn = db()
    c = conn.cursor()
    rows = []
    seen = set()

    def add_source_filter(sql, params):
        if sources:
            placeholders = ','.join('?' for _ in sources)
            sql += f" AND sessions.source IN ({placeholders})"
            params.extend(sources)
        return sql, params

    if query:
        qlike = '%' + query.lower() + '%'
        try:
            params = [qlike]
            sql = """
            SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
            FROM sessions
            JOIN messages ON sessions.id = messages.session_id
            WHERE lower(coalesce(sessions.title, '')) LIKE ?
            """
            sql, params = add_source_filter(sql, params)
            sql += " ORDER BY sessions.created_at DESC LIMIT ?"
            params.append(limit)
            for row in c.execute(sql, tuple(params)).fetchall():
                if row[0] not in seen:
                    rows.append(row)
                    seen.add(row[0])
        except Exception:
            pass

        try:
            params = [query]
            sql = """
            SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
            FROM messages
            JOIN sessions ON sessions.id = messages.session_id
            WHERE messages MATCH ?
            """
            sql, params = add_source_filter(sql, params)
            sql += " LIMIT ?"
            params.append(limit * 2)
            for row in c.execute(sql, tuple(params)).fetchall():
                if row[0] not in seen:
                    rows.append(row)
                    seen.add(row[0])
        except Exception:
            pass

        try:
            params = [qlike]
            sql = """
            SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
            FROM messages
            JOIN sessions ON sessions.id = messages.session_id
            WHERE lower(messages.content) LIKE ?
            """
            sql, params = add_source_filter(sql, params)
            sql += " ORDER BY sessions.created_at DESC LIMIT ?"
            params.append(limit * 2)
            for row in c.execute(sql, tuple(params)).fetchall():
                if row[0] not in seen:
                    rows.append(row)
                    seen.add(row[0])
        except Exception:
            pass
    else:
        try:
            params = []
            sql = """
            SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content)
            FROM sessions
            JOIN messages ON sessions.id = messages.session_id
            WHERE 1=1
            """
            sql, params = add_source_filter(sql, params)
            sql += " ORDER BY sessions.created_at DESC LIMIT ?"
            params.append(limit * 2)
            rows = c.execute(sql, tuple(params)).fetchall()
        except Exception:
            rows = []

    return rows


def score_handoff_row(row, query=None):
    sid, source, path, chat_session_id, title, created_at, content = row
    content = content or ''
    facts = extract_facts_from_text(content, query=query)
    query_l = (query or '').lower().strip()
    haystack = ' '.join([str(title or ''), str(path or ''), content]).lower()

    score = 0
    if query_l and query_l in haystack:
        score += 20
    if title and query_l and query_l in title.lower():
        score += 10
    if source in ('vscode-copilot', 'vscode-live', 'copilot-artifact'):
        score += 25
    elif source == 'markdown':
        score -= 8
    score += min(len(facts.get('files') or []), 6) * 3
    score += min(len(facts.get('commands') or []), 6) * 4
    score += min(len(facts.get('errors') or []), 6) * 6
    score += min(len(facts.get('nextSteps') or []), 6) * 4
    score += min(len(facts.get('highlights') or []), 6)

    parsed_created = parse_timestamp(created_at)
    if parsed_created:
        # Small deterministic recency bump; enough to break ties, not enough to
        # swamp exact query or operational facts.
        score += max(0, min(5, int(parsed_created.timestamp() // 86400) % 6))

    return score, facts


def score_handoff_value(value, query=None):
    text = stringify_text(value)
    score = 0
    query_l = (query or '').lower().strip()
    lower = text.lower()
    if query_l and query_l in lower:
        score += 10
    if PATH_RE.search(text):
        score += 4
    if COMMAND_LINE_RE.search(text):
        score += 5
    if ERROR_RE.search(text):
        score += 8
    if NEXT_RE.search(text) or DECISION_RE.search(text):
        score += 6
    return score


def select_scored_values(values, query=None, limit=8):
    scored = []
    for i, value in enumerate(values or []):
        scored.append((score_handoff_value(value, query=query), i, sanitize_handoff_text(value)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return unique_preserve_order([item[2] for item in scored if item[0] > 0][:limit])


def cmd_handoff(query=None, limit=5, sources=None, json_out=False):
    rows = get_handoff_candidate_rows(query=query, limit=limit, sources=sources)
    if not rows:
        # Handoff is intended as the first command an agent runs. Bootstrap an
        # empty index once so a fresh clone still returns useful local context.
        cmd_scan(verbose=False)
        rows = get_handoff_candidate_rows(query=query, limit=limit, sources=sources)
    fallback_used = False
    if not rows and query:
        rows = get_handoff_candidate_rows(query=None, limit=limit, sources=sources)
        fallback_used = bool(rows)
    scored_rows = []
    for row in rows:
        score, facts = score_handoff_row(row, query=query)
        scored_rows.append((score, row, facts))
    scored_rows.sort(key=lambda item: (-item[0], item[1][5] or ''))
    scored_rows = scored_rows[:limit]

    if not scored_rows:
        message = {
            'query': query or '',
            'message': 'No indexed sessions matched. Run `python csr.py scan`, try a broader query, or inspect the workspace normally.',
        }
        if json_out:
            print(json.dumps(message, ensure_ascii=False, indent=2))
        else:
            print('# Agent Handoff')
            print()
            print('## Query')
            print(query or '(recent/high-signal fallback)')
            print()
            print('No indexed sessions matched. Run `python csr.py scan`, try a broader query, or inspect the workspace normally.')
        return

    aggregate = {
        'files': [],
        'commands': [],
        'errors': [],
        'nextSteps': [],
        'highlights': [],
    }
    sessions = []
    for score, row, facts in scored_rows:
        sid, source, path, chat_session_id, title, created_at, content = row
        sessions.append({
            'id': sid,
            'score': score,
            'source': source,
            'title': sanitize_handoff_text(title or ''),
            'created_at': created_at,
            'path': sanitize_handoff_text(path or ''),
        })
        for key in aggregate:
            for value in facts.get(key) or []:
                add_unique_limited(aggregate[key], value, limit=40)

    files = select_scored_values(aggregate.get('files'), query=query, limit=12)
    commands = select_scored_values(aggregate.get('commands'), query=query, limit=10)
    errors = select_scored_values(aggregate.get('errors'), query=query, limit=8)
    next_steps = select_scored_values(aggregate.get('nextSteps'), query=query, limit=10)
    highlights = select_scored_values(aggregate.get('highlights'), query=query, limit=8)

    suggested = 'Inspect the likely files/session above, then continue from the decisions and errors listed here.'
    if fallback_used:
        suggested = 'No exact indexed match was found. Use these recent/high-signal sessions as orientation, then run a narrower handoff query if needed.'
    elif errors:
        suggested = 'Start by resolving or confirming the listed errors, then inspect the likely files/session above.'
    elif next_steps:
        suggested = 'Continue from the listed decisions / next steps and inspect the likely files/session above.'
    elif not query:
        suggested = 'Use these recent/high-signal sessions as pre-reasoning context, then run a narrower handoff query if needed.'

    payload = {
        'query': query or '',
        'fallback': 'recent-high-signal' if fallback_used else '',
        'sessions': sessions,
        'files': files,
        'commands': commands,
        'errors': errors,
        'nextSteps': next_steps,
        'highlights': highlights,
        'suggestedNextAction': suggested,
    }
    if json_out:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    def section(label, values):
        print()
        print(f'## {label}')
        if not values:
            print('- None found')
            return
        for value in values:
            print(f'- {value}')

    print('# Agent Handoff')
    print()
    print('## Query')
    print(query or '(recent/high-signal fallback)')
    if fallback_used:
        print()
        print('No exact indexed match was found; showing recent/high-signal sessions instead.')

    print()
    print('## Likely sessions')
    for session in sessions:
        label = session.get('title') or session.get('path') or session.get('id')
        bits = [f"score={session.get('score')}", f"source={session.get('source')}", f"id={session.get('id')}"]
        if session.get('created_at'):
            bits.append(f"created={session.get('created_at')}")
        print(f"- {label} ({'; '.join(bits)})")

    section('Files', files)
    section('Commands already run', commands)
    section('Errors / failures', errors)
    section('Decisions / next steps', next_steps)
    section('Other high-signal context', highlights)

    print()
    print('## Suggested next action')
    print(sanitize_handoff_text(suggested))


def cmd_list(limit=20, sources=None, json_out=False, current_session_only=False,
             exclude_current_session=False, include_excluded=False, exclude_sessions=None,
             bootstrap=True):
    """List sessions metadata."""
    conn = db()
    c = conn.cursor()

    def load_rows():
        params = []
        sql = "SELECT id, source, path, chat_session_id, title, created_at FROM sessions"
        if sources:
            placeholders = ','.join('?' for _ in sources)
            sql += f" WHERE source IN ({placeholders})"
            params.extend(sources)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        found = c.execute(sql, tuple(params)).fetchall()
        return [
            r for r in found
            if should_include_chat_session(
                r[3],
                current_session_only=current_session_only,
                exclude_current_session=exclude_current_session,
                include_excluded=include_excluded,
                extra_excluded_ids=exclude_sessions,
            )
        ]

    rows = load_rows()
    if not rows and bootstrap:
        # Agents commonly run `list` before `handoff`. Make that first contact
        # useful in a fresh workspace without requiring a separate scan step.
        cmd_scan(verbose=False)
        rows = load_rows()
    if json_out:
        out = [
            {
                "id": r[0],
                "source": r[1],
                "path": sanitize_handoff_text(r[2]),
                "chat_session_id": r[3],
                "title": sanitize_handoff_text(r[4]),
                "created_at": r[5],
            }
            for r in rows
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    for r in rows:
        print(r[0], r[1], sanitize_handoff_text(r[2]), r[3] or '-', sanitize_handoff_text(r[4]) or '-', r[5])


def cmd_show(sid, current_session_only=False, exclude_current_session=False,
             include_excluded=False, exclude_sessions=None):
    conn = db()
    c = conn.cursor()

    row = c.execute(
        "SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content) "
        "FROM sessions JOIN messages ON sessions.id = messages.session_id WHERE sessions.id=? ORDER BY messages.rowid DESC LIMIT 1",
        (sid,),
    ).fetchone()

    if not row:
        print("not found")
        return

    if not should_include_chat_session(
        row[3],
        current_session_only=current_session_only,
        exclude_current_session=exclude_current_session,
        include_excluded=include_excluded,
        extra_excluded_ids=exclude_sessions,
    ):
        print("excluded by session filter")
        return

    print("# SESSION")
    print(f"id: {row[0]} | source: {row[1]} | chat_session_id: {row[3] or '-'} | title: {row[4] or '-'} | path: {row[2]} | created_at: {row[5]}")
    print("-" * 60)
    print(row[6])


def cmd_export(current_session_only=False, exclude_current_session=False,
               include_excluded=False, exclude_sessions=None):
    conn = db()
    c = conn.cursor()

    rows = c.execute("""
    SELECT id, chat_session_id FROM sessions
    ORDER BY created_at DESC
    """).fetchall()

    row = None
    for candidate in rows:
        if should_include_chat_session(
            candidate[1],
            current_session_only=current_session_only,
            exclude_current_session=exclude_current_session,
            include_excluded=include_excluded,
            extra_excluded_ids=exclude_sessions,
        ):
            row = candidate
            break

    if not row:
        print("no sessions")
        return

    msg = c.execute(
        "SELECT coalesce(sessions.display_content, messages.content) FROM sessions JOIN messages ON sessions.id = messages.session_id WHERE sessions.id=? ORDER BY messages.rowid DESC LIMIT 1",
        (row[0],),
    ).fetchone()

    print("# SESSION HANDOFF\n")
    print(msg[0])


def cmd_health():
    base = Path(os.getenv("APPDATA", "")) / "Code" / "User" / "workspaceStorage"

    print("DB:", DB_PATH)
    print("VSCode storage exists:", base.exists())
    print("Workspace:", os.getcwd())


# ----------------------------
# CLI
# ----------------------------
def main():
    parser = argparse.ArgumentParser(prog='csr', description='Code Session Recall - lightweight session search')
    sub = parser.add_subparsers(dest='cmd')

    sub.add_parser('scan', help='scan workspace and index sessions')

    ps = sub.add_parser('search', help='search sessions')
    ps.add_argument('query', nargs='+', help='search query')
    ps.add_argument('-n', '--limit', type=int, default=10, help='max results')
    ps.add_argument('-s', '--source', type=str, help='comma-separated sources to filter')
    ps.add_argument('--json', action='store_true', dest='json_out', help='output JSON')
    ps.add_argument('--exact', action='store_true', help='exact phrase match')
    ps.add_argument('--since', help='ISO date/time or epoch seconds to filter (inclusive)')
    ps.add_argument('--until', help='ISO date/time or epoch seconds to filter (inclusive)')
    ps.add_argument('--current-session', action='store_true', help='only return results from the configured current workspace chat session')
    ps.add_argument('--exclude-current-session', action='store_true', help='exclude the configured current workspace chat session')
    ps.add_argument('--include-excluded-sessions', action='store_true', help='include sessions from the workspace exclusion block')
    ps.add_argument('--exclude-session', action='append', help='exclude a specific chat session id (repeatable)')

    pl = sub.add_parser('list', help='list sessions')
    pl.add_argument('-n', '--limit', type=int, default=20)
    pl.add_argument('-s', '--source', type=str, help='comma-separated sources to filter')
    pl.add_argument('--json', action='store_true', dest='json_out', help='output JSON')
    pl.add_argument('--current-session', action='store_true', help='only list results from the configured current workspace chat session')
    pl.add_argument('--exclude-current-session', action='store_true', help='exclude the configured current workspace chat session')
    pl.add_argument('--include-excluded-sessions', action='store_true', help='include sessions from the workspace exclusion block')
    pl.add_argument('--exclude-session', action='append', help='exclude a specific chat session id (repeatable)')

    for command_name, help_text in (
        ('handoff', 'emit compact agent handoff context'),
        ('ask', 'alias for handoff; answer with compact recalled context'),
    ):
        phandoff = sub.add_parser(command_name, help=help_text)
        phandoff.add_argument('query', nargs='*', help='optional handoff query; defaults to recent/high-signal sessions')
        phandoff.add_argument('-n', '--limit', type=int, default=5, help='max candidate sessions')
        phandoff.add_argument('-s', '--source', type=str, help='comma-separated sources to filter')
        phandoff.add_argument('--json', action='store_true', dest='json_out', help='output JSON')

    pshow = sub.add_parser('show', help='show session content')
    pshow.add_argument('id', help='session id')
    pshow.add_argument('--json', action='store_true', dest='json_out', help='output JSON')
    pshow.add_argument('--current-session', action='store_true', help='only allow showing the configured current workspace chat session')
    pshow.add_argument('--exclude-current-session', action='store_true', help='exclude the configured current workspace chat session')
    pshow.add_argument('--include-excluded-sessions', action='store_true', help='include sessions from the workspace exclusion block')
    pshow.add_argument('--exclude-session', action='append', help='exclude a specific chat session id (repeatable)')

    pexport = sub.add_parser('export', help='export latest session')
    pexport.add_argument('--current-session', action='store_true', help='only export from the configured current workspace chat session')
    pexport.add_argument('--exclude-current-session', action='store_true', help='exclude the configured current workspace chat session')
    pexport.add_argument('--include-excluded-sessions', action='store_true', help='include sessions from the workspace exclusion block')
    pexport.add_argument('--exclude-session', action='append', help='exclude a specific chat session id (repeatable)')
    sub.add_parser('health', help='show health info')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == 'scan':
        cmd_scan()

    elif args.cmd == 'search':
        q = ' '.join(args.query)
        sources = args.source.split(',') if args.source else None
        cmd_search(
            q,
            limit=args.limit,
            sources=sources,
            json_out=args.json_out,
            exact=args.exact,
            since=args.since,
            until=args.until,
            current_session_only=args.current_session,
            exclude_current_session=args.exclude_current_session,
            include_excluded=args.include_excluded_sessions,
            exclude_sessions=args.exclude_session,
        )

    elif args.cmd == 'list':
        sources = args.source.split(',') if args.source else None
        cmd_list(
            limit=args.limit,
            sources=sources,
            json_out=args.json_out,
            current_session_only=args.current_session,
            exclude_current_session=args.exclude_current_session,
            include_excluded=args.include_excluded_sessions,
            exclude_sessions=args.exclude_session,
        )

    elif args.cmd in ('handoff', 'ask'):
        q = ' '.join(args.query).strip() if args.query else None
        sources = args.source.split(',') if args.source else None
        cmd_handoff(
            query=q,
            limit=args.limit,
            sources=sources,
            json_out=args.json_out,
        )

    elif args.cmd == 'show':
        if args.json_out:
            conn = db(); c = conn.cursor()
            row = c.execute(
                'SELECT sessions.id, sessions.source, sessions.path, sessions.chat_session_id, sessions.title, sessions.created_at, coalesce(sessions.display_content, messages.content) '
                'FROM sessions JOIN messages ON sessions.id = messages.session_id WHERE sessions.id=? ORDER BY messages.rowid DESC LIMIT 1',
                (args.id,),
            ).fetchone()
            if not row:
                print(json.dumps({'error': 'not found'}))
            elif not should_include_chat_session(
                row[3],
                current_session_only=args.current_session,
                exclude_current_session=args.exclude_current_session,
                include_excluded=args.include_excluded_sessions,
                extra_excluded_ids=args.exclude_session,
            ):
                print(json.dumps({'error': 'excluded by session filter'}))
            else:
                print(json.dumps({
                    'id': row[0],
                    'source': row[1],
                    'path': row[2],
                    'chat_session_id': row[3],
                    'title': row[4],
                    'created_at': row[5],
                    'content': row[6],
                }, ensure_ascii=False))
        else:
            cmd_show(
                args.id,
                current_session_only=args.current_session,
                exclude_current_session=args.exclude_current_session,
                include_excluded=args.include_excluded_sessions,
                exclude_sessions=args.exclude_session,
            )

    elif args.cmd == 'export':
        cmd_export(
            current_session_only=args.current_session,
            exclude_current_session=args.exclude_current_session,
            include_excluded=args.include_excluded_sessions,
            exclude_sessions=args.exclude_session,
        )

    elif args.cmd == 'health':
        cmd_health()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
