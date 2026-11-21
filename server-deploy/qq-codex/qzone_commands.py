"""Owner-only, explicit Qzone likes using NapCat 4.18.42 native reads.

No model decides the account or post. A committed reservation prevents a lost
write acknowledgement or repeated chat command from causing another write.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import time

LIKE_COMMANDS = {
    '/空间点赞', '/说说点赞', '/空间点赞最新', '/说说点赞最新',
    '给我最新一条说说点赞', '给我的最新一条说说点赞',
    '给我最新的说说点赞', '给我的最新说说点赞', '赞一下我最新的说说',
    '给我说说点赞', '给我的说说点赞', '给我空间点赞',
    '给我最新一条说说点个赞', '给我的最新一条说说点个赞',
}
USAGE = '可以发“给我最新一条说说点赞”或 /空间点赞；只处理你本人最新可见的一条说说。/空间状态 查看最近结果。'
TZ = timezone(timedelta(hours=8))


def parse(text):
    command = re.sub(r'\s+', '', text.strip()).rstrip('。！!')
    if command in LIKE_COMMANDS:
        return 'like'
    if command == '/空间状态':
        return 'status'
    if command.startswith(('/空间点赞', '/说说点赞', '/空间状态')):
        return 'usage'
    return None


def own_posts(data, owner):
    if not isinstance(data, dict) or not isinstance(data.get('msglist'), list):
        raise ValueError('invalid_qzone_list')
    result = []
    for post in data['msglist']:
        if not isinstance(post, dict) or str(post.get('user_id')) != owner:
            continue
        feed = post.get('feed')
        if not isinstance(feed, dict):
            continue
        common = feed.get('cell_common')
        if not isinstance(common, dict) or common.get('app_id') != 311:
            continue
        tid, occurred = post.get('tid'), post.get('time')
        if not isinstance(tid, str) or not tid or len(tid) > 8192:
            continue
        if isinstance(occurred, bool) or not isinstance(occurred, int) or not 0 < occurred <= time.time() + 300:
            continue
        result.append(post)
    return result


def liked(post):
    value = (post.get('feed', {}).get('cell_like') or {}).get('liked')
    return value if isinstance(value, bool) else None


def connect(root):
    path = Path(root) / 'qzone-likes.sqlite3'
    db = sqlite3.connect(path, timeout=5)
    path.chmod(0o600)
    db.execute('''CREATE TABLE IF NOT EXISTS likes (
        owner TEXT, tid TEXT, state TEXT NOT NULL, updated REAL NOT NULL,
        PRIMARY KEY(owner,tid))''')
    db.commit()
    return db


def save(db, owner, tid, state):
    with db:
        db.execute('INSERT OR REPLACE INTO likes VALUES (?,?,?,?)',
                   (owner, tid, state, time.time()))


def status(root, owner):
    if not (Path(root) / 'qzone-likes.sqlite3').exists():
        return '还没有空间点赞记录。' + USAGE
    db = connect(root)
    try:
        row = db.execute('SELECT state,updated FROM likes WHERE owner=? ORDER BY updated DESC LIMIT 1',
                         (owner,)).fetchone()
    finally:
        db.close()
    if row is None:
        return '还没有空间点赞记录。' + USAGE
    label = '已核验点赞成功' if row[0] == 'confirmed' else '结果待核对，未自动重复点赞'
    return '最近一次空间操作：' + label + '（' + datetime.fromtimestamp(row[1], TZ).strftime('%m-%d %H:%M') + '）。'


def qzone_command(text, request, config, root):
    action = parse(text)
    if action is None:
        return None
    if action == 'usage':
        return USAGE
    owner, bot = str(config['owner_qq']), str(config['bot_qq'])
    if action == 'status':
        try:
            return status(root, owner)
        except (OSError, sqlite3.Error):
            return '暂时读不到空间操作记录，没有发起点赞。'
    db = None
    try:
        info = request('get_login_info', {})
        if not isinstance(info, dict) or str(info.get('user_id')) != bot:
            return '当前QQ身份不匹配，没有发起点赞。'
        payload = {'target_uin': owner, 'format': 'native'}
        posts = own_posts(request('get_qzone_msg_list', payload), owner)
        if not posts:
            return '暂时没找到你可见的说说，没有发起点赞。'
        post = max(posts, key=lambda p: p['time'])
        tid = post['tid']
        current = liked(post)
        if current is None:
            return '暂时读不到这条说说的点赞状态，没有发起点赞。'
        db = connect(root)
        if current:
            save(db, owner, tid, 'confirmed')
            return '你最新可见的这条说说已经点过赞啦，没有重复点赞。'
        with db:
            inserted = db.execute('INSERT OR IGNORE INTO likes VALUES (?,?,?,?)',
                                  (owner, tid, 'uncertain', time.time())).rowcount
        if not inserted:
            return '这条说说之前已处理过，目前状态需要核对，先不重复点赞。'
        # Exactly one write. Never change endpoint or replay on an exception.
        try:
            request('like_qzone', {'target_uin': owner, 'tid': tid, 'abstime': post['time']})
        except Exception:
            pass
        for attempt in range(2):
            if attempt:
                time.sleep(1)
            try:
                checked = own_posts(request('get_qzone_msg_list', payload), owner)
                match = next((p for p in checked if p['tid'] == tid), None)
                if match is not None and liked(match) is True:
                    save(db, owner, tid, 'confirmed')
                    date = datetime.fromtimestamp(post['time'], TZ).strftime('%m月%d日')
                    preview = re.sub(r'\s+', ' ', str(post.get('content') or '')).strip()[:45]
                    return '已给你' + date + '最新可见的说说点了赞，并核验成功。' + ('“' + preview + '”' if preview else '')
            except Exception:
                continue
        return '已尝试点赞，但暂时没能确认结果；我记下了这条，不会自动重复请求。'
    except Exception:
        return '这次空间接口没接上，暂时没法完成点赞。可以稍后发 /空间状态 查看记录。'
    finally:
        if db is not None:
            db.close()
