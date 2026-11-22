"""Owner-only news status/feedback commands; no general filesystem or shell tool."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

NEWS = Path('/home/ubuntu/server-maintenance/news')
sys.path.append(str(NEWS))
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
    clean = text.strip().rstrip('？?。！!')
    if clean in ('看新闻偏好','查看新闻偏好','新闻偏好是什么','我的新闻偏好','新闻偏好'):
        return news_command(records,'/新闻偏好','')
    if match := re.fullmatch(r'(?:以后)?(?:新闻)?\s*(多推|少推)(?:些|一点|一些)?\s*(国际政治|战争安全|全球经济|灾害卫生|科技科学|中国及周边|科技新闻|科学新闻|战争新闻)', clean):
        return news_command(records,'/新闻偏好',f'{match[2]} {match[1]}')
    if clean.startswith('新闻偏好：'):
        return news_command(records,'/新闻偏好',clean.split('：',1)[1].strip())
    if match := re.fullmatch(r'(?:请|帮我)?(?:把)?(?:我的)?新闻偏好(?:改为|改成|更新为)[：: ]*(.+)', clean):
        return news_command(records,'/新闻偏好','规则 额外选题偏好：'+match[1])
    if match := re.fullmatch(r'(?:请|帮我)?(?:给)?(?:我的)?新闻偏好(?:加一条|补充)[：: ]*(.+)', clean):
        return news_command(records,'/新闻偏好','加规则 '+match[1])
    if re.fullmatch(r'(?:记住[，,：: ]*)?(?:以后|今后|请|帮我)(?=.*(?:新闻|快报|简报))(?=.*(?:多推|少推|优先|只推|关注)).{3,220}', clean):
        return news_command(records,'/新闻偏好','加规则 '+clean)
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
    if command == '/新闻偏好':
        import news_preferences as preferences

        request = {'action':'show'}
        if argument.strip():
            aliases = {'科技新闻':'科技科学','科学新闻':'科技科学','战争新闻':'战争安全'}
            if match := re.fullmatch(r'(.+?)\s+(多推|少推|[0-5](?:\.\d+)?)', argument.strip()):
                topic = aliases.get(match[1],match[1])
                if match[2] in ('多推','少推'):
                    request = {'action':'adjust_weight','topic':topic,'direction':'more' if match[2]=='多推' else 'less'}
                else:
                    request = {'action':'set_weight','topic':topic,'weight':float(match[2])}
            elif match := re.fullmatch(r'规则\s+([^：:]+)[：:]\s*(.*)', argument.strip()):
                request = {'action':'set_rule','name':match[1],'value':match[2]}
            elif match := re.fullmatch(r'加规则\s+(.+)', argument.strip()):
                request = {'action':'add_rule','value':match[1]}
            else:
                return '可以用“/新闻偏好 科技科学 多推”，或“/新闻偏好 规则 数学突破：优先关注重大数学成果”。'
        try:
            prefs = preferences.update(request, NEWS, Path(records)/'news-feedback.sqlite3')
        except (ValueError, OSError, sqlite3.Error):
            return '新闻偏好操作未完成，请核对主题和参数后再试。'
        return ('已更新共享新闻偏好。\n' if request['action']!='show' else '')+preferences.describe(prefs)
    path = NEWS/'.private/news.sqlite3'
    if not path.exists():
        return '新闻服务尚未初始化。'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
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
    import news_preferences as preferences

    try:
        preferences.update({'action':'feedback','event_key':found[0],'category':found[1],'rating':parts[1]},
                           NEWS, Path(records)/'news-feedback.sqlite3')
    except (ValueError, OSError, sqlite3.Error):
        return '这条新闻反馈没能写入共享指南，请稍后再试。'
    return f'已记录“{parts[1]}”，共享新闻偏好已更新。'
