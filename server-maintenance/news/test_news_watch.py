from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import news_watch as n

CONFIG = {'breaking_daily_cap': 3, 'model_daily_budget': 10, 'quiet_start': 23, 'quiet_end': 8}
NOW = datetime(2026, 11, 16, 12, tzinfo=n.TZ).timestamp()
FEED = ('test', 'BBC', 'https://feeds.bbci.co.uk/news/world/rss.xml', ['bbc.com'])


def article(key, family='BBC'):
    return {'id': key, 'publisher': family, 'family': family, 'feed': 'test', 'url': 'https://bbc.com/news/'+key,
            'title': 'Major ceasefire agreement signed', 'summary': 'The parties announced a ceasefire.',
            'published': NOW-300, 'score': 5}


def event(key='test-ceasefire', ids=None):
    return {'event_key': key, 'title': '停火协议正式宣布', 'summary': '有关方面宣布达成停火协议。',
            'why': '可能影响地区安全局势。', 'category': '战争安全', 'importance': 'major', 'verified': True,
            'evidence_ids': ['a', 'b'] if ids is None else ids, 'event_time': '尚未确认',
            'update_of': '', 'material_update': False, 'is_correction': False}


class NewsTests(unittest.TestCase):
    def setUp(self):
        clock = patch.object(n.time, 'time', return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.temp = tempfile.TemporaryDirectory()
        for name, value in [('preference_path', Path(self.temp.name)/'prefs.json'), ('feedback_path', Path(self.temp.name)/'feedback.db')]:
            patcher = patch.object(n, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.state = n.State(Path(self.temp.name)/'state.db')
        self.articles = [article('a'), article('b', 'LeMonde')]
        self.qq = Mock()
        self.qq.ready.return_value = True
        self.qq.send.return_value = {'message_id': 42}

    def tearDown(self):
        self.state.db.close()
        self.temp.cleanup()

    def validated(self, e=None):
        return n.validate_events([event() if e is None else e], self.articles, 'breaking')[0]

    def test_rss_date_domain_and_wire_origin_are_checked(self):
        body = b'''<rss><channel><item><title>Reuters: ceasefire announced</title><link>https://bbc.com/news/a</link>
        <pubDate>Mon, 16 Nov 2026 03:00:00 GMT</pubDate><description>Public report</description></item></channel></rss>'''
        rows = n.parse_feed(body, FEED, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['family'], 'Reuters')
        self.assertEqual(n.parse_feed(body.replace(b'https://bbc.com/news/a', b'http://127.0.0.1/'), FEED, NOW), [])
        self.assertEqual(n.parse_feed(body.replace(b'16 Nov 2026', b'19 Nov 2026'), FEED, NOW), [])
        with self.assertRaises(ValueError):
            n.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "x">]><rss/>', FEED, NOW)

    def test_redirect_to_private_or_unknown_hosts_is_blocked_before_following(self):
        handler = n.FeedRedirect()
        for url in ['http://127.0.0.1/', 'https://example.com/news', 'http://169.254.169.254/']:
            with self.assertRaises(ValueError):
                handler.redirect_request(None, None, 302, '', {}, url)

    def test_two_independent_sources_required_and_unknown_evidence_rejected(self):
        self.assertEqual(len(n.validate_events([event()], self.articles, 'breaking')), 1)
        same_wire = [article('a', 'Reuters'), article('b', 'Reuters')]
        self.assertEqual(n.validate_events([event()], same_wire, 'breaking'), [])
        self.assertEqual(n.validate_events([event(ids=['invented'])], self.articles, 'breaking'), [])
        one = event(ids=['a'])
        self.assertEqual(n.validate_events([one], self.articles, 'breaking'), [])
        self.assertFalse(n.validate_events([one], self.articles, 'digest')[0]['verified'])

    def test_same_key_or_shared_evidence_does_not_duplicate_after_restart(self):
        e = self.validated()
        self.assertTrue(n.add_event(self.state, e, NOW))
        self.assertFalse(n.add_event(self.state, dict(e, event_key='different-key'), NOW+60))
        self.state.db.close()
        self.state = n.State(Path(self.temp.name)/'state.db')
        self.assertFalse(n.add_event(self.state, e, NOW+120))
        self.assertEqual(self.state.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)

    def test_update_requires_material_change_and_six_hour_gap(self):
        e = self.validated()
        n.add_event(self.state, e, NOW)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW), 'sent_1')
        update = dict(e, summary='协议正式生效，各方开始执行。', material_update=True, update_of=e['event_key'])
        self.assertTrue(n.add_event(self.state, update, NOW+300))
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+600), 'nothing_due')
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+6*3600+1), 'sent_1')
        self.assertFalse(n.add_event(self.state, dict(update, event_key='unknown-event', update_of='missing', evidence_ids=['z']), NOW))

    def test_unsent_old_version_is_replaced_by_latest_material_update(self):
        e = self.validated()
        n.add_event(self.state, e, NOW)
        update = dict(e, summary='协议正式生效，各方开始执行。', material_update=True, update_of=e['event_key'])
        self.assertTrue(n.add_event(self.state, update, NOW+300))
        self.assertEqual(self.state.db.execute("SELECT count(*) FROM outbox WHERE status='pending'").fetchone()[0], 1)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+300), 'sent_1')

    def test_quiet_hours_hold_and_morning_bundles_limited_events(self):
        night = datetime(2026, 11, 16, 23, 30, tzinfo=n.TZ).timestamp()
        for i in range(4):
            self.state.queue('breaking:'+str(i), 'breaking', str(i), 'News '+str(i), night)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, night), 'quiet_hours')
        self.qq.send.assert_not_called()
        morning = datetime(2026, 11, 17, 8, tzinfo=n.TZ).timestamp()
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, morning), 'sent_3')
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, morning+900), 'nothing_due')
        self.assertEqual(self.qq.send.call_count, 1)

    def test_offline_pending_and_expiry_not_replayed(self):
        self.state.queue('one', 'breaking', 'one', 'News', NOW)
        self.qq.ready.return_value = False
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW), 'qq_offline_pending')
        self.qq.send.assert_not_called()
        self.qq.ready.return_value = True
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+19*3600), 'quiet_hours')
        self.assertEqual(self.state.db.execute('SELECT status FROM outbox').fetchone()[0], 'expired')

    def test_uncertain_send_and_process_crash_are_never_automatically_repeated(self):
        self.state.queue('one', 'breaking', 'one', 'News', NOW)
        self.qq.send.side_effect = TimeoutError()
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW), 'uncertain_no_retry')
        self.state.db.close()
        self.state = n.State(Path(self.temp.name)/'state.db')
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+900), 'nothing_due')
        self.state.queue('two', 'breaking', 'two', 'News', NOW)
        with self.state.db:
            self.state.db.execute("UPDATE outbox SET status='sending' WHERE dedup='two'")
        self.state.db.close()
        self.state = n.State(Path(self.temp.name)/'state.db')
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+1800), 'nothing_due')

    def test_model_budget_reserves_two_digest_attempts_and_persists(self):
        config = dict(CONFIG, model_daily_budget=4)
        for _ in range(2):
            self.assertIsNotNone(self.state.reserve_model('breaking', config, NOW))
        self.assertIsNone(self.state.reserve_model('breaking', config, NOW))
        for _ in range(2):
            self.assertIsNotNone(self.state.reserve_model('digest', config, NOW))
        self.assertIsNone(self.state.reserve_model('digest', config, NOW))

    def test_digest_idempotent_and_does_not_pad_empty_news(self):
        self.assertFalse(n.make_digest(self.state, [], NOW))
        events = n.validate_events([event()], self.articles, 'digest')
        self.assertTrue(n.make_digest(self.state, events, NOW))
        self.assertFalse(n.make_digest(self.state, events, NOW))
        body = self.state.db.execute('SELECT body FROM outbox').fetchone()[0]
        self.assertNotIn('https://', body)
        self.assertNotIn('媒体报道', body)
        stored = json.loads(self.state.db.execute('SELECT payload FROM digest_items').fetchone()[0])
        self.assertEqual(stored['sources'][0]['url'], 'https://bbc.com/news/a')

    def test_usgs_major_event_uses_real_authority_and_no_casualty_invention(self):
        body = json.dumps({'features': [{'id': 'us123', 'properties': {
            'mag': 7.1, 'time': (NOW-300)*1000, 'place': 'test region',
            'url': 'https://earthquake.usgs.gov/earthquakes/eventpage/us123', 'alert': 'yellow'}}]}).encode()
        events = n.parse_quakes(body, NOW)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['authoritative'])
        self.assertIn('不推断伤亡', events[0]['summary'])
        self.assertNotIn('[N', n.format_breaking(events[0]))
        self.assertIn('不推断伤亡', n.format_breaking(events[0]))

    def test_sent_news_hides_id_keeps_backend_sources_and_correction_meaning(self):
        e = self.validated()
        n.add_event(self.state, e, NOW)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW), 'sent_1')
        text = self.qq.send.call_args.args[0]
        self.assertNotIn('[N', text)
        self.assertNotIn(e['title'], text)
        stored = json.loads(self.state.db.execute('SELECT payload FROM events').fetchone()[0])
        self.assertEqual(stored['event_key'], e['event_key'])
        self.assertEqual(len(stored['sources']), 2)
        self.assertIn('更正', n.format_breaking(dict(e, is_correction=True)))
        self.assertIn('新进展', n.format_breaking(dict(e, update_of=e['event_key'])))

    def test_old_queued_header_is_hidden_without_changing_delivery_bookkeeping(self):
        old = '小c来报个信｜重大新闻 [N36db0acf]\n会谈\n双方今天在深圳会谈。'
        self.state.queue('legacy', 'breaking', 'legacy-event', old, NOW)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW), 'sent_1')
        text = self.qq.send.call_args.args[0]
        self.assertNotIn('[N36db0acf]', text)
        self.assertIn('双方今天在深圳会谈。', text)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, NOW+1), 'nothing_due')

    def test_three_queued_news_share_date_without_repeated_greeting(self):
        queued = datetime(2026, 11, 18, 23, tzinfo=n.TZ).timestamp()
        sent = datetime(2026, 11, 19, 10, tzinfo=n.TZ).timestamp()
        summaries = [
            '11月18日，以军越过停火协议划出的“黄线”，在加沙中部展开地面行动。一些巴勒斯坦居民逃离难民营，以军称行动是为了拆除一条地道。',
            '11月18日，科威特和巴林都称遭到伊朗袭击，科威特称已击退来袭。前一天，美军空袭了霍尔木兹海峡的伊朗格什姆岛。',
            '11月18日，美国国防部长赫格塞思在委内瑞拉首都加拉加斯访问时宣布，两国将恢复军事合作，协议包括联合训练和情报共享。',
        ]
        for number, summary in enumerate(summaries):
            self.state.queue('old-'+str(number), 'breaking', str(number),
                             '有条新消息，跟你说一声。\n'+summary, queued)
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, sent), 'sent_3')
        body = self.qq.send.call_args.args[0]
        self.assertNotIn('有条新消息', body)
        self.assertNotIn('11月18日', body)
        self.assertEqual(body.count('昨天'), 1)
        self.assertEqual(body, '昨天这几件事，跟你说说：\n\n'+'\n\n'.join(
            summary.removeprefix('11月18日，') for summary in summaries))
        self.assertEqual(self.state.db.execute("SELECT count(*) FROM outbox WHERE status='sent'").fetchone()[0], 3)
        self.assertEqual(self.state.db.execute('SELECT body FROM outbox ORDER BY id').fetchone()[0],
                         '有条新消息，跟你说一声。\n'+summaries[0])
        self.assertEqual(n.flush(self.state, CONFIG, self.qq, sent+1), 'nothing_due')

    def test_news_dates_use_beijing_delivery_day_and_keep_queued_relative_anchor(self):
        queued = datetime(2026, 11, 18, 23, 59, tzinfo=n.TZ).timestamp()
        sent = datetime(2026, 11, 19, 0, 1, tzinfo=n.TZ).timestamp()
        body = '今天，某方声称已控制该地，尚未确认。昨天双方谈过一次，前一天另有会谈。'
        self.assertEqual(n.outward_news_text(body, sent, queued),
                         '昨天，某方声称已控制该地，尚未确认。前天双方谈过一次，前一天另有会谈。')
        self.assertEqual(n.news_dates('11月19日宣布，2026年11月18日曾谈判。', sent, queued),
                         '今天宣布，昨天曾谈判。')

    def test_new_year_historical_invalid_and_recurring_dates_are_not_misdated(self):
        queued = datetime(2026, 12, 31, 23, tzinfo=n.TZ).timestamp()
        sent = datetime(2027, 1, 1, 8, tzinfo=n.TZ).timestamp()
        self.assertEqual(n.news_dates('12月31日谈判，1月1日签署。', sent, queued),
                         '昨天谈判，今天签署。')
        unchanged = '2025年1月1日、去年1月1日、明年1月1日、每年1月1日、2月30日、1月1日至3日。'
        self.assertEqual(n.news_dates(unchanged, sent, queued), unchanged)

    def test_plain_news_has_no_template_and_mixed_dates_keep_their_context(self):
        sent = datetime(2026, 11, 19, 12, tzinfo=n.TZ).timestamp()
        e = event()
        e['summary'] = '双方要恢复合作，但细节还没确认。'
        self.assertEqual(n.format_breaking(e), e['summary'])
        rows = [(1, 'breaking', '11月18日，某方称已停火。', sent),
                (2, 'breaking', '11月19日，另一方称谈判仍在继续。', sent)]
        self.assertEqual(n.news_batch(rows, sent), '昨天，某方称已停火。\n\n今天，另一方称谈判仍在继续。')
        correction = n.format_breaking(dict(e, is_correction=True))
        self.assertTrue(n.news_batch([(3, 'correction', correction, sent)], sent).startswith('刚才那条有个地方得更正一下。'))

    def test_dry_run_collects_without_model_or_sending(self):
        result = ('test', self.articles, {'ok': True})
        with patch.object(n, 'collect_feed', return_value=result), patch.object(n, 'fetch', return_value=b'{"features":[]}'), \
             patch.object(n, 'call_editor') as editor, patch.object(n, 'flush') as flush:
            n.run(self.state, CONFIG, 'tick', dry_run=True)
        editor.assert_not_called()
        flush.assert_not_called()

    def test_overnight_collects_without_spending_model_budget(self):
        night = datetime(2026, 11, 16, 23, 30, tzinfo=n.TZ).timestamp()
        result = ('test', self.articles, {'ok': True})
        with patch.object(n.time, 'time', return_value=night), patch.object(n, 'collect_feed', return_value=result), \
             patch.object(n, 'fetch', return_value=b'{"features":[]}'), patch.object(n, 'call_editor') as editor:
            output = n.run(self.state, CONFIG, 'tick')
        self.assertEqual(output['status'], 'collected_quiet_hours')
        editor.assert_not_called()
        self.assertEqual(self.state.db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)

    def test_successful_digest_retry_clears_previous_failure(self):
        with self.state.db:
            self.state.put('last_digest_error', 'ValueError')
        result = ('test', self.articles, {'ok': True})
        with patch.object(n, 'collect_feed', return_value=result), \
             patch.object(n, 'fetch', return_value=b'{"features":[]}'), \
             patch.object(n, 'call_editor', return_value=n.validate_events([event()], self.articles, 'digest')), \
             patch.object(n, 'flush', return_value='nothing_due'):
            n.run(self.state, CONFIG, 'digest')
        self.assertIsNone(self.state.get('last_digest_error'))
        self.assertEqual(self.state.get('last_digest_result'), 'queued')


if __name__ == '__main__':
    unittest.main()
