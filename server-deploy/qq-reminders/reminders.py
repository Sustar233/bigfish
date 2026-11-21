"""Durable owner-only QQ message reminders. Never runs message text as code."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import sqlite3
import struct
import threading
import time
import urllib.request
import uuid
from zoneinfo import ZoneInfo

try:
    TZ = ZoneInfo('Asia/Shanghai')
except KeyError:
    TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
ROOT = Path('/home/ubuntu/qq-reminders')
SOCKET = '/run/qq-reminders/control.sock'
OWNER = '1000000001'
CONFIGS = {
    'smallc': ('/home/ubuntu/qq-codex/bridge/.private/config.json', '1000000002', 'http://127.0.0.1:13001'),
    'harness': ('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json', '1000000003', 'http://127.0.0.1:13101'),
}


def authorize(r):
    if str(r.get('owner')) != OWNER or r.get('channel') != 'private':
        raise PermissionError('仅本人私聊可设置提醒')
    origin, bot = r.get('origin', ''), r.get('bot')
    valid = (bot == 'smallc' and origin == 'smallc-private-' + OWNER or
             bot == 'harness' and re.fullmatch('onebot-private-' + OWNER + r'(?:-[A-Za-z0-9_-]+)?', origin))
    if not valid:
        raise PermissionError('提醒来源不匹配')
    return bot


def normalize(r, now):
    repeat = r.get('repeat', 'none')
    if repeat not in ('none', 'daily', 'weekdays', 'weekly', 'interval'):
        raise ValueError('不支持的重复类型')
    message = r.get('message', '').strip()
    if not 1 <= len(message) <= 2000:
        raise ValueError('提醒内容应为1–2000字')
    spec = {'repeat': repeat}
    if repeat == 'none':
        if r.get('delay_seconds') is not None:
            delay = float(r['delay_seconds'])
            if not 1 <= delay <= 31622400:
                raise ValueError('相对时间应为1秒至1年')
            due = now + delay
        else:
            at = datetime.fromisoformat(str(r.get('fire_at', '')).replace('Z', '+00:00'))
            if at.tzinfo is None:
                at = at.replace(tzinfo=TZ)
            due = at.timestamp()
        if due <= now:
            raise ValueError('指定时间已经过去，请提供未来时间')
    elif repeat == 'interval':
        minutes = float(r.get('interval_minutes', 0))
        if not 1 <= minutes <= 525600:
            raise ValueError('重复间隔应为1分钟至1年')
        spec['seconds'] = minutes * 60
        due = now + spec['seconds']
    else:
        match = re.fullmatch(r'(\d{1,2}):(\d{2})', str(r.get('at', '')))
        if not match or int(match[1]) > 23 or int(match[2]) > 59:
            raise ValueError('请提供明确的北京时间，如08:00')
        spec.update(hour=int(match[1]), minute=int(match[2]))
        if repeat == 'weekdays':
            spec['weekdays'] = [0, 1, 2, 3, 4]
        elif repeat == 'weekly':
            days = [int(x) for x in str(r.get('weekdays', '')).split(',')]
            if not days or any(d not in range(7) for d in days):
                raise ValueError('星期应为0–6，0代表周一')
            spec['weekdays'] = sorted(set(days))
        due = next_time(spec, now)
    return message, spec, due


def next_time(spec, after):
    if spec['repeat'] == 'none':
        return None
    if spec['repeat'] == 'interval':
        return after + spec['seconds']
    local = datetime.fromtimestamp(after, TZ)
    for offset in range(8):
        candidate = (local + timedelta(days=offset)).replace(hour=spec['hour'], minute=spec['minute'], second=0, microsecond=0)
        if candidate.timestamp() > after and ('weekdays' not in spec or candidate.weekday() in spec['weekdays']):
            return candidate.timestamp()
    raise ValueError('找不到下次提醒时间')


class Store:
    def __init__(self, database):
        self.database = str(database)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY,bot TEXT,request_key TEXT,message TEXT,
                spec TEXT,next_fire REAL,state TEXT,created REAL,updated REAL,last_error TEXT,retry_after REAL DEFAULT 0);
            CREATE UNIQUE INDEX IF NOT EXISTS request_once ON reminders(bot,request_key);
            CREATE TABLE IF NOT EXISTS deliveries(reminder_id TEXT,due REAL,state TEXT,message_id TEXT,error TEXT,
                PRIMARY KEY(reminder_id,due));''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def view(row):
        d = dict(row)
        d['spec'] = json.loads(d['spec'])
        d['next_fire_beijing'] = datetime.fromtimestamp(d['next_fire'], TZ).isoformat()
        return d

    def dispatch(self, r, now=None):
        now = time.time() if now is None else now
        bot = authorize(r)
        action = r.get('action')
        if action == 'time':
            return {'now_beijing':datetime.fromtimestamp(now,TZ).isoformat()}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if action == 'list':
                return [self.view(x) for x in db.execute("SELECT * FROM reminders WHERE bot=? AND state NOT IN ('cancelled','done','expired') ORDER BY created DESC LIMIT 100", (bot,))]
            if action == 'create':
                key = str(r.get('request_key', ''))
                if not 1 <= len(key) <= 160:
                    raise ValueError('缺少稳定的请求编号')
                old = db.execute('SELECT * FROM reminders WHERE bot=? AND request_key=?', (bot, key)).fetchone()
                if old:
                    return self.view(old)
                if db.execute("SELECT count(*) FROM reminders WHERE bot=? AND state IN ('active','sending')", (bot,)).fetchone()[0] >= 100:
                    raise ValueError('提醒已达100条，请先整理')
                message, spec, due = normalize(r, now)
                identifier = uuid.uuid4().hex[:12]
                db.execute('INSERT INTO reminders VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (identifier, bot, key, message, json.dumps(spec), due, 'active', now, now, '', 0))
            elif action in ('cancel', 'update'):
                identifier = r.get('reminder_id')
                if identifier == 'latest':
                    row = db.execute("SELECT id FROM reminders WHERE bot=? AND state IN ('active','sending','needs_review') ORDER BY created DESC LIMIT 1", (bot,)).fetchone()
                    identifier = row['id'] if row else ''
                old = db.execute('SELECT * FROM reminders WHERE id=? AND bot=?', (identifier, bot)).fetchone()
                if not old:
                    raise ValueError('没找到本账号的这条提醒')
                if action == 'cancel':
                    db.execute("UPDATE reminders SET state='cancelled',updated=? WHERE id=?", (now, identifier))
                else:
                    if old['state'] == 'sending':
                        raise ValueError('正在发送，暂不能修改；可先取消后新建')
                    message, spec, due = normalize(r, now)
                    db.execute("UPDATE reminders SET message=?,spec=?,next_fire=?,state='active',updated=?,last_error='',retry_after=0 WHERE id=?",
                               (message, json.dumps(spec), due, now, identifier))
            else:
                raise ValueError('不支持的提醒操作')
            return self.view(db.execute('SELECT * FROM reminders WHERE id=?', (identifier,)).fetchone())

    def recover(self, now):
        with self.db() as db:
            for row in db.execute("SELECT * FROM reminders WHERE state='sending'").fetchall():
                future = next_time(json.loads(row['spec']), now)
                db.execute("UPDATE deliveries SET state='unknown',error='service_restart' WHERE reminder_id=? AND state='attempted'", (row['id'],))
                db.execute('UPDATE reminders SET state=?,next_fire=?,last_error=? WHERE id=?',
                           ('active' if future else 'needs_review', future or row['next_fire'], '上次发送结果不确定，未自动重发', row['id']))

    def tick(self, transport, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            rows = db.execute("SELECT * FROM reminders WHERE state='active' AND next_fire<=? AND retry_after<=? ORDER BY next_fire LIMIT 20", (now, now)).fetchall()
        for row in rows:
            spec, due = json.loads(row['spec']), row['next_fire']
            if now - due > 86400:
                future = next_time(spec, now)
                with self.db() as db:
                    db.execute("UPDATE reminders SET next_fire=?,state=?,last_error='过期未补发' WHERE id=? AND state='active' AND next_fire=?",
                               (future or due, 'active' if future else 'expired', row['id'], due))
                continue
            try:
                online = transport.online(row['bot'])
            except Exception:
                online = False
            if not online:
                with self.db() as db:
                    db.execute("UPDATE reminders SET retry_after=?,last_error='QQ暂不可用，等待恢复' WHERE id=? AND state='active'", (now+60, row['id']))
                continue
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                changed = db.execute("UPDATE reminders SET state='sending',updated=? WHERE id=? AND state='active' AND next_fire=?", (now, row['id'], due)).rowcount
                if not changed:
                    continue
                db.execute("INSERT INTO deliveries VALUES(?,?,'attempted',NULL,NULL)", (row['id'], due))
            try:
                message = row['message']
                if now-due > 300:
                    message += '\n（原定北京时间' + datetime.fromtimestamp(due, TZ).strftime('%m-%d %H:%M') + '）'
                message_id = transport.send(row['bot'], message)
                state, error = 'sent', ''
            except Exception as exc:
                message_id, state, error = None, 'unknown', type(exc).__name__
            future = next_time(spec, max(now, time.time()) if now is None else now)
            with self.db() as db:
                db.execute('UPDATE deliveries SET state=?,message_id=?,error=? WHERE reminder_id=? AND due=?', (state, str(message_id) if message_id else None, error, row['id'], due))
                db.execute("UPDATE reminders SET state=?,next_fire=?,updated=?,last_error=?,retry_after=0 WHERE id=? AND state='sending'",
                           ('active' if future else 'done' if state=='sent' else 'needs_review', future or due, now, error, row['id']))


class OneBot:
    def request(self, bot, action, data):
        path, expected, url = CONFIGS[bot]
        config = json.loads(Path(path).read_text())
        if str(config.get('owner_qq')) != OWNER or str(config.get('bot_qq')) != expected or config.get('onebot_url') != url:
            raise PermissionError('账号配置不匹配')
        request = urllib.request.Request(url+'/'+action, data=json.dumps(data).encode(),
                                        headers={'Authorization':'Bearer '+config['onebot_token'],'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=12) as response:
            result = json.load(response)
        if result.get('status') != 'ok' or result.get('retcode') != 0:
            raise RuntimeError('OneBot rejected')
        return result.get('data', {})

    def online(self, bot):
        return self.request(bot, 'get_status', {}).get('online') is True

    def send(self, bot, message):
        result = self.request(bot, 'send_private_msg', {'user_id':int(OWNER), 'message':[{'type':'text','data':{'text':message}}], 'auto_escape':True})
        if not result.get('message_id'):
            raise RuntimeError('Missing send receipt')
        return result['message_id']


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            self.connection.settimeout(10)
            _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise PermissionError('无效本机调用者')
            data = self.rfile.readline(16385)
            if len(data)>16384 or not data.endswith(b'\n'):
                raise ValueError('请求过大或不完整')
            response = {'ok':True,'result':self.server.store.dispatch(json.loads(data))}
        except Exception as error:
            response = {'ok':False,'error':str(error)[:200]}
        self.wfile.write((json.dumps(response,ensure_ascii=False)+'\n').encode())


def main():
    os.umask(0o077)
    (ROOT/'data').mkdir(exist_ok=True,mode=0o700)
    store = Store(ROOT/'data/reminders.sqlite3')
    store.recover(time.time())
    transport = OneBot()
    def worker():
        while True:
            try:
                store.tick(transport)
            except Exception as error:
                print('reminder_tick_failed '+type(error).__name__,flush=True)
            time.sleep(3)
    threading.Thread(target=worker,daemon=True).start()
    Path(SOCKET).unlink(missing_ok=True)
    with socketserver.ThreadingUnixStreamServer(SOCKET,Handler) as server:
        server.store=store
        os.chmod(SOCKET,0o600)
        server.serve_forever()


if __name__ == '__main__':
    main()
