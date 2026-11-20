"""Durable topic weights and feedback; factual verification is independent."""
import copy
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path
import re
import sqlite3

CATEGORIES = ['国际政治', '战争安全', '全球经济', '灾害卫生', '科技科学', '中国及周边']
DEFAULT = {'version': 1,
    '说明': '1为正常权重，越高越优先；0跳过普通新闻。重大事件和更正保留。关键词按字面匹配。',
    'topic_weights': {c: 1.0 for c in CATEGORIES},
    'blocked_categories': [], 'blocked_keywords': [], 'keyword_weights': {},
    'event_feedback': {}, 'feedback_cursor': 0, 'feedback_history': [],
    'presentation': {'narrator': '小c', 'style': '像朋友口述新闻，自然转述，不堆播音腔',
                     'inline_links': False, 'publisher_prefaces': False,
                     'sources_on_request': True}}


def load(path):
    result = copy.deepcopy(DEFAULT)
    if Path(path).exists():
        raw = json.loads(Path(path).read_text())
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
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.chmod(0o600)
    temp.replace(path)


def sync(path, feedback_path):
    prefs = load(path)
    rows = []
    if Path(feedback_path).exists():
        with sqlite3.connect('file:'+str(feedback_path)+'?mode=ro', uri=True) as db:
            rows = db.execute('SELECT id,at,event_key,category,rating FROM feedback WHERE id>? ORDER BY id',
                              (prefs['feedback_cursor'],)).fetchall()
    for number, at, key, category, rating in rows:
        if category in CATEGORIES and rating in ('重要', '多推这类', '少推这类'):
            factor = .8 if rating == '少推这类' else 1.25
            prefs['topic_weights'][category] = round(max(.25, min(3, prefs['topic_weights'][category]*factor)), 4)
        prefs['event_feedback'][key] = rating
        prefs['feedback_history'].append({'id': number, 'at': at, 'event_key': key,
                                          'category': category, 'rating': rating})
        prefs['feedback_cursor'] = number
    prefs['feedback_history'] = prefs['feedback_history'][-100:]
    prefs['event_feedback'] = dict(list(prefs['event_feedback'].items())[-500:])
    if rows or not Path(path).exists():
        prefs['updated_at'] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        save(path, prefs)
    return prefs


def category(article):
    text = (article.get('title', '')+' '+article.get('summary', '')).lower()
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
