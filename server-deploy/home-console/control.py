"""Fixed feature registry. No arbitrary command or file operations from HTTP."""
import hashlib
import json
from pathlib import Path
import subprocess
import sqlite3
from contextlib import closing

ROOT = Path('/home/ubuntu/home-console')
FLAGS = ROOT / 'data/flags'
GROUP_DB = Path('/home/ubuntu/qq-group/.private/control.sqlite3')
TIMERS = {
    'news': 'news-watch.timer', 'digest': 'news-digest.timer',
    'weather': 'changsha-weather.timer', 'zhihu': 'zhihu-daily.timer',
    'gold': 'gold-price-watch.timer',
}
LABELS = {'smallc': '小 c 私聊', 'harness': '大肥鱼私聊', 'group': '三人群聊',
          'news': '新闻快报', 'digest': '晚间简报', 'weather': '早间天气',
          'zhihu': '知乎日报', 'gold': '金价提醒'}
NOTES = {
    'smallc': '暂停新私聊处理，保留 QQ 登录、记忆与后台通知。暂停时的消息不会补答。',
    'harness': '暂停新私聊处理，保留 QQ 登录和网页后台。已开始的回复可能完成。',
    'group': '暂停群聊回复与群内功能；保留登录与档案。已开始的操作可能完成。',
    'news': '控制后续采集与快报调度；晚间简报单独设置。正在执行的任务仍会完成。',
    'digest': '控制后续晚报调度。已排队的新闻可能由快报任务投递；完全停新闻请同时关闭快报。',
    'weather': '控制后续早间天气调度；不影响私聊里的天气查询。',
    'zhihu': '控制后续日报生成与投递；正在执行的任务仍会完成。',
    'gold': '控制后续金价检查与提醒；正在执行的任务仍会完成。',
}


def run(args):
    return subprocess.run(args, text=True, capture_output=True, timeout=20)


def timer_state(unit):
    p = run(['systemctl', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'UnitFileState'])
    values = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
    if p.returncode or values.get('LoadState') != 'loaded':
        return {'enabled': None, 'actual': 'unknown', 'saved': 'unknown'}
    saved = values.get('UnitFileState', 'unknown')
    active = values.get('ActiveState', 'unknown')
    enabled = True if active == 'active' and saved == 'enabled' else False if active == 'inactive' and saved == 'disabled' else None
    service = unit.replace('.timer', '.service')
    executing = run(['systemctl', 'is-active', service]).stdout.strip() in ('active', 'activating')
    return {'enabled': enabled, 'actual': active, 'saved': saved, 'executing': executing}


def snapshot():
    result = []
    for key, label in LABELS.items():
        if key in TIMERS:
            state = timer_state(TIMERS[key])
        else:
            paused = (FLAGS / (key + '.paused')).exists()
            if key == 'group' and GROUP_DB.exists():
                with closing(sqlite3.connect(f'file:{GROUP_DB}?mode=ro', uri=True, timeout=3)) as db:
                    row = db.execute("SELECT value FROM state WHERE key='paused'").fetchone()
                    paused = paused or bool(row and row[0] == '1')
            unit = {'smallc': 'qq-chat.service', 'harness': 'deepseek-harness.service', 'group': 'qq-group.service'}[key]
            active = run(['systemctl', 'is-active', unit]).stdout.strip()
            state = {'enabled': not paused, 'actual': active or 'unknown', 'saved': 'paused' if paused else 'enabled'}
        result.append(dict(id=key, label=label, note=NOTES[key], category='chat' if key not in TIMERS else 'notice', **state))
    return result


def revision(rows):
    # Exclude changing task execution status from the settings version.
    stable = [(row['id'], row['enabled'], row['actual'], row['saved']) for row in rows]
    return hashlib.sha256(json.dumps(stable).encode()).hexdigest()


def change(key, enabled):
    if key not in LABELS or type(enabled) is not bool:
        raise ValueError('invalid_feature')
    if key in TIMERS:
        p = run(['sudo', '-n', '/usr/local/sbin/bigfish-home-timer', key, 'on' if enabled else 'off'])
        if p.returncode:
            raise RuntimeError('timer_change_failed')
    else:
        FLAGS.mkdir(mode=0o700, parents=True, exist_ok=True)
        flag = FLAGS / (key + '.paused')
        if enabled:
            flag.unlink(missing_ok=True)
        else:
            temporary = flag.with_suffix('.pending')
            temporary.write_text('paused\n')
            temporary.replace(flag)
        if key == 'group':
            with closing(sqlite3.connect(GROUP_DB, timeout=3)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("INSERT OR REPLACE INTO state VALUES('paused',?)", ('0' if enabled else '1',))
                if not enabled:
                    row = db.execute("SELECT value FROM state WHERE key='epoch'").fetchone()
                    db.execute("INSERT OR REPLACE INTO state VALUES('epoch',?)", (str(int(row[0] if row else 0)+1),))


def timer_main():
    import sys
    if sys.argv[1:] == ['traffic']:
        try:
            status = json.loads(Path('/home/ubuntu/server-maintenance/network/status.json').read_text())
            print(json.dumps({key: status.get(key) for key in ('day', 'used', 'daily_limit', 'checked_at')}))
        except (OSError, ValueError):
            raise SystemExit(1)
        return
    if len(sys.argv) != 3 or sys.argv[1] not in TIMERS or sys.argv[2] not in ('on', 'off'):
        raise SystemExit(2)
    unit = TIMERS[sys.argv[1]]
    action = 'enable' if sys.argv[2] == 'on' else 'disable'
    raise SystemExit(run(['/usr/bin/systemctl', action, '--now', unit]).returncode)


if __name__ == '__main__':
    timer_main()
