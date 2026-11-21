"""Owner-private emotional memory, using local SQLite FTS5 and Chinese character pairs."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

EXCLUDE = re.compile(r'工作|上班|客户|项目|任务|生图|绘图|画图|帮我画|出图|改图|服务器|服务端|调试|排障|接口|代码|部署|脚本|报错|配置|日志|运维|系统提示|提示词|口令|指令|密码|账号|手机号|https?://|[a-z]{3,}|\d{5,}', re.I)
THEMES = {
    '陪伴':'陪我|陪着|陪伴|有人在|抱抱|拥抱|听我说|听我讲|倾听',
    '低落':'难过|低落|伤心|委屈|失落|不开心|心情不好|想哭',
    '安心':'安心|踏实|放心|安全感|被理解|被在乎',
    '纪念':'纪念|难忘|第一次|生日|一直记得',
    '思念':'想念|思念|舍不得|很想你|挂念',
    '喜悦':'高兴|开心|幸福|感动|珍惜',
    '压力':'焦虑|紧张|担心|害怕|不安',
}
WORTH = re.compile(r'对我.{0,5}重要|我(?:一直|最|更|很|特别)?(?:希望|喜欢|珍惜|在意|怀念|难忘|记得)|每当|每次|的时候|那天|那次|第一次|纪念日|记住|记得我|让我.{0,5}(?:安心|感动|踏实)|谢谢你.{1,32}')
OPERATIONS = re.compile(r'生成|图片|海报|插画|修图|画[一两三四五张幅]|排版|开发|数据库|测试|维修|需求|排期|交付|老板|工单|汇报|同事|会议|修复|端口|重启|订单|方案|加班|开会|业务|报表|排查|接单|客户|稿件|产品|画面|参考图|美术|素材|上线|联网|电脑故障|写.{0,3}程序')


def terms(text):
    tags=[k for k,v in THEMES.items() if re.search(v,text)]
    words=[s[i:i+2] for s in re.findall(r'[\u3400-\u9fff]+',text) for i in range(len(s)-1)]
    return list(dict.fromkeys(tags+words))


def note(text):
    if (not isinstance(text,str) or not 3<=len(text)<=240 or EXCLUDE.search(text)
            or re.search(r'不要记|别记|不许记|忘掉|忘记|假如|比如|假设|[？?]|[“「]|你还记得',text)
            or not WORTH.search(text) or not any(re.search(v,text) for v in THEMES.values())):
        return None
    if OPERATIONS.search(text) or re.search(r'张.{0,3}图|绘画|画.{0,5}图|帮.{0,5}(?:画|排查|检查服务)|不要保存|别存|不想被记住',text):
        return None
    for clause in re.split(r'[。！？；\n]',text):
        if WORTH.search(clause) and any(re.search(v,clause) for v in THEMES.values()):
            return clause.strip()
    return None


def turn(path,text):
    if not text or EXCLUDE.search(text) or OPERATIONS.search(text):
        return []
    with closing(sqlite3.connect(path,timeout=3)) as db, db:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(words,body UNINDEXED,day UNINDEXED)")
        forget=re.fullmatch(r'(?:请)?(?:忘掉|忘记|删除)(?:那条|关于)?(.{1,80}?)(?:的记忆)[。！! ]*',text)
        if forget:
            db.execute('DELETE FROM memories WHERE instr(body,?)>0',(forget[1],))
            return []
        keys=terms(text)
        matches=[]
        if keys:
            rows=db.execute('SELECT day,body,words FROM memories WHERE words MATCH ? ORDER BY rank LIMIT 8',
                               (' OR '.join('"'+t+'"' for t in keys[:80]),)).fetchall()
            for day,body,words in rows:
                shared=set(keys).intersection(words.split())
                if shared.intersection(THEMES) or len(shared)>=3:
                    matches.append((day,body))
            matches=matches[:3]
        value=note(text)
        if value and not db.execute('SELECT 1 FROM memories WHERE body=?',(value,)).fetchone():
            db.execute('INSERT INTO memories VALUES(?,?,?)',(' '.join(terms(value)),value,datetime.now(timezone.utc).date().isoformat()))
        return [dict(day=d,words=b) for d,b in matches if b!=value]


def safe_turn(path, text):
    try:
        return turn(path, text)
    except (OSError, sqlite3.Error):
        return []


if __name__=='__main__':
    print(json.dumps(safe_turn(Path('/home/ubuntu/qq-dsh/records/heart.sqlite3'),sys.stdin.read(4001)),ensure_ascii=False))
