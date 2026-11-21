from datetime import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import today


class TodayTest(unittest.TestCase):
    def test_spoken_requests_and_casual_chat(self):
        for text, expected in [('小c，今天有什么值得看？', ('reading',)),
                               ('早上出门要带伞吗？', ('weather',)),
                               ('刚才那张图画好了没呀', ('picture',)),
                               ('说说今天的天气和新闻', ('weather','news')),
                               ('今天好累，陪我聊会儿', ()), ('我今天逃了节课', ()),
                               ('你会不会想我呀', ()), ('/今日', ())]:
            with self.subTest(text=text):
                self.assertEqual(today.topics_for(text), expected)

    def test_empty_host_does_not_create_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            text = today.overview('one', home)
            self.assertIn('【长沙天气】', text)
            self.assertEqual(list(home.iterdir()), [])

    def test_dates_receipts_and_account_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            day = '2026-11-20'
            now = datetime.fromisoformat(day + 'T08:10:00+08:00')
            def database(rel, script):
                path = home/rel
                path.parent.mkdir(parents=True)
                db = sqlite3.connect(path)
                try:
                    db.executescript(script)
                finally:
                    db.close()
            database('server-maintenance/weather/.private/weather.sqlite3',
                     "CREATE TABLE forecasts(day,updated,body); INSERT INTO forecasts VALUES('2026-11-19','','昨日天气');")
            database('server-maintenance/news/.private/news.sqlite3', """
                CREATE TABLE outbox(kind,status,message_id,dedup,sent);
                INSERT INTO outbox VALUES('digest','sent','1','digest:2026-11-19',100);
                INSERT INTO outbox VALUES('digest','queued',NULL,'digest:2026-11-20',200);
                CREATE TABLE digest_items(day,position,payload);
                INSERT INTO digest_items VALUES('2026-11-19',1,'{"title":"已发标题"}');
                INSERT INTO digest_items VALUES('2026-11-20',1,'{"title":"草稿标题"}');
            """)
            database('server-maintenance/images/.private/jobs.sqlite3', """
                CREATE TABLE jobs(bot,id,status,updated);
                INSERT INTO jobs VALUES('one','ownjob','uncertain',100);
                INSERT INTO jobs VALUES('two','otherjob','queued',200);
            """)
            root = home/'dailyZhihu/output'
            root.mkdir(parents=True)
            (root/'server-status.json').write_text(json.dumps(dict(
                date=day, status='sent', email_sent=True, completed_at=now.isoformat())))
            (root/'digest.json').write_text(json.dumps(dict(fetched_at=day,items=[dict(title_zh='今日精读')])))
            text = today.overview('one', home, now)
            facts = today.conversation_facts(('picture',), 'one', home, now)
            self.assertEqual(set(facts), {'本账号绘图进度'})
            self.assertIn('送达情况待确认', facts['本账号绘图进度'])
            self.assertEqual(set(today.conversation_facts(('reading',), 'one', home, now)),
                             {'当日知乎精读','最近已送达的新闻晚报'})
            for expected in ('还没有存档', '今日精读', '已发标题', 'ownjob'):
                self.assertIn(expected, text)
            for hidden in ('昨日天气', '草稿标题', 'otherj'):
                self.assertNotIn(hidden, text)
