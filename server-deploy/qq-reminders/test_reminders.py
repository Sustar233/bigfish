from datetime import datetime
import tempfile
from pathlib import Path
import unittest
from reminders import Store, TZ, authorize, next_time
from reminder_client import parse


class Transport:
    def __init__(self, online=True, uncertain=False):
        self.available=online;self.uncertain=uncertain;self.messages=[]
    def online(self,bot):return self.available
    def send(self,bot,message):
        self.messages.append((bot,message))
        if self.uncertain:raise TimeoutError('uncertain')
        return 123


class RemindersTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3')
        self.now=datetime(2026,11,21,10,0,tzinfo=TZ).timestamp()
        self.base=dict(owner='1000000001',channel='private',origin='smallc-private-1000000001',bot='smallc')
    def tearDown(self):self.tmp.cleanup()
    def request(self,**kwargs):return dict(self.base,**kwargs)
    def create(self,**kwargs):
        r=dict(action='create',request_key='request',message='喝水',repeat='none',delay_seconds=10)
        r.update(kwargs);return self.store.dispatch(self.request(**r),self.now)
    def test_owner_and_channel_guards(self):
        for update in [dict(owner='999'),dict(channel='group'),dict(origin='onebot-group-1000000001'),dict(bot='harness'),dict(origin='smallc-private-10000000010')]:
            with self.assertRaises(PermissionError):authorize(dict(self.base,**update))
    def test_persistence_and_idempotency(self):
        one=self.create();two=self.create(message='不同重试')
        self.assertEqual(one['id'],two['id'])
        fresh=Store(self.store.database)
        self.assertEqual(len(fresh.dispatch(self.request(action='list'),self.now)),1)
    def test_exact_once_tick(self):
        self.create();transport=Transport()
        self.store.tick(transport,self.now+11);self.store.tick(transport,self.now+12)
        self.assertEqual(transport.messages,[('smallc','喝水')])
    def test_offline_pending_then_recovery(self):
        self.create();t=Transport(False);self.store.tick(t,self.now+11)
        self.assertFalse(t.messages)
        t.available=True;self.store.tick(t,self.now+80)
        self.assertEqual(len(t.messages),1)
    def test_unknown_send_no_retry(self):
        self.create();t=Transport(uncertain=True)
        self.store.tick(t,self.now+11);self.store.tick(t,self.now+100)
        self.assertEqual(len(t.messages),1)
        self.assertEqual(self.store.dispatch(self.request(action='list'),self.now)[0]['state'],'needs_review')
    def test_restart_inflight_no_resend(self):
        one=self.create()
        with self.store.db() as db:
            db.execute("UPDATE reminders SET state='sending' WHERE id=?",(one['id'],))
            db.execute("INSERT INTO deliveries VALUES(?,?,'attempted',NULL,NULL)",(one['id'],one['next_fire']))
        self.store.recover(self.now+11);t=Transport();self.store.tick(t,self.now+12)
        self.assertFalse(t.messages)
        self.assertEqual(self.store.dispatch(self.request(action='list'),self.now)[0]['state'],'needs_review')
    def test_cancel_and_bot_isolation(self):
        one=self.create()
        with self.assertRaises(ValueError):
            self.store.dispatch(dict(self.request(action='cancel',reminder_id=one['id']),bot='harness',origin='onebot-private-1000000001'),self.now)
        self.store.dispatch(self.request(action='cancel',reminder_id='latest'),self.now)
        t=Transport();self.store.tick(t,self.now+11);self.assertFalse(t.messages)
    def test_update(self):
        one=self.create()
        self.store.dispatch(self.request(action='update',reminder_id=one['id'],repeat='daily',at='11:00',message='午饭'),self.now)
        t=Transport();self.store.tick(t,self.now+11);self.assertFalse(t.messages)
        self.store.tick(t,self.now+3601);self.assertEqual(t.messages,[('smallc','午饭')])
    def test_expired_oneoff_not_flooded(self):
        self.create();t=Transport();self.store.tick(t,self.now+86420);self.assertFalse(t.messages)
    def test_overdue_daily_coalesced(self):
        self.create(repeat='daily',at='10:01');t=Transport()
        self.store.tick(t,self.now+7200);self.store.tick(t,self.now+7201)
        self.assertEqual(len(t.messages),1)
        item=self.store.dispatch(self.request(action='list'),self.now)[0]
        self.assertGreater(item['next_fire'],self.now+7200)
    def test_timezone_weekday(self):
        self.create(repeat='weekdays',at='08:00')
        item=self.store.dispatch(self.request(action='list'),self.now)[0]
        self.assertTrue(item['next_fire_beijing'].startswith('2026-11-23T08:00'))
    def test_natural_language(self):
        now=datetime.fromtimestamp(self.now,TZ)
        cases=[('半小时后提醒我喝水','none','喝水'),('明天早上八点提醒我开会','none','开会'),('每天晚上八点提醒我看书','daily','看书'),('工作日9:30给我发一句早安','weekdays','早安'),('每周五下午三点提醒我整理资料','weekly','整理资料'),('提醒我明天8点喝水','none','喝水'),('每隔30分钟提醒我起来走走','interval','起来走走')]
        for text,repeat,message in cases:
            with self.subTest(text=text):
                r=parse(text,now);self.assertEqual(r['repeat'],repeat);self.assertEqual(r['message'],message)
        self.assertIsNone(parse('今天有点困',now))
        self.assertEqual(parse('取消刚才的提醒',now)['reminder_id'],'latest')


if __name__=='__main__':unittest.main()
