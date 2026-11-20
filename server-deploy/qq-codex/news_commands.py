"""Owner-only news status/feedback commands; no general filesystem or shell tool."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

NEWS = Path('/home/ubuntu/server-maintenance/news')
RATINGS = {'重要', '不感兴趣', '少推这类', '多推这类'}
LATEST = {'刚才', '这条', '上一条', '最新'}


def delivered_items(db, tables):
    if 'outbox' not in tables:
        return []
    columns = {r[1] for r in db.execute('PRAGMA table_info(outbox)')}
    if not {'id', 'kind', 'event_key', 'status', 'sent'} <= columns:
        return []
    row = db.execute("SELECT kind,event_key FROM outbox WHERE status='sent' ORDER BY sent DESC,id DESC LIMIT 1").fetchone()
    if not row:
        return []
    kind, key = row
    if kind == 'digest' and 'digest_items' in tables:
        return [(k, json.loads(p)) for k, p in db.execute(
            'SELECT event_key,payload FROM digest_items WHERE day=? ORDER BY position',
            (key.removeprefix('digest:'),))]
    if 'events' in tables:
        return [(k, json.loads(p)) for k, p in db.execute('SELECT key,payload FROM events WHERE key=?', (key,))]
    return []


def resolve_items(db, token=''):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    latest = []
    if 'digest_items' in tables:
        latest = [(key,json.loads(payload)) for key,payload in db.execute(
            'SELECT event_key,payload FROM digest_items WHERE day=(SELECT max(day) FROM digest_items) ORDER BY position')]
    if not token or token in LATEST:
        delivered = delivered_items(db, tables)
        return delivered if delivered else ([] if token in LATEST else latest)
    number = re.fullmatch(r'(?:第)?([1-8])(?:条)?', token)
    if number:
        index = int(number[1])-1
        return latest[index:index+1]
    code = token.lower().removeprefix('n')
    if not re.fullmatch('[0-9a-f]{8}', code):
        return []
    rows = [(key,json.loads(payload)) for key,payload in db.execute('SELECT key,payload FROM events')]
    return [(key,e) for key,e in rows+latest if hashlib.sha256(key.encode()).hexdigest()[:8]==code][:1]


def news_followup(records, text):
    recent = r'(?:刚才(?:这|那)?条|这条|那条|上一条)(?:新闻|快报)?'
    if re.fullmatch(recent+r'(?:的)?(?:来源|原文|链接)(?:呢|是什么|给我看看)?[？?。！!]*', text.strip()):
        return news_command(records, '/新闻来源', '刚才')
    rating = re.fullmatch(recent+r'[，,\s]*(重要|不感兴趣|少推这类|多推这类)[。！!]*', text.strip())
    if rating:
        return news_command(records, '/新闻反馈', '刚才 '+rating[1])
    match = re.fullmatch(r'(?:今天|刚才|这份|最新)?(?:的)?(?:世界)?(?:新闻|简报)(?:的)?(?:来源|原文|链接)[呢？?。！!]*', text.strip())
    item = re.fullmatch(r'(?:简报|新闻)?第([1-8])条(?:新闻)?(?:的)?(?:来源|原文|链接)(?:呢|是什么|给我看看)?[？?。！!]*', text.strip())
    feedback = re.fullmatch(r'(?:简报|新闻)?第([1-8])条(?:新闻)?[，,\s]*(重要|不感兴趣|少推这类|多推这类)[。！!]*', text.strip())
    if feedback:
        return news_command(records, '/新闻反馈', feedback[1]+' '+feedback[2])
    if item or match:
        return news_command(records, '/新闻来源', item[1] if item else '')
    return None


def news_command(records, command, argument):
    path = NEWS/'.private/news.sqlite3'
    if not path.exists():
        return '新闻服务尚未初始化。'
    with sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True) as db:
        if command == '/新闻偏好':
            prefs_path = NEWS/'.private/interest_preferences.json'
            prefs = json.loads(prefs_path.read_text()) if prefs_path.exists() else {}
            weights = prefs.get('topic_weights', {})
            return ('当前新闻主题权重（1为正常）：\n'+'\n'.join(k+'：'+str(v) for k,v in weights.items())+
                    '\n反馈后下次采集同步生效。可以说“第2条少推这类”或“第3条多推这类”。')
        if command == '/新闻来源':
            found = resolve_items(db, argument.strip())
            if not found:
                return '还没找到这条新闻的来源记录。可以说“刚才那条新闻的来源”，简报也可以说“第2条的来源”。'
            blocks = []
            for _,e in found:
                links = '\n'.join(s.get('publisher','')+' '+s['url'] for s in e.get('sources',[]) if s.get('url','').startswith('https://'))
                blocks.append(e.get('title','新闻')+'\n'+links)
            return ('你问的原文在这里：\n\n'+'\n\n'.join(blocks))[:2900]
        if command == '/新闻状态':
            values = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM state')}
            health = values.get('source_health', {})
            good = sum(h.get('ok') is True for h in health.values())
            pending = db.execute("SELECT count(*) FROM outbox WHERE status='pending'").fetchone()[0]
            return (f'新闻监控：每15分钟采集，重大快报每天最多3条，21:00简报，23:00–08:00免打扰。\n'
                    f'最近采集：{values.get("last_collection", "尚无")}；来源可用 {good}/{len(health)}；待发送 {pending} 条。\n'
                    '想调选题，可以说“刚才那条少推这类”，简报就说“第2条少推这类”。\n也可以问我新闻来源，或用 /新闻偏好 看选题设置。')
        parts = argument.split(maxsplit=1)
        if len(parts) != 2 or not (parts[0] in LATEST or re.fullmatch(r'(?:[Nn]?[0-9a-fA-F]{8}|[1-8])', parts[0])) or parts[1] not in RATINGS:
            return '用法：/新闻反馈 刚才或简报序号 重要|不感兴趣|少推这类|多推这类。例如 /新闻反馈 刚才 少推这类。'
        matches = resolve_items(db, parts[0])
        if len(matches) > 1:
            return '刚才那份有好几条新闻，告诉我是第几条吧，比如“第2条少推这类”。'
        found = (matches[0][0],matches[0][1].get('category','')) if matches else None
    if not found:
        return '未找到对应新闻。可以说“刚才那条”，或告诉我是简报第几条。'
    target = Path(records)/'news-feedback.sqlite3'
    with sqlite3.connect(target) as db:
        db.execute('CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY,at REAL,event_key TEXT,category TEXT,rating TEXT)')
        db.execute('INSERT INTO feedback(at,event_key,category,rating) VALUES(?,?,?,?)', (time.time(), found[0], found[1], parts[1]))
    target.chmod(0o600)
    return f'已记录“{parts[1]}”，后续筛选会参考这条偏好。'
