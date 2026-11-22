from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock
from weather_catchup import catch_up
from news_recovery import flush_recovery

NOW=datetime(2026,11,22,10,0,tzinfo=timezone(timedelta(hours=8)))


class WeatherState:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE deliveries(day TEXT PRIMARY KEY,status TEXT)')
        self.db.execute('CREATE TABLE forecasts(day TEXT PRIMARY KEY,updated TEXT,body TEXT)')
    def get(self,day):
        row=self.db.execute('SELECT status FROM deliveries WHERE day=?',(day,)).fetchone()
        return row[0] if row else None
    def put(self,day,status,now,**kwargs):
        with self.db:self.db.execute('INSERT OR REPLACE INTO deliveries VALUES(?,?)',(day,status))


class CatchupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=WeatherState(Path(self.tmp.name)/'weather.db')
        self.collect=Mock(return_value='新预报');self.qq=Mock();self.factory=Mock(return_value=self.qq)
        def send(state,now,text,qq):
            qq.send(text);state.put(now.date().isoformat(),'sent',now);return 'sent'
        self.send=Mock(side_effect=send)
    def tearDown(self):self.state.db.close();self.tmp.cleanup()

    def test_expired_today_is_delivered_once_with_original_forecast_time(self):
        self.state.put('2026-11-22','expired',NOW)
        with self.state.db:self.state.db.execute('INSERT INTO forecasts VALUES(?,?,?)',('2026-11-22',NOW.replace(hour=6).isoformat(),'当天预报'))
        self.assertEqual(catch_up(self.state,NOW,self.collect,self.factory,self.send)['status'],'sent')
        text=self.qq.send.call_args.args[0];self.assertIn('06:00',text);self.assertIn('上午通勤时段已过',text)
        self.assertEqual(catch_up(self.state,NOW,self.collect,self.factory,self.send)['status'],'already_handled')
        self.send.assert_called_once();self.collect.assert_not_called()

    def test_yesterday_is_not_sent_as_today(self):
        with self.state.db:self.state.db.execute('INSERT INTO forecasts VALUES(?,?,?)',('2026-11-21',NOW.isoformat(),'昨天旧预报'))
        catch_up(self.state,NOW,self.collect,self.factory,self.send)
        self.collect.assert_called_once_with(NOW)
        self.assertNotIn('昨天旧预报',self.qq.send.call_args.args[0])

    def test_sent_uncertain_and_inflight_do_not_resend(self):
        for status in ['sent','sending','uncertain']:
            self.state.put('2026-11-22',status,NOW)
            self.assertEqual(catch_up(self.state,NOW,self.collect,self.factory,self.send)['status'],'already_handled')
        self.factory.assert_not_called();self.collect.assert_not_called()

    def test_not_due_or_source_failure_cannot_claim_delivery(self):
        self.assertEqual(catch_up(self.state,NOW.replace(hour=2),self.collect,self.factory,self.send)['status'],'not_due')
        self.collect.side_effect=TimeoutError()
        self.assertEqual(catch_up(self.state,NOW,self.collect,self.factory,self.send)['status'],'source_unavailable')
        self.factory.assert_not_called()

    def test_news_digest_has_priority_and_does_not_collect_or_generate(self):
        flush=Mock(side_effect=['sent_1','nothing_due'])
        result=flush_recovery('state','config',flush)
        self.assertEqual(result['status'],'sent')
        self.assertEqual([c.kwargs['kind'] for c in flush.call_args_list],['digest',None])

    def test_news_quiet_or_uncertain_does_not_repeat(self):
        for result in ['quiet_hours','uncertain_no_retry','qq_offline_pending']:
            flush=Mock(return_value=result)
            self.assertEqual(flush_recovery('state','config',flush)['status'],result)
            flush.assert_called_once()


if __name__=='__main__':unittest.main()
