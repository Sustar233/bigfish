"""Durable topic weights and feedback; factual verification is independent."""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
import time

CATEGORIES = ['国际政治', '战争安全', '全球经济', '灾害卫生', '科技科学', '中国及周边']
ROOT = Path('/home/ubuntu/server-maintenance/news')
LEGACY_FEEDBACK = Path('/home/ubuntu/qq-codex/bridge/.private/records/news-feedback.sqlite3')
RATINGS = ('重要', '不感兴趣', '少推这类', '多推这类')
DEFAULT = {'version': 1,
    '说明': '1为正常权重，越高越优先；0跳过普通新闻。重大事件和更正保留。关键词按字面匹配。',
    'topic_weights': {c: 1.0 for c in CATEGORIES},
    'blocked_categories': [], 'blocked_keywords': [], 'keyword_weights': {},
    'event_feedback': {}, 'feedback_cursor': 0, 'feedback_history': [],
    'editorial_rules': {},
    'presentation': {'narrator': '小c', 'style': '像朋友口述新闻，自然转述，不堆播音腔',
                     'inline_links': False, 'publisher_prefaces': False,
                     'sources_on_request': True}}


def load(path):
    result = copy.deepcopy(DEFAULT)
    if Path(path).exists():
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        result.update(raw)
        result['topic_weights'] = {**DEFAULT['topic_weights'], **raw.get('topic_weights', {})}
    for value in [*result['topic_weights'].values(), *result['keyword_weights'].values()]:
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 5:
            raise ValueError('新闻偏好权重必须是0到5之间的有限数值')
    for key in ('blocked_categories', 'blocked_keywords'):
        if not isinstance(result[key], list) or any(not isinstance(x, str) or not x or len(x)>80 for x in result[key]):
            raise ValueError('Invalid preference filter')
    return result


