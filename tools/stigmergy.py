#!/usr/bin/env python3
"""Local continuity helper; made by jared castorena 1728studios llc.

No dependencies, network calls, authentication, scheduler or agent execution.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import uuid

KIT = Path(__file__).resolve().parent.parent
STATE = '.stigmergy'
MEMORY = 'stigmergicmemory.md'
MAIL = 'stigmergichat.md'
FOOTER = '<!-- stigmergy:previous-memory -->'
CREDIT = 'made by jared castorena 1728studios llc'
STATUSES = {'active', 'blocked', 'paused', 'completed'}
KINDS = {'assignment', 'blocker', 'interface', 'completion', 'decision'}
MESSAGE = re.compile(r'^<!-- stigmergy-message (\{[^\n]+\}) -->\n(.*?)\n<!-- /stigmergy-message -->\n', re.M | re.S)
INTERFACE_VERSION = 2
RECOVERY = {
    'E_USAGE': 'correct_arguments',
    'E_INVALID_INPUT': 'correct_input',
    'E_NOT_INITIALIZED': 'initialize_if_authorized',
    'E_ALREADY_INITIALIZED': 'resume_existing_state',
    'E_STALE_MEMORY': 'reread_and_reconcile',
    'E_STALE_GOAL': 'reread_and_reconcile',
    'E_LOCKED': 'inspect_lock_owner',
    'E_MISSING_CURSOR': 'locate_prior_record',
    'E_NOT_FOUND': 'check_id',
    'E_MAIL_INTEGRITY': 'stop_and_inspect',
    'E_GOAL_INTEGRITY': 'stop_and_inspect',
    'E_ARCHIVE_INTEGRITY': 'stop_and_inspect',
    'E_UNSAFE_PATH': 'stop_and_inspect',
    'E_IO': 'inspect_filesystem',
}


class ProtocolError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AgentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ProtocolError('E_USAGE', message)


def success(result):
    return {'ok': True, 'interface_version': INTERFACE_VERSION, **result}



def utc():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def bounded(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f'{name} must be nonempty single-line text of at most {limit} characters')
    return value


def managed(root, *parts):
    base = Path(root).expanduser().resolve() / STATE
    path = base
    for part in ('', *parts):
        path = path / part if part else path
        if path.is_symlink():
            raise ProtocolError('E_UNSAFE_PATH', f'managed path is a symlink: {path.name}')
    return path


def atomic_write(path, raw, mode=0o600):
    if path.is_symlink():
        raise ProtocolError('E_UNSAFE_PATH', 'refusing to replace a symlink')
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def writer(root):
    base = managed(root)
    if not base.is_dir():
        raise ProtocolError('E_NOT_INITIALIZED', 'workspace is not initialized; run init first')
    lock = managed(root, '.write.lock')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ProtocolError('E_LOCKED', 'writer lock exists; inspect its owner before manual recovery') from None
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(json_bytes({'pid': os.getpid(), 'host': socket.gethostname(), 'started_at': utc()}))
        yield
    finally:
        lock.unlink()


def freeze(path, raw):
    if path.is_symlink():
        raise ProtocolError('E_UNSAFE_PATH', 'archive path is a symlink')
    if path.exists():
        if path.read_bytes() != raw or path.stat().st_mode & 0o222:
            raise ProtocolError('E_ARCHIVE_INTEGRITY', 'existing archive differs or is writable')
    else:
        atomic_write(path, raw, 0o444)
    if path.read_bytes() != raw:
        raise ProtocolError('E_ARCHIVE_INTEGRITY', 'archive verification failed')


def init_workspace(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('project directory must already exist')
    base = managed(root)
    base.mkdir(mode=0o700, exist_ok=False)  # Exclusive creation; never overwrite user state.
    atomic_write(base / '.gitignore', b'*\n')
    (base / 'archives').mkdir(mode=0o700)
    with writer(root):
        for name in (MEMORY, MAIL, 'goals.json', 'decisions.md'):
            atomic_write(base / name, (KIT / 'templates' / name).read_bytes())
    return {'initialized': str(base), 'private_by_default': True, 'attribution': CREDIT}


def current_body(raw):
    text = raw.decode('utf-8')
    if '\x00' in text:
        raise ValueError('memory must not contain NUL characters')
    return re.split(r'^<!-- stigmergy:previous-memory -->\r?$', text, maxsplit=1, flags=re.M)[0].rstrip() + '\n'


def checkpoint(root, draft, expected):
    with writer(root):
        target = managed(root, MEMORY)
        old = target.read_bytes()
        old_hash = digest(old)
        if expected != old_hash:
            raise ProtocolError('E_STALE_MEMORY', 'stale memory hash; reread and reconcile before retrying')
        clean = current_body(draft)
        if not clean.strip():
            raise ValueError('memory draft must not be empty')
        if clean == current_body(old):
            return {'changed': False, 'memory_sha256': old_hash}
        lines = old.decode('utf-8').splitlines()
        headings = [(i + 1, re.sub(r'^#{1,6}\s+', '', line)) for i, line in enumerate(lines) if re.match(r'^#{1,6}\s+', line)]
        topics = [{'title': title, 'start_line': start, 'end_line': headings[i+1][0]-1 if i+1 < len(headings) else len(lines)} for i, (start, title) in enumerate(headings)]
        name = f'memory-{old_hash}.md'
        index_name = f'memory-{old_hash}.index.json'
        footer = f'\n{FOOTER}\n## Previous complete memory\nArchive: archives/{name}\nSHA-256: {old_hash}\nIndex: archives/{index_name}\n'
        # Bounded footer: exact topic ranges are in the immutable index.
        final = (clean + footer).encode('utf-8')
        line_count = len(final.decode('utf-8').splitlines())
        if len(final) > 12288 or line_count > 80:
            raise ValueError('final memory exceeds 12 KB / 80 lines; shorten the draft before retrying')
        archive_dir = managed(root, 'archives')
        freeze(archive_dir / name, old)
        freeze(archive_dir / index_name, json_bytes({'sha256': old_hash, 'bytes': len(old), 'lines': len(lines), 'topics': topics}))
        atomic_write(target, final)
        return {'changed': True, 'memory_sha256': digest(final), 'bytes': len(final), 'lines': line_count, 'target_exceeded': len(final) > 4096 or line_count > 60, 'archive': f'archives/{name}', 'index': f'archives/{index_name}'}


def read_goals(root):
    try:
        return _read_goals(root)
    except ProtocolError:
        raise
    except (ValueError, KeyError, TypeError) as error:
        raise ProtocolError('E_GOAL_INTEGRITY', str(error)) from None


def _read_goals(root):
    value = json.loads(managed(root, 'goals.json').read_text())
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1 or type(value.get('revision')) is not int or value['revision'] < 0 or not isinstance(value.get('goals'), list):
        raise ValueError('invalid goal state envelope')
    ids = set()
    for goal in value['goals']:
        if not isinstance(goal, dict) or not isinstance(goal.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', goal['id']) or goal['id'] in ids:
            raise ValueError('invalid or duplicate goal ID')
        ids.add(goal['id'])
        for field in ('objective', 'next_action', 'updated_at'):
            bounded(goal.get(field), field, 1000)
        bounded(goal.get('owner'), 'owner')
        if goal.get('reason') is not None:
            bounded(goal['reason'], 'reason', 1000)
        if goal.get('status') not in STATUSES or type(goal.get('acceptance_reviewed')) is not bool:
            raise ValueError('invalid goal status or review flag')
        for field in ('acceptance', 'evidence'):
            values = goal.get(field)
            if not isinstance(values, list) or field == 'acceptance' and not values:
                raise ValueError(f'invalid goal {field}')
            for item in values:
                bounded(item, field, 1000)
        if goal['status'] in {'blocked', 'paused'}:
            bounded(goal.get('reason'), 'reason', 1000)
        if goal['status'] == 'completed' and (not goal['evidence'] or not goal['acceptance_reviewed']):
            raise ValueError('completed goal requires reviewed acceptance and evidence')
    return value



def list_goals(root, after=None, limit=10):
    if not 1 <= limit <= 20:
        raise ValueError('goal list limit must be 1..20')
    state = read_goals(root)
    start = 0
    if after is not None:
        found = next((i for i, goal in enumerate(state['goals']) if goal['id'] == after), None)
        if found is None:
            raise ProtocolError('E_MISSING_CURSOR', 'goal cursor ID is missing')
        start = found + 1
    page = state['goals'][start:start+limit]
    return {'revision': state['revision'], 'goals': [{key: goal[key] for key in ('id', 'owner', 'status')} for goal in page], 'next_after': page[-1]['id'] if page else after, 'more': start+len(page) < len(state['goals'])}


def exact_goal(root, ident):
    state = read_goals(root)
    found = next((g for g in state['goals'] if g['id'] == ident), None)
    if found is None:
        raise ProtocolError('E_NOT_FOUND', 'goal ID not found')
    return {'revision': state['revision'], 'goal': found}


def change_goal(root, expected, goal_id, *, objective=None, owner=None, acceptance=None, next_action=None, status=None, evidence=(), reviewed=False, reason=None):
    with writer(root):
        path = managed(root, 'goals.json')
        old = path.read_bytes()
        state = read_goals(root)
        if state['revision'] != expected:
            raise ProtocolError('E_STALE_GOAL', 'stale goal revision; reread and reconcile before retrying')
        found = next((g for g in state['goals'] if g['id'] == goal_id), None)
        if objective is not None:
            if found is not None or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', goal_id):
                raise ValueError('goal ID is invalid or already exists')
            if not acceptance:
                raise ValueError('at least one acceptance criterion is required')
            found = {'id': goal_id, 'objective': bounded(objective, 'objective', 1000), 'owner': bounded(owner, 'owner'), 'acceptance': [bounded(x, 'acceptance', 1000) for x in acceptance], 'next_action': bounded(next_action, 'next action', 1000), 'status': 'active', 'evidence': [], 'acceptance_reviewed': False, 'reason': None}
            state['goals'].append(found)
        elif found is None:
            raise ProtocolError('E_NOT_FOUND', 'unknown goal ID')
        elif all(x is None for x in (owner, next_action, status, reason)) and not evidence and not reviewed:
            raise ValueError('no goal update supplied')
        if owner is not None:
            found['owner'] = bounded(owner, 'owner')
        if next_action is not None:
            found['next_action'] = bounded(next_action, 'next action', 1000)
        if status is not None:
            if status not in STATUSES:
                raise ValueError('unknown goal status')
            found['status'] = status
        found['evidence'] = list(dict.fromkeys([*found['evidence'], *[bounded(x, 'evidence', 1000) for x in evidence]]))
        if found['status'] in {'blocked', 'paused'}:
            found['reason'] = bounded(reason, 'reason', 1000)
        else:
            found['reason'] = None
        found['acceptance_reviewed'] = bool(reviewed) if found['status'] == 'completed' else False
        if found['status'] == 'completed':
            if not reviewed or not found['evidence']:
                raise ValueError('completion requires evidence and --reviewed acceptance')
            if next_action is None:
                found['next_action'] = 'None; acceptance reviewed.'
        found['updated_at'] = utc()
        state['revision'] += 1
        freeze(managed(root, 'archives', f'goals-{digest(old)}.json'), old)
        atomic_write(path, json_bytes(state))
        return {'revision': state['revision'], 'goal': found}


def read_mail(root):
    try:
        return _read_mail(root)
    except ProtocolError:
        raise
    except (ValueError, KeyError, TypeError) as error:
        raise ProtocolError('E_MAIL_INTEGRITY', str(error)) from None


def _read_mail(root):
    text = managed(root, MAIL).read_bytes().decode('utf-8')
    matches = list(MESSAGE.finditer(text))
    if text.count('<!-- stigmergy-message ') != len(matches) or text.count('<!-- /stigmergy-message -->') != len(matches):
        raise ValueError('malformed mail delimiters; no bodies returned')
    messages, ids = [], set()
    for match in matches:
        meta, body = json.loads(match[1]), match[2]
        if not isinstance(meta, dict) or type(meta.get('schema_version')) is not int or meta['schema_version'] != 1:
            raise ValueError('invalid message schema')
        ident = meta.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'msg-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{12}', ident) or ident in ids:
            raise ValueError('invalid or duplicate message ID')
        for field in ('author', 'to', 'title', 'next_owner', 'utc'):
            bounded(meta.get(field), field)
        if meta.get('kind') not in KINDS or meta.get('reply_to') is not None and meta['reply_to'] not in ids:
            raise ValueError('invalid message kind or reply chain')
        if not isinstance(meta.get('evidence'), list):
            raise ValueError('invalid message evidence')
        for ref in meta['evidence']:
            bounded(ref, 'evidence', 1000)
        if meta.get('body_sha256') != digest(body.encode('utf-8')) or len(body.encode('utf-8')) > 4000:
            raise ValueError('message content checksum or size failed; no bodies returned')
        ids.add(ident)
        messages.append({'metadata': meta, 'body': body})
    return messages


def post_mail(root, *, author, to, kind, title, body, next_owner, reply_to=None, evidence=()):
    for name, value in [('author', author), ('to', to), ('title', title), ('next owner', next_owner)]:
        bounded(value, name)
    body = body.rstrip('\n')
    if kind not in KINDS or not body.strip() or len(body.encode('utf-8')) > 4000 or '\x00' in body or 'stigmergy-message' in body:
        raise ValueError('invalid mail kind/body; use <=4000 UTF-8 bytes without reserved delimiters')
    with writer(root):
        path = managed(root, MAIL)
        old = path.read_bytes()
        messages = read_mail(root)
        if reply_to is not None and reply_to not in {m['metadata']['id'] for m in messages}:
            raise ValueError('reply-to ID does not exist in the current board')
        ident = 'msg-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:12]
        meta = {'schema_version': 1, 'id': ident, 'utc': utc(), 'author': author, 'to': to, 'kind': kind, 'title': title, 'reply_to': reply_to, 'next_owner': next_owner, 'evidence': [bounded(x, 'evidence', 1000) for x in evidence], 'body_sha256': digest(body.encode('utf-8'))}
        entry = '\n<!-- stigmergy-message ' + json.dumps(meta, ensure_ascii=False) + ' -->\n' + body + '\n<!-- /stigmergy-message -->\n'
        atomic_write(path, old + entry.encode('utf-8'))
        return {'id': ident, 'authentication': 'unverified', 'native_delivery_required': True}


def list_mail(root, after=None, limit=5, latest=False):
    if not 1 <= limit <= 20 or latest and after is not None:
        raise ValueError('limit must be 1..20; latest and after are mutually exclusive')
    messages = read_mail(root)
    start = max(0, len(messages)-limit) if latest else 0
    if after is not None:
        found = next((i for i, m in enumerate(messages) if m['metadata']['id'] == after), None)
        if found is None:
            raise ProtocolError('E_MISSING_CURSOR', 'cursor ID is missing; locate its archived board before resetting')
        start = found + 1
    page = messages[start:start+limit]
    return {'messages': [m['metadata'] for m in page], 'next_after': page[-1]['metadata']['id'] if page else after, 'more': start+len(page) < len(messages), 'authentication': 'unverified'}


def exact_mail(root, ident, offset=0, max_chars=2000):
    if offset < 0 or not 1 <= max_chars <= 8000:
        raise ValueError('offset must be nonnegative and max-chars must be 1..8000')
    found = next((m for m in read_mail(root) if m['metadata']['id'] == ident), None)
    if found is None:
        raise ProtocolError('E_NOT_FOUND', 'message ID not found')
    if offset > len(found['body']):
        raise ValueError('offset is beyond this message')
    chunk = found['body'][offset:offset+max_chars]
    return {'metadata': found['metadata'], 'body': chunk, 'next_offset': offset+len(chunk), 'complete': offset+len(chunk) == len(found['body']), 'authentication': 'unverified'}


def workspace_status(root):
    raw = managed(root, MEMORY).read_bytes()
    state, messages = read_goals(root), read_mail(root)
    return {'memory_sha256': digest(raw), 'memory_bytes': len(raw), 'memory_lines': len(raw.decode('utf-8').splitlines()), 'goal_revision': state['revision'], 'goals_by_status': {s: sum(g['status'] == s for g in state['goals']) for s in sorted(STATUSES)}, 'last_message_id': messages[-1]['metadata']['id'] if messages else None}


def resume(root, *, memory_offset=0, expected_memory=None, goal_after=None, mail_after=None, limit=3, max_bytes=6000):
    if not 2048 <= max_bytes <= 12288 or not 1 <= limit <= 20 or memory_offset < 0:
        raise ValueError('resume needs max-bytes 2048..12288, limit 1..20 and nonnegative memory-offset')
    raw = managed(root, MEMORY).read_bytes()
    sha = digest(raw)
    if expected_memory is not None and expected_memory != sha:
        raise ProtocolError('E_STALE_MEMORY', 'memory changed; restart resume at offset zero')
    if memory_offset and expected_memory is None:
        raise ValueError('memory continuation requires --expect-memory-sha256')
    body = raw.decode('utf-8')
    if memory_offset > len(body):
        raise ValueError('memory-offset is beyond the current memory')
    goals = list_goals(root, goal_after, limit)
    mail = list_mail(root, mail_after, limit)
    mail['messages'] = [{k: m[k] for k in ('id', 'to', 'kind')} for m in mail['messages']]
    chunk = body[memory_offset:memory_offset+2000]
    result = {
        'snapshot': 'sequential_reads',
        'memory': {'sha256': sha, 'offset': memory_offset, 'body': chunk,
                   'next_offset': memory_offset+len(chunk), 'complete': memory_offset+len(chunk) == len(body)},
        'goals': goals, 'mail': mail,
    }
    def size():
        return len(json_bytes(success(result)))
    # Retain stable cursors when a page is shortened to fit the serialized budget.
    for page, key, before, id_key in [(mail, 'messages', mail_after, 'id'), (goals, 'goals', goal_after, 'id')]:
        while size() > max_bytes and page[key]:
            page[key].pop()
            page['more'] = True
            page['next_after'] = page[key][-1][id_key] if page[key] else before
    if size() > max_bytes:
        low, high = 0, len(chunk)
        while low < high:
            mid = (low+high+1)//2
            result['memory'].update(body=chunk[:mid], next_offset=memory_offset+mid, complete=memory_offset+mid == len(body))
            if size() <= max_bytes:
                low = mid
            else:
                high = mid-1
        result['memory'].update(body=chunk[:low], next_offset=memory_offset+low, complete=memory_offset+low == len(body))
    return result


def command_contract(operation=None):
    contract = json.loads((KIT / 'agent-contract.json').read_text())
    if operation is None:
        return {'kit_version': contract['kit_version'], 'commands': list(contract['commands']),
                'recovery': contract['recovery']}
    command = contract['commands'].get(operation)
    if command is None:
        raise ProtocolError('E_NOT_FOUND', 'contract operation not found')
    argv = contract['invocation']['prefix'] + command['argv']
    names = {name for arg in argv for name in re.findall(r'\{([A-Z0-9_]+)\}', arg)}
    return {'kit_version': contract['kit_version'], 'operation': operation,
            'invocation': contract['invocation'], 'command': command,
            'bindings': {key: value for key, value in contract['bindings'].items() if key in names},
            'responses': contract['responses']}


def parser():
    p = AgentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path.cwd(), help='existing project root (default: current directory)')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init'); sub.add_parser('status')
    lookup = sub.add_parser('contract'); lookup.add_argument('--operation')
    r = sub.add_parser('resume')
    r.add_argument('--memory-offset', type=int, default=0); r.add_argument('--expect-memory-sha256')
    r.add_argument('--goal-after'); r.add_argument('--mail-after'); r.add_argument('--limit', type=int, default=3)
    r.add_argument('--max-bytes', type=int, default=6000)
    c = sub.add_parser('checkpoint'); c.add_argument('--draft', type=Path, required=True); c.add_argument('--expect-sha256', required=True)
    goal = sub.add_parser('goal').add_subparsers(dest='operation', required=True)
    listing = goal.add_parser('list'); listing.add_argument('--after'); listing.add_argument('--limit', type=int, default=10)
    read = goal.add_parser('read'); read.add_argument('id')
    a = goal.add_parser('add')
    for name in ('id', 'owner', 'objective', 'next-action'):
        a.add_argument('--'+name, required=True)
    a.add_argument('--accept', action='append', required=True); a.add_argument('--expect-revision', type=int, required=True)
    u = goal.add_parser('update'); u.add_argument('id'); u.add_argument('--status', choices=sorted(STATUSES)); u.add_argument('--owner'); u.add_argument('--next-action'); u.add_argument('--reason'); u.add_argument('--reviewed', action='store_true'); u.add_argument('--evidence', action='append', default=[]); u.add_argument('--expect-revision', type=int, required=True)
    mail = sub.add_parser('mail').add_subparsers(dest='operation', required=True)
    post = mail.add_parser('post')
    for name in ('author', 'to', 'title', 'next-owner'):
        post.add_argument('--'+name, required=True)
    post.add_argument('--kind', choices=sorted(KINDS), required=True); post.add_argument('--body-file', type=Path, required=True); post.add_argument('--reply-to'); post.add_argument('--evidence', action='append', default=[])
    listing = mail.add_parser('list'); listing.add_argument('--after'); listing.add_argument('--latest', action='store_true'); listing.add_argument('--limit', type=int, default=5)
    read = mail.add_parser('read'); read.add_argument('id'); read.add_argument('--offset', type=int, default=0); read.add_argument('--max-chars', type=int, default=2000)
    return p


def main(argv=None):
    a = None
    try:
        a = parser().parse_args(argv)
        if a.command not in {'init', 'contract'} and not managed(a.root).is_dir():
            raise ProtocolError('E_NOT_INITIALIZED', 'workspace is not initialized; run init first')
        if a.command == 'contract': result = command_contract(a.operation)
        elif a.command == 'init': result = init_workspace(a.root)
        elif a.command == 'status': result = workspace_status(a.root)
        elif a.command == 'resume': result = resume(a.root, memory_offset=a.memory_offset, expected_memory=a.expect_memory_sha256, goal_after=a.goal_after, mail_after=a.mail_after, limit=a.limit, max_bytes=a.max_bytes)
        elif a.command == 'checkpoint': result = checkpoint(a.root, a.draft.read_bytes(), a.expect_sha256)
        elif a.command == 'goal':
            if a.operation == 'list': result = list_goals(a.root, a.after, a.limit)
            elif a.operation == 'read': result = exact_goal(a.root, a.id)
            elif a.operation == 'add': result = change_goal(a.root, a.expect_revision, a.id, objective=a.objective, owner=a.owner, acceptance=a.accept, next_action=a.next_action)
            else: result = change_goal(a.root, a.expect_revision, a.id, owner=a.owner, status=a.status, next_action=a.next_action, reason=a.reason, evidence=a.evidence, reviewed=a.reviewed)
        elif a.operation == 'post': result = post_mail(a.root, author=a.author, to=a.to, kind=a.kind, title=a.title, body=a.body_file.read_text(), next_owner=a.next_owner, reply_to=a.reply_to, evidence=a.evidence)
        elif a.operation == 'list': result = list_mail(a.root, a.after, a.limit, a.latest)
        else: result = exact_mail(a.root, a.id, a.offset, a.max_chars)
        print(json.dumps(success(result), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, ProtocolError):
            code = error.code
        elif isinstance(error, FileExistsError) and a is not None and a.command == 'init':
            code = 'E_ALREADY_INITIALIZED'
        elif isinstance(error, OSError):
            code = 'E_IO'
        else:
            code = 'E_INVALID_INPUT'
        print(json.dumps({'ok': False, 'interface_version': INTERFACE_VERSION,
                          'error': {'code': code, 'message': str(error), 'recovery': RECOVERY[code]}}, ensure_ascii=False), file=sys.stderr)
        return 2 if code == 'E_USAGE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
