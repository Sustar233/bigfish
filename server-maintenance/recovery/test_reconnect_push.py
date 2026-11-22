from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import reconnect_push as app


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=app.State(Path(self.tmp.name))
    def tearDown(self):self.tmp.cleanup()

    def test_reconnect_kicks_once_and_does_not_repeat_when_healthy(self):
        self.assertFalse(self.state.heartbeat(False))
        self.assertTrue(self.state.heartbeat(True))
        self.assertFalse(self.state.heartbeat(True))
        runner=Mock(return_value={'status':'already_handled'})
        app.work(self.state,runner)
        self.assertEqual(runner.call_count,3)
        self.assertFalse(app.State(Path(self.tmp.name)).heartbeat(True))

    def test_new_outage_creates_new_episode_underlying_topic_dedup_remains_authoritative(self):
        self.state.heartbeat(True);app.work(self.state,lambda _: {'status':'nothing_due'})
        self.state.heartbeat(False);self.assertTrue(self.state.heartbeat(True))
        self.assertEqual(self.state.pending()[0],2)

    def test_source_failure_does_not_block_other_topics_and_only_retries_failure(self):
        self.state.heartbeat(True)
        def run(topic):
            if topic=='weather':raise TimeoutError()
            return {'status':'checked'}
        app.work(self.state,run)
        with self.state.db() as db:
            statuses=dict(db.execute('SELECT topic,status FROM tasks'))
            db.execute("UPDATE tasks SET retry_at=0 WHERE status='pending'")
        self.assertEqual(statuses,{'weather':'pending','news':'done','gold':'done'})
        self.assertTrue(self.state.heartbeat(True))
        runner=Mock(return_value={'status':'sent'});app.work(self.state,runner)
        runner.assert_called_once_with('weather')

    def test_uncertain_or_stale_is_not_blindly_retried(self):
        self.state.heartbeat(True)
        for topic,result in [('weather',{'status':'uncertain'}),('news',{'status':'uncertain_no_retry'}),
                             ('gold',{'status':'skipped_stale_quote'})]:
            self.state.result(1,topic,result)
        with self.state.db() as db:self.state.put(db,'lease_until',0)
        self.assertFalse(self.state.heartbeat(True))

    def test_news_quiet_hours_remain_pending_without_replaying_weather(self):
        self.state.heartbeat(True)
        app.work(self.state,lambda topic:{'status':'quiet_hours' if topic=='news' else 'sent'})
        with self.state.db() as db:states=dict(db.execute('SELECT topic,status FROM tasks'))
        self.assertEqual(states,{'weather':'done','news':'pending','gold':'done'})

    def test_paused_timer_does_not_run_a_notification_command(self):
        with patch.object(app,'enabled',return_value=False),patch.object(app.subprocess,'run') as run:
            self.assertEqual(app.execute('weather'),{'status':'disabled'})
            run.assert_not_called()


if __name__=='__main__':unittest.main()
