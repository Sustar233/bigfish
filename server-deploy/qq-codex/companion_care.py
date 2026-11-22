"""Private, opt-in follow-ups. Store a topic and deadline only."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import re
import sqlite3

LOCAL = timezone(timedelta(hours=8))
TOPICS = {'上台':'上台', '演出':'演出', '比赛':'比赛', '考试':'考试', '见面':'见面'}
RESULT = re.compile(r'结束|完了|完啦|顺利|考完|比完|见到了|发挥得|表现得|取消了|不用问了|别问了')


def care_turn(db, text, now=None):
    now = now or datetime.now(LOCAL)
    db.execute("""CREATE TABLE IF NOT EXISTS care(id INTEGER PRIMARY KEY CHECK(id=1),
               enabled INTEGER DEFAULT 0,quiet_start INTEGER DEFAULT 22,quiet_end INTEGER DEFAULT 9,
               topic TEXT,due REAL)""")
    db.execute('INSERT OR IGNORE INTO care(id) VALUES(1)')
    if re.fullmatch(r'(?:以后)?(?:不用|不要|关闭|别再)主动关心我[了。！!]*',text):
        db.execute('UPDATE care SET enabled=0,topic=NULL,due=NULL')
        return '好，以后就等你来聊。'
    if re.fullmatch(r'(?:以后)?(?:可以|允许|开启)主动关心我[。！!]*',text):
        db.execute('UPDATE care SET enabled=1')
        return '好，你提到在意的事，我可以过后问一句。默认晚上十点到早上九点安静。'
    quiet = re.fullmatch(r'(?:免打扰|别打扰我)[ ：:，]*(\d{1,2})点?到(\d{1,2})点?[。！!]*',text)
    if quiet:
        start,end = map(int,quiet.groups())
        if max(start,end)>23 or start==end:
            return '告诉我两个不同的整点就好，比如「免打扰 22点到9点」。'
        db.execute('UPDATE care SET quiet_start=?,quiet_end=?',(start,end))
        return '好，这段时间我会安静。'
    enabled,topic = db.execute('SELECT enabled,topic FROM care').fetchone()
    if not enabled:
        return
    if topic and RESULT.search(text) and (topic in text or re.search(r'考完|比完|不用问了|别问了|那件事|已经结束',text)):
        db.execute('UPDATE care SET topic=NULL,due=NULL')
        return
    match = re.search(r'今天|明天|后天|(?:周|星期)[一二三四五六日天]', text)
    subject = next((name for name in TOPICS if name in text), None)
    if match and subject and re.search(r'我|有点|紧张|期待|担心',text) and not RESULT.search(text):
        date = match[0]
        days = {'今天':0,'明天':1,'后天':2}.get(date)
        if days is None:
            days = ('一二三四五六日'.index(date[-1].replace('天','日'))-now.weekday())%7
        due = (now+timedelta(days=days)).replace(hour=20,minute=0,second=0,microsecond=0)
        due = max(due,now+timedelta(hours=2))
        db.execute('UPDATE care SET topic=?,due=?',(subject,due.timestamp()))


def deliver_due(path, send, now=None):
    now = now or datetime.now(LOCAL)
    if not path.is_file():
        return
    with closing(sqlite3.connect(path,timeout=3)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='care'").fetchone():
            return
        row = db.execute('SELECT topic,due,quiet_start,quiet_end FROM care WHERE enabled=1 AND due<=?',(now.timestamp(),)).fetchone()
        if not row:
            return
        topic,due,start,end = row
        expired = now.timestamp()-due>86400
        if not expired and (now.hour-start)%24 < (end-start)%24:
            return
        db.execute('UPDATE care SET topic=NULL,due=NULL')
    if not expired:
        send(f'你之前提到的{topic}，后来怎么样了？想聊的话我在。')
