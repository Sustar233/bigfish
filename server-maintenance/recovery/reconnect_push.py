"""Existing health-check heartbeat dispatches bounded, durable reconnect catch-up."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path('/home/ubuntu/server-maintenance/recovery')
COMMANDS = {
    'weather': ['/usr/bin/python3', '/home/ubuntu/server-maintenance/weather/weather_morning.py', '--catch-up'],
    'news': ['/usr/bin/python3', '/home/ubuntu/server-maintenance/news/news_watch.py', '--flush-only'],
    'gold': ['/usr/bin/python3', '/home/ubuntu/gold-watch/gold_watch.py'],
}
TIMERS = {'weather': ['changsha-weather.timer'], 'news': ['news-watch.timer','news-digest.timer'],
          'gold': ['gold-price-watch.timer']}


class State:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        (self.root / '.private').mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / '.private/reconnect.sqlite3'
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS tasks(episode INTEGER,topic TEXT,status TEXT,retry_at REAL,result TEXT,
                    PRIMARY KEY(episode,topic));''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def get(db, key, default=None):
        row = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put(db, key, value):
        db.execute('INSERT OR REPLACE INTO state VALUES(?,?)', (key, json.dumps(value)))

    def heartbeat(self, online, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = self.get(db, 'online')
            episode = self.get(db, 'episode', 0)
            self.put(db, 'online', bool(online))
            if not online:
                return False
            if previous is not True:
                episode += 1
                self.put(db, 'episode', episode)
                db.executemany('INSERT INTO tasks VALUES(?,?,?,0,NULL)', [(episode, topic, 'pending') for topic in COMMANDS])
            due = db.execute("SELECT 1 FROM tasks WHERE episode=? AND status!='done' AND retry_at<=?", (episode, now)).fetchone()
            if not due or self.get(db, 'lease_until', 0) > now:
                return False
            self.put(db, 'lease_until', now + 360)
            return True

    def pending(self):
        with self.db() as db:
            episode = self.get(db, 'episode', 0)
            rows = db.execute("SELECT topic FROM tasks WHERE episode=? AND status!='done' AND retry_at<=? ORDER BY rowid", (episode, time.time())).fetchall()
        return episode, [row[0] for row in rows]

    def result(self, episode, topic, result):
        status = result.get('status')
        waiting = status in ('queued','qq_offline_pending','source_unavailable','qq_configuration_error',
            'check_failed','already_running','quiet_hours','runner_error') or result.get('delivery') == 'queued_qq_offline'
        if status == 'sent' and any(value in ('qq_offline_pending','quiet_hours') for value in result.get('outcomes', [])):
            waiting = True
        with self.db() as db:
            db.execute('UPDATE tasks SET status=?,retry_at=?,result=? WHERE episode=? AND topic=?',
                ('pending' if waiting else 'done', time.time()+300 if waiting else 0,
                 json.dumps(result, ensure_ascii=False), episode, topic))


def enabled(topic):
    return any(subprocess.run(['systemctl','is-active','--quiet',timer], capture_output=True).returncode == 0 for timer in TIMERS[topic])


def execute(topic):
    if not enabled(topic):
        return {'status':'disabled'}
    try:
        result = subprocess.run(COMMANDS[topic], capture_output=True, text=True, timeout=90)
        for line in reversed(result.stdout.splitlines()):
            try:
                data = json.loads(line)
                if isinstance(data, dict) and isinstance(data.get('status'), str):
                    return {key:data[key] for key in ('status','delivery','day','outcomes') if key in data}
            except ValueError:
                pass
    except Exception:
        pass
    return {'status':'runner_error'}


def work(state=None, runner=execute):
    state = state or State()
    with (state.root / '.private/worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        episode, topics = state.pending()
        try:
            for topic in topics:
                try:
                    result = runner(topic)
                except Exception:
                    result = {'status':'runner_error'}
                state.result(episode, topic, result)
        finally:
            with state.db() as db:
                state.put(db, 'lease_until', 0)


def heartbeat(online):
    state = State()
    if state.heartbeat(online):
        try:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            return True
        except Exception:
            with state.db() as db:
                state.put(db,'lease_until',0)
    return False


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    if args.worker:
        work()
