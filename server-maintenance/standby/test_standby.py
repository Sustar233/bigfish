from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import standby as app


class StandbyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = app.State(Path(self.tmp.name)/'state.sqlite3')

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_confirmations_enter_qq_mode_and_online_restores(self):
        self.state.health(False, 1)
        self.assertIsNone(app.mode(self.state))
        self.state.health(False, 2)
        self.assertEqual(app.mode(self.state), 'qq')
        self.assertIn('自己这个号', app.reply_if_active('你好', 'harness', self.state))
        self.state.health(True, 0)
        self.assertIsNone(app.reply_if_active('/生图 小猪', 'smallc', self.state))

    def test_model_error_blocks_every_new_feature_without_executing_any(self):
        self.state.failed('quota')
        for text in ['/生图 小猪','给我新闻','帮我画图','提醒我喝水','查询服务器','给我说说点赞','/记住 我喜欢猫','/导出 md']:
            for actor in ['smallc','harness']:
                reply = app.reply_if_active(text,actor,self.state)
                self.assertIn('不开功能', reply)
                self.assertIn('不留待办', reply)
        self.assertIn('这个QQ', app.reply_if_active('你好','smallc',self.state))

    def test_qq_recovery_does_not_claim_model_is_ready(self):
        self.state.failed('auth');self.state.health(False,2);self.state.health(True,0)
        self.assertEqual(app.mode(self.state),'model')
        self.state.clear_model()
        self.assertIsNone(app.mode(self.state))

    def test_recovery_probe_is_rate_limited_and_never_runs_while_qq_offline(self):
        self.state.put(model_out='quota',probe_after=100)
        self.assertFalse(self.state.reserve_probe(99))
        self.assertTrue(self.state.reserve_probe(100))
        self.assertFalse(self.state.reserve_probe(101))
        self.state.health(False,2)
        self.assertFalse(self.state.reserve_probe(500))

    def test_simple_chat_has_no_model_call(self):
        self.state.health(False,2)
        with patch.object(app.subprocess,'Popen',side_effect=AssertionError('no subprocess')):
            for text in ['你好','我好累','小c什么时候回来','你是谁']:
                self.assertIsInstance(app.reply_if_active(text,'harness',self.state),str)

    def test_database_failure_is_restricted_rather_than_falling_through_to_tools(self):
        broken=Mock();broken.read.side_effect=OSError('unavailable')
        self.assertIn('不开功能',app.reply_if_active('/生图 小猪','smallc',broken))

    def test_read_does_not_initialize_or_write_standby_state(self):
        self.assertEqual(self.state.read(), {})
        self.assertFalse(self.state.path.exists())
        self.state.failed('quota')
        with patch.object(self.state, 'db', side_effect=OSError('read-only service')):
            self.assertEqual(app.mode(self.state), 'model')

    def test_image_failure_uses_ordinary_error_reply_when_state_is_read_only(self):
        with patch.object(app, 'actor_for', return_value='smallc'), \
                patch.object(app.State, 'failed', side_effect=OSError('read-only service')):
            self.assertIsNone(app.image_failure_message('bot', 'owner', 'network'))

    def test_group_bypasses_models_and_uses_harness_own_account_for_qq_outage(self):
        self.state.health(False,2)
        room=Mock();room.control.get.return_value='0';room.members_safe.return_value=True
        self.assertTrue(app.group_reception(room,'event','/空间点赞',{'codex':'c','harness':'h'},'owner','group',self.state))
        self.assertEqual(room.send.call_args.args[0],'harness')
        self.assertIn('不开功能',room.send.call_args.args[1])


if __name__=='__main__':unittest.main()
