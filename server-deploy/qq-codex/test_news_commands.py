import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import news_commands as n


class NewsCommandTests(unittest.TestCase):
    def test_latest_feedback_and_sources_follow_sent_story_not_newer_pending_story(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'.private').mkdir()
            records = root/'records'
            records.mkdir()
            with sqlite3.connect(root/'.private/news.sqlite3') as db:
                db.executescript('CREATE TABLE events(key TEXT,payload TEXT); CREATE TABLE outbox(id INTEGER,kind TEXT,event_key TEXT,status TEXT,sent REAL);')
                for key in ('delivered-story', 'pending-story'):
                    db.execute('INSERT INTO events VALUES(?,?)', (key,json.dumps({'title':key,'category':'科技科学',
                        'sources':[{'publisher':'BBC','url':'https://bbc.com/news/'+key}]})))
                db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(1,'breaking','delivered-story','sent',100))
                db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(2,'breaking','pending-story','pending',None))
            with patch.object(n, 'NEWS', root):
                text = n.news_followup(records, '刚才那条新闻的来源呢')
                self.assertIn('https://bbc.com/news/delivered-story', text)
                self.assertNotIn('pending-story', text)
                self.assertIn('已记录', n.news_followup(records, '这条新闻少推这类'))
                self.assertNotIn('N编号', n.news_command(records, '/新闻反馈', '无效参数'))
            with sqlite3.connect(records/'news-feedback.sqlite3') as db:
                self.assertEqual(db.execute('SELECT event_key FROM feedback').fetchall(), [('delivered-story',)])

    def test_latest_digest_feedback_requires_a_specific_item(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE events(key TEXT,payload TEXT); CREATE TABLE digest_items(day TEXT,position INTEGER,event_key TEXT,payload TEXT); CREATE TABLE outbox(id INTEGER,kind TEXT,event_key TEXT,status TEXT,sent REAL);')
            for i in (1,2):
                db.execute('INSERT INTO digest_items VALUES(?,?,?,?)',('2026-11-18',i,str(i),'{}'))
            db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(1,'digest','digest:2026-11-18','sent',100))
            self.assertEqual(len(n.resolve_items(db,'刚才')),2)

    def test_digest_sources_and_numbered_feedback_can_be_requested_naturally(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'.private').mkdir()
            records=root/'records'
            records.mkdir()
            (root/'.private/interest_preferences.json').write_text(json.dumps({'topic_weights':{'科技科学':1.5}}))
            with sqlite3.connect(root/'.private/news.sqlite3') as db:
                db.executescript('CREATE TABLE events(key TEXT,payload TEXT); CREATE TABLE digest_items(day TEXT,position INTEGER,event_key TEXT,payload TEXT);')
                db.execute('INSERT INTO digest_items VALUES(?,?,?,?)',('2026-11-17',1,'story-one',json.dumps({
                    'title':'新闻原文','category':'科技科学','sources':[{'publisher':'BBC','url':'https://bbc.com/news/a'}]})))
            with patch.object(n,'NEWS',root):
                self.assertIn('https://bbc.com/news/a',n.news_followup(records,'第1条来源呢'))
                self.assertIn('已记录',n.news_followup(records,'第1条少推这类'))
                self.assertIsNone(n.news_followup(records,'这段代码怎么理解'))
                self.assertIn('科技科学：1.5',n.news_command(records,'/新闻偏好',''))

    def test_status_and_feedback_are_fixed_scope_and_validate_event(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'.private').mkdir()
            records = root/'records'
            records.mkdir()
            with sqlite3.connect(root/'.private/news.sqlite3') as db:
                db.executescript('CREATE TABLE state(key TEXT,value TEXT); CREATE TABLE events(key TEXT,payload TEXT); CREATE TABLE outbox(status TEXT);')
                db.execute('INSERT INTO events VALUES(?,?)', ('event-one', json.dumps({'category': '全球经济'})))
            with patch.object(n, 'NEWS', root):
                self.assertIn('21:00', n.news_command(records, '/新闻状态', ''))
                code = hashlib.sha256(b'event-one').hexdigest()[:8]
                self.assertIn('已记录', n.news_command(records, '/新闻反馈', 'N'+code+' 少推这类'))
                self.assertIn('未找到', n.news_command(records, '/新闻反馈', 'N00000000 不感兴趣'))
                self.assertIn('用法', n.news_command(records, '/新闻反馈', '../../secret 重要'))
            with sqlite3.connect(records/'news-feedback.sqlite3') as db:
                self.assertEqual(db.execute('SELECT rating FROM feedback').fetchall(), [('少推这类',)])


if __name__ == '__main__':
    unittest.main()
