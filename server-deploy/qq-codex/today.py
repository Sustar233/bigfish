"""Render the owner's private daily overview from existing local results."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import sys
from zoneinfo import ZoneInfo

HOME = Path('/home/ubuntu')
TZ = ZoneInfo('Asia/Shanghai')


def read_db(path):
    return closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.5))


def weather(home, now):
    with read_db(home/'server-maintenance/weather/.private/weather.sqlite3') as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='forecasts'").fetchone():
            return '今天的通勤预报还没有存档。'
        row = db.execute('SELECT updated,body FROM forecasts WHERE day=?', (now.date().isoformat(),)).fetchone()
    if not row:
        return '今天的通勤预报还没有存档。'
    return f'{datetime.fromisoformat(row[0]):%H:%M} 更新\n{row[1][:600]}'


def zhihu(home, now):
    root = home/'dailyZhihu/output'
    if not (root/'server-status.json').is_file():
        return '还没有日报完成记录。'
    status = json.loads((root/'server-status.json').read_text(encoding='utf-8'))
    if status.get('date') != now.date().isoformat() or status.get('status') not in ('sent', 'generated'):
        return '今天的日报还未就绪，每天 08:00 开始生成。'
    stamp = datetime.fromisoformat(status['completed_at']).astimezone(TZ)
    label = '已提交邮件' if status.get('email_sent') else '已生成'
    output = f'{stamp:%H:%M} {label}'
    try:
        digest = json.loads((root/'digest.json').read_text(encoding='utf-8'))
        if digest['fetched_at'][:10] == status['date']:
            titles = [item['title_zh'][:70] for item in digest['items'][:3]]
            if titles:
                output += '\n' + ' · '.join(titles)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return output


def news(home, now):
    with read_db(home/'server-maintenance/news/.private/news.sqlite3') as db:
        row = db.execute("""SELECT dedup,sent FROM outbox WHERE kind='digest' AND status='sent'
                            AND message_id IS NOT NULL ORDER BY sent DESC LIMIT 1""").fetchone()
        if not row:
            return '还没有已投递的晚报。'
        day = row[0].removeprefix('digest:')
        items = db.execute('SELECT payload FROM digest_items WHERE day=? ORDER BY position LIMIT 3', (day,))
        titles = [json.loads(item[0])['title'][:75] for item in items]
    stamp = datetime.fromtimestamp(row[1], TZ)
    return f'{day} 晚报（{stamp:%m-%d %H:%M} 发出）' + ('\n' + ' · '.join(titles) if titles else '')


def tasks(home, bot):
    path = home/'server-maintenance/images/.private/jobs.sqlite3'
    with read_db(path) as db:
        rows = db.execute("""SELECT id,status,updated FROM jobs WHERE CAST(bot AS TEXT)=?
                             AND status IN ('queued','generating','generated','sending','uncertain')
                             ORDER BY updated DESC LIMIT 3""", (str(bot),)).fetchall()
    labels = {'queued': '等待生成', 'generating': '生成中', 'generated': '待发图',
              'sending': '正在发送', 'uncertain': '投递待核对'}
    return '\n'.join(f'{datetime.fromtimestamp(at, TZ):%m-%d %H:%M} 绘图 {job[:6]} · {labels[state]}'
                     for job,state,at in rows) or '这个账号没有待处理的绘图任务。'


def latest_picture(home, bot):
    with read_db(home/'server-maintenance/images/.private/jobs.sqlite3') as db:
        row = db.execute("""SELECT status,updated FROM jobs WHERE CAST(bot AS TEXT)=?
                            ORDER BY updated DESC LIMIT 1""", (str(bot),)).fetchone()
    if not row:
        return '这个账号还没有绘图记录。'
    labels = {'queued': '排队中', 'generating': '正在画', 'generated': '已画好，等着发送',
              'sending': '正在发图', 'sent': '已发图', 'sent_relayed': '已转发',
              'failed': '没有完成', 'uncertain': '已尝试发送，送达情况待确认'}
    return f'本账号最近更新的一张图（{datetime.fromtimestamp(row[1], TZ):%m-%d %H:%M}）：{labels.get(row[0], "进度待确认")}。'


TOPICS = ('weather', 'zhihu', 'news', 'reading', 'picture', 'day')


def topics_for(text):
    """Look up possible context, never dispatch an action or replace the user's turn."""
    if not text or text.lstrip().startswith('/') or len(text) > 400:
        return ()
    if re.search(r'(?:今天|今日|今日份).{0,6}(?:概览|简报|一览)|(?:说说|捋捋|过一遍).{0,5}今天.{0,5}(?:情况|要紧事)', text):
        return ('day',)
    matches = []
    if re.search(r'(?:带|拿|用|备).{0,3}伞|(?:天气|气温|下雨|会冷|会热|降温).{0,8}(?:吗|么|如何|怎样|怎么样|多少|不)|会不会(?:下雨|降温|很冷|很热)|冷不冷|热不热|下不下雨|(?:今天|长沙|早上|出门|通勤).{0,6}(?:天气|几度|下雨)', text):
        matches.append('weather')
    if re.search(r'知乎|双语精读|英语精读', text):
        matches.append('zhihu')
    if re.search(r'新闻|晚报|发生了什么大事|有啥大事|有什么大事', text):
        matches.append('news')
    if re.search(r'(?:画|图).{0,9}(?:好了吗|好了没|好没|画好|好啦|进度|怎么样了|出了吗|出了没|发了吗|发了没|到哪了|画完)|(?:刚才|之前).{0,8}(?:那张图|的画).{0,4}(?:呢|怎样)', text):
        matches.append('picture')
    if not matches and re.search(r'(?:今天|今日|最近|这两天).{0,12}(?:值得(?:看|读)|有什么看头|看点|新鲜事|有啥好看|有什么好看)', text):
        matches.append('reading')
    return tuple(matches)


def conversation_facts(topics, bot, home=HOME, now=None):
    now = now or datetime.now(TZ)
    expanded = set(topics)
    if 'day' in expanded:
        expanded.update(('weather', 'zhihu', 'news'))
    if 'reading' in expanded:
        expanded.update(('zhihu', 'news'))
    facts = {}
    for topic, label, reader, arg in [('weather', '当日长沙通勤预报', weather, now),
                                      ('zhihu', '当日知乎精读', zhihu, now),
                                      ('news', '最近已送达的新闻晚报', news, now),
                                      ('picture', '本账号绘图进度', latest_picture, bot)]:
        if topic in expanded:
            try:
                facts[label] = reader(home, arg)
            except (OSError, ValueError, KeyError, IndexError, TypeError, sqlite3.Error):
                facts[label] = '暂时取不到记录。'
    return facts


def overview(bot, home=HOME, now=None):
    now = now or datetime.now(TZ)
    sections = [f'{now:%m月%d日 %H:%M} · 今日']
    for title, reader, arg in [('长沙天气', weather, now), ('知乎精读', zhihu, now),
                               ('最近新闻', news, now), ('待处理', tasks, bot)]:
        try:
            text = reader(home, arg)
        except (OSError, ValueError, KeyError, IndexError, TypeError, sqlite3.Error):
            text = '暂时读不到记录。'
        sections.append(f'【{title}】{text}')
    return '\n\n'.join(sections)


if __name__ == '__main__':
    if len(sys.argv) == 2:
        print(overview(sys.argv[1]))
    elif len(sys.argv) == 3 and sys.argv[2] in TOPICS:
        print(json.dumps(conversation_facts([sys.argv[2]], sys.argv[1]), ensure_ascii=False))
    else:
        raise SystemExit(2)
