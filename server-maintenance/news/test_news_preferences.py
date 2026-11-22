import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import news_preferences as p
import news_watch as n


class PreferencesTests(unittest.TestCase):
    def test_shared_guide_merges_existing_rules_and_immediate_feedback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old=root/'.private/interest_preferences.json'
            p.save(old, {'topic_weights': {'全球经济': 1.5}, 'blocked_keywords':['重复旧闻']})
            old_db=root/'no-legacy-feedback'
            p.update({'action':'set_rule','name':'科学进展','value':'优先数学突破'}, root, old_db)
            p.update({'action':'feedback','event_key':'story-a','category':'科技科学','rating':'多推这类'}, root, old_db)
            p.update({'action':'set_weight','topic':'战争安全','weight':0.35}, root, old_db)
            self.assertEqual(p.load(p.guide_path(root))['topic_weights']['科技科学'],1.25)
            current=p.update({'action':'show'}, root, old_db)
            self.assertEqual(current['topic_weights']['全球经济'],1.5)
            self.assertEqual(current['topic_weights']['战争安全'],0.35)
            self.assertEqual(current['editorial_rules']['科学进展'],'优先数学突破')
            self.assertEqual(current['blocked_keywords'],['重复旧闻'])
            self.assertEqual(current['event_feedback']['story-a'],'多推这类')

    def test_formal_proof_report_is_promoted_and_can_use_older_sources(self):
        from test_news_watch import event, NOW
        prefs=p.load('/nonexistent-interest-test')
        prefs['topic_weights'].update({'科技科学':3,'战争安全':.35})
        with tempfile.TemporaryDirectory() as td, patch.object(n,'current_preferences',return_value=prefs):
            state=n.State(Path(td)/'news.db')
            title='Two groups verify mathematician’s claim that Claude helped prove mathematics problem'
            self.assertGreaterEqual(n.priority(title),2)
            self.assertTrue(p.science_milestone(title))
            articles=[{'id':identity,'family':family,'title':title,'summary':'','published':NOW-24*3600,'score':5,
                       'publisher':family,'url':f'https://example.org/{identity}'} for identity,family in [('a','Nature'),('b','BBC')]]
            state.ingest(articles)
            self.assertEqual(len(n.breaking_pool(state,6,NOW)),2)
            war=event(ids=['a','b'])
            self.assertEqual(n.validate_events([dict(war,conflict_impact='local')],articles,'breaking'),[])
            self.assertEqual(n.validate_events([dict(war,conflict_impact='local')],articles,'digest')[0]['importance'],'context')
            self.assertEqual(len(n.validate_events([war],articles,'breaking')),1)
            state.db.close()

    def test_nature_calendar_day_is_preserved_without_guessed_event_time(self):
        from test_news_watch import NOW
        body = (b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                b'xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                b'<item><title>Riemann hypothesis verification</title><link>https://www.nature.com/articles/test</link>'
                b'<dc:date>2026-11-15</dc:date></item></rdf:RDF>')
        source = ('nature_science','Nature','https://www.nature.com/nature.rss',['nature.com'])
        article, = n.parse_feed(body, source, NOW)
        self.assertEqual(article['publication_day'],'2026-11-15')
        self.assertEqual(article['score'],5)
        self.assertNotIn('event_time',article)

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
