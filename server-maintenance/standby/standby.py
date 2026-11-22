"""Smallc temporary reception: no jobs, tools, memory writes or chat models."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

STATE = Path('/home/ubuntu/qq-codex/bridge/.private/records/standby.sqlite3')


class State:
    def __init__(self, path=STATE):
        self.path = Path(path)

    def db(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        self.path.chmod(0o600)
        db.execute('CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT)')
        db.commit()
        return db

    def read(self):
        if not self.path.exists():
            return {}
        db = sqlite3.connect(self.path.absolute().as_uri() + '?mode=ro', uri=True, timeout=5)
        try:
            return {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM state')}
        finally:
            db.close()

    def put(self, **values):
        db = self.db()
        try:
            with db:
                db.executemany('INSERT OR REPLACE INTO state VALUES (?,?)',
                               [(k, json.dumps(v)) for k, v in values.items()])
        finally:
            db.close()

    def health(self, online, failures):
        if online:
            self.put(qq_out=False, qq_checked=time.time())
        elif failures >= 2:
            self.put(qq_out=True, qq_checked=time.time())

    def failed(self, category):
        if category in ('quota', 'auth', 'network', 'timeout', 'generation'):
            self.put(model_out=category, model_since=time.time(), probe_after=time.time()+300)

    def clear_model(self):
        self.put(model_out=None)

    def reserve_probe(self, now=None):
        now = time.time() if now is None else now
        db = self.db()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                data = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM state')}
                if data.get('qq_out') or not data.get('model_out') or now < data.get('probe_after', 0):
                    return False
                db.execute('INSERT OR REPLACE INTO state VALUES (?,?)', ('probe_after', json.dumps(now+300)))
                return True
        finally:
            db.close()


def mode(state):
    data = state.read()
    return None if data.get('qq_out') else 'model' if data.get('model_out') else None


def reception(text, actor, reason):
    if re.search(r'^/|生图|画|绘|gif|动图|新闻|监控|提醒|查|搜索|服务器|代码|设置|删除|记住|导出|点赞|任务|帮我做', text, re.I):
        return '这事先等小c回来再说吧。现在是大肥鱼值班，我只陪你聊两句，不开功能，也不留待办。'
    if re.search(r'回来|恢复|什么时候|去哪|在不在', text):
        return '小c这会儿还没确认恢复，我先替她守着。有什么正事等她回来再说吧，嘿嘿。'
    if re.search(r'困|累|难过|不开心|烦', text):
        return '那我先陪你待会儿。小c暂时不在，复杂的事等她回来再说。'
    if actor == 'smallc':
        return '小c暂时出去啦，现在是大肥鱼替她看着这个QQ，嘿嘿。有事等她回来再说吧。'
    return ('小c的QQ暂时掉线啦，我在自己这个号替她看着，嘿嘿。有什么事等她回来再说吧。'
            if reason == 'qq' else '小c这会儿回不了话，大肥鱼先值班。陪你聊两句可以，正事等她回来再说吧。')


def reply_if_active(text, actor, state=None):
    state = state or State()
    try:
        reason = mode(state)
    except Exception:
        return '值班状态暂时没核对上，我先不开功能。有什么事等小c回来再说吧。'
    return reception(text, actor, reason) if reason else None


def actor_for(bot, user):
    for actor, path in [('smallc', '/home/ubuntu/qq-codex/bridge/.private/config.json'),
                        ('harness', '/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json')]:
        config = json.loads(Path(path).read_text())
        if str(bot) == str(config['bot_qq']) and str(user) == str(config['owner_qq']):
            return actor
    return None


def image_blocked(bot, user):
    actor = actor_for(bot, user)
    return bool(actor and reply_if_active('生图', actor) is not None)


def image_failure_message(bot, user, category):
    if category in ('quota', 'auth', 'network', 'timeout') and actor_for(bot, user) == 'smallc':
        try:
            State().failed(category)
        except (OSError, sqlite3.OperationalError):
            # A read-only image worker can still report the generation failure.
            return None
        return reception('生图', 'smallc', 'model')
    return None


def launch_probe(state=None):
    state = state or State()
    if state.reserve_probe():
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--probe'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)


def probe(state=None):
    state = state or State()
    try:
        sys.path.insert(0, '/home/ubuntu/qq-codex/bridge')
        sys.path.insert(0, '/home/ubuntu/server-maintenance/usage')
        from usage_meter import run_metered
        with tempfile.TemporaryDirectory(prefix='smallc-recovery-') as tmp:
            output = Path(tmp) / 'ready.txt'
            command = ['/home/ubuntu/.local/bin/codex-proxy', 'exec', '--ignore-user-config',
                '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                '-c', 'web_search="disabled"', '-c', 'model_reasoning_effort="low"', '--json',
                '--output-last-message', str(output)]
            for feature in ('shell_tool', 'apps', 'remote_plugin', 'multi_agent', 'hooks', 'image_generation'):
                command += ['--disable', feature]
            command += ['-']
            result = run_metered(command, project='system_verification', input='这是恢复检查。只回复 READY，不调用任何工具。',
                cwd=tmp, text=True, capture_output=True, timeout=60)
            if result.returncode == 0 and output.is_file() and output.read_text().strip() == 'READY':
                state.clear_model()
                return True
    except Exception:
        pass
    return False


def sync_health(online, failures):
    state = State()
    state.health(online, failures)
    if online:
        launch_probe(state)


def group_reception(room, key, text, accounts, owner, group, state=None):
    state = state or State()
    reason = mode(state)
    if not reason:
        return False
    if room.control.get('paused') == '1' or not room.members_safe():
        return True
    label = 'harness' if reason == 'qq' else 'codex'
    call = room.control.reserve(key, label)
    if call is None:
        return True
    actor = 'harness' if label == 'harness' else 'smallc'
    reply = reception(text, actor, reason)
    event_key = key + '/standby'
    try:
        room.data.record(event_key, 'assistant', reply, status='generated', source='qq-standby',
            payload={'group_id':group,'speaker':'大肥鱼（临时值班）','sender':accounts[label]})
        room.send(label, reply)
        room.data.mark(event_key, 'sent')
        room.control.mark(call, 'sent')
    except Exception:
        room.data.mark(event_key, 'failed_or_uncertain')
        room.control.mark(call, 'failed_or_uncertain')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--actor', choices=('smallc', 'harness'), default='harness')
    args = parser.parse_args()
    if args.probe:
        probe()
        return
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('input_too_large')
        text = json.loads(raw).get('text', '')
        if not isinstance(text, str):
            raise ValueError('invalid_text')
        reply = reply_if_active(text, args.actor)
        print(json.dumps({'active': reply is not None, 'reply': reply}, ensure_ascii=False))
    except Exception:
        print(json.dumps({'active': True, 'reply': '现在先由大肥鱼值班，功能先不开，等小c回来再说吧。'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
