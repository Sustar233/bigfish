import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import news_preferences as p
import news_watch as n


class PreferencesTests(unittest.TestCase):
    def test_feedback_is_persisted_once_and_changes_topic_weight(self):
        with tempfile.TemporaryDirectory() as td:
            prefs,dbpath = Path(td)/'prefs.json',Path(td)/'feedback.sqlite3'
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE feedback(id INTEGER PRIMARY KEY,at REAL,event_key TEXT,category TEXT,rating TEXT)')
                db.execute("INSERT INTO feedback VALUES(1,1,'event-a','全球经济','少推这类')")
                db.execute("INSERT INTO feedback VALUES(2,1,'event-b','战争安全','不感兴趣')")
            first = p.sync(prefs,dbpath)
            self.assertEqual(first['topic_weights']['全球经济'],.8)
            self.assertEqual(first['topic_weights']['战争安全'],1)
            self.assertEqual(p.sync(prefs,dbpath)['topic_weights']['全球经济'],.8)
            self.assertEqual(first['event_feedback']['event-b'],'不感兴趣')

    def test_weights_reorder_and_filters_do_not_erase_corrections(self):
        prefs = p.load('/nonexistent-interest-test')
        prefs['topic_weights']['科技科学']=2
        a={'title':'科技进展','category':'科技科学','importance':'context'}
        b={'title':'普通经济消息','category':'全球经济','importance':'context'}
        self.assertEqual(p.rank([b,a],prefs)[0],a)
        prefs['blocked_keywords']=['经济']
        self.assertEqual(p.rank([b,a],prefs),[a])
        self.assertEqual(len(p.rank([dict(b,is_correction=True)],prefs)),1)

    def test_invalid_weight_fails_instead_of_silently_resetting(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'prefs.json'
            path.write_text(json.dumps({'topic_weights':{'全球经济':-1}}))
            with self.assertRaises(ValueError): p.load(path)

    def test_spoken_formatter_keeps_claims_and_uncertainty(self):
        self.assertEqual(n.spoken('据BBC报道，某方宣布停火，尚未证实。 https://bbc.com/a'), '某方宣布停火，尚未证实。')
        self.assertEqual(n.spoken('某方声称已控制该地，目前尚未确认。'), '某方声称已控制该地，目前尚未确认。')

    def test_article_pool_applies_interest_before_final_limit(self):
        with tempfile.TemporaryDirectory() as td:
            state=n.State(Path(td)/'news.db')
            prefs=p.load('/nonexistent-interest-test')
            prefs['topic_weights']['科技科学']=5
            items=[{'id':str(i),'title':'ordinary headline','summary':'','published':100,'score':1} for i in range(65)]
            items.append({'id':'ai','title':'AI technology','summary':'','published':99,'score':1})
            state.ingest(items)
            with patch.object(n,'current_preferences',return_value=prefs):
                self.assertEqual(state.articles(limit=2,now=101)[0]['id'],'ai')
            state.db.close()


if __name__=='__main__': unittest.main()