def save(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as staging:
            temp = Path(staging.name)
            json.dump(value, staging, ensure_ascii=False, indent=2)
        temp.chmod(0o600)
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def guide_path(root=ROOT):
    return Path(root) / '.private/preferences/interest_preferences.json'


@contextmanager
def lock(path):
    import fcntl

    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def apply_feedback(prefs, at, key, category, rating, number=None):
    if category in CATEGORIES and rating in ('重要', '多推这类', '少推这类'):
        factor = .8 if rating == '少推这类' else 1.25
        before = prefs['topic_weights'][category]
        prefs['topic_weights'][category] = round(min(5, max(.25, before * factor)), 4) if before else 0
    prefs['event_feedback'][key] = rating
    entry = {'at': at, 'event_key': key, 'category': category, 'rating': rating}
    if number is not None:
        entry['id'] = number
        prefs['feedback_cursor'] = number
    prefs['feedback_history'] = (prefs['feedback_history'] + [entry])[-100:]
    prefs['event_feedback'] = dict(list(prefs['event_feedback'].items())[-500:])


def sync(path, feedback_path):
    with lock(path):
        return sync_locked(path, feedback_path)


def sync_locked(path, feedback_path):
    prefs = load(path)
    rows = []
    if Path(feedback_path).exists():
        with sqlite3.connect(Path(feedback_path).resolve().as_uri()+'?mode=ro', uri=True) as db:
            rows = db.execute('SELECT id,at,event_key,category,rating FROM feedback WHERE id>? ORDER BY id',
                              (prefs['feedback_cursor'],)).fetchall()
    for number, at, key, category, rating in rows:
        apply_feedback(prefs, at, key, category, rating, number)
    if rows or not Path(path).exists():
        prefs['updated_at'] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        save(path, prefs)
    return prefs


def update(request, root=ROOT, legacy_feedback=LEGACY_FEEDBACK):
    """One writer interface for the desktop, smallc commands and Feiyu tools."""
    path = guide_path(root)
    with lock(path):
        if not path.exists():
            save(path, load(Path(root)/'.private/interest_preferences.json'))
        prefs = sync_locked(path, legacy_feedback)
        action = request.get('action')
        if action == 'show':
            return prefs
        if action == 'feedback':
            key, category, rating = (request.get(k, '') for k in ('event_key','category','rating'))
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{5,99}', key) or rating not in RATINGS:
                raise ValueError('新闻反馈参数无效')
            apply_feedback(prefs, time.time(), key, category, rating)
        elif action in ('set_weight', 'adjust_weight'):
            name = request.get('topic', '')
            if name not in CATEGORIES:
                raise ValueError('未知新闻主题')
            if action == 'set_weight':
                value = request.get('weight')
                if isinstance(value, bool) or not isinstance(value, (int,float)) or not 0 <= value <= 5:
                    raise ValueError('权重应为 0 至 5')
            else:
                direction = request.get('direction')
                if direction not in ('more','less'):
                    raise ValueError('需要选择多推或少推')
                before = prefs['topic_weights'][name]
                value = min(5,max(.25, before * (1.25 if direction=='more' else .8)))
            prefs['topic_weights'][name] = round(value,4)
        elif action in ('set_rule', 'add_rule'):
            name, value = request.get('name','').strip(), request.get('value','').strip()
            rules = prefs['editorial_rules']
            if action == 'add_rule':
                if not value:
                    raise ValueError('请输入要补充的新闻偏好')
                if value in rules.values():
                    return prefs
                name = next(f'补充选题偏好 {i}' for i in range(1, len(rules) + 2)
                            if f'补充选题偏好 {i}' not in rules)
            if not re.fullmatch(r'[\w -]{1,30}', name) or len(value)>240:
                raise ValueError('规则名应为 1–30 字，内容最多 240 字')
            if name not in rules and len(rules) >= 24:
                raise ValueError('已有 24 条规则，请先整理')
            if value:
                rules[name] = value
            else:
                rules.pop(name, None)
        else:
            raise ValueError('未知偏好操作')
        prefs['updated_at'] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        save(path, prefs)
        return prefs


def describe(prefs):
    lines = ['当前新闻偏好（1 为正常权重）']
    lines.extend(f'{key}：{value:g}' for key,value in prefs['topic_weights'].items())
    lines.extend(f'{name}：{value}' for name,value in prefs['editorial_rules'].items())
    if prefs['blocked_categories'] or prefs['blocked_keywords']:
        lines.append('过滤：'+'、'.join(prefs['blocked_categories']+prefs['blocked_keywords']))
    return '\n'.join(lines)


def science_milestone(text):
    return bool(re.search(r'riemann hypothesis|navier.stokes|millennium prize|unitary conjecture|黎曼猜想|千禧年难题|千禧难题|'
                          r'(?:maths?|math(?:ematical|ematics|ematician)|mathematics problem|conjecture|科研|数学|科学|猜想).{0,90}'
                          r'(?:breakthrough|proved|proof|cracked|solved|verify|突破|证明|破解|解出|独立验证)|'
                          r'(?:breakthrough|proved|proof|cracked|solved|verify).{0,90}(?:maths?|mathematics|conjecture|century.old problem)',
                          text.casefold()))


def category(article):
    text = (article.get('title', '')+' '+article.get('summary', '')).lower()
    if science_milestone(text) or article.get('feed','').startswith(('nature_', 'quanta_')):
        return '科技科学'
    rules = [('灾害卫生', r'earthquake|tsunami|pandemic|地震|海啸|疫情|洪水'),
             ('科技科学', r'artificial intelligence|\bai\b|technology|science|space|robot|科技|人工智能|模型|航天|科学'),
             ('全球经济', r'econom|inflation|trade|tariff|bank|interest rate|经济|金融|关税|央行|利率'),
             ('战争安全', r'war|ceasefire|missile|military|attack|战争|停火|导弹|袭击|军事'),
             ('中国及周边', r'china|taiwan|japan|korea|中国|台湾|日本|韩国')]
    for name, pattern in rules:
        if re.search(pattern, text):
            return name
    feed = article.get('feed', '')
    return '科技科学' if 'technology' in feed else '全球经济' if 'business' in feed or 'finance' in feed else '国际政治'


def weight(item, prefs, raw=False):
    name = category(item) if raw else item.get('category', '')
    text = (item.get('title', '')+' '+item.get('summary', '')).casefold()
    protected = item.get('is_correction') or item.get('importance') == 'major' or (raw and item.get('score', 0)>=5)
    rating = prefs['event_feedback'].get(item.get('event_key', ''))
    blocked = name in prefs['blocked_categories'] or any(k.casefold() in text for k in prefs['blocked_keywords'])
    w = prefs['topic_weights'].get(name, 1.0)
    for key, multiplier in prefs['keyword_weights'].items():
        if key.casefold() in text:
            w *= multiplier
    if blocked or rating == '不感兴趣':
        w = 0
    if rating in ('重要', '多推这类'):
        w *= 1.25
    return max(.1, w) if protected else w


def rank(items, prefs, raw=False):
    eligible = [(i, weight(item, prefs, raw), item) for i,item in enumerate(items)]
    eligible = [row for row in eligible if row[1]>0]
    def score(row):
        i,w,item = row
        base = max(1, item.get('score', 1)) if raw else 2 if item.get('importance')=='major' else 1
        return (-base*w, i)
    return [row[2] for row in sorted(eligible, key=score)]


if __name__ == '__main__':
    import sys

    try:
        request = json.loads(sys.stdin.read(16384))
        if request.get('action') == 'feedback_item':
            sys.path.insert(0, '/home/ubuntu/qq-codex/bridge')
            from news_commands import news_command
            print(news_command(LEGACY_FEEDBACK.parent, '/新闻反馈', f"{request.get('item','')} {request.get('rating','')}"))
        else:
            print(describe(update(request)))
    except (ValueError, TypeError, AttributeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
