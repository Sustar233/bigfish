import inspect
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import standby
import bridge
import group_chat as group


class StandbyRoutes(unittest.TestCase):
    @unittest.skipUnless('standby_reply' in inspect.getsource(bridge.Bridge.work),'requires deployed standby bridge')
    def test_smallc_worker_blocks_commands_media_and_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=standby.State(Path(tmp)/'state.sqlite3');state.failed('quota')
            for text in ['/生图 小猪','/提醒 18点吃饭','/空间点赞','你好']:
                b=object.__new__(bridge.Bridge);b.stop=threading.Event();b.tasks=queue.Queue();b.tasks.put(('fixture',text))
                b.media_inputs={};b.config={'owner_qq':'1000000001','bot_qq':'1000000002'};b.store=Mock()
                b.media=Mock();b.media.deliver.return_value=[];b.media.command.side_effect=AssertionError('media feature used')
                b.command=Mock(side_effect=AssertionError('task command used'));b.verify_account=Mock()
                b.send=Mock(side_effect=lambda _:b.stop.set())
                def strict_log(event, **kwargs):
                    if event == 'reply_failed':
                        raise
                with patch.object(standby,'State',return_value=state),patch.object(bridge,'model_reply',side_effect=AssertionError('chat model used')),patch.object(bridge,'log',side_effect=strict_log):
                    b.work()
                b.command.assert_not_called();b.media.command.assert_not_called();b.store.append_turn.assert_not_called()
                b.send.assert_called_once()
                self.assertIn('大肥鱼',b.send.call_args.args[0])

    @unittest.skipUnless('group_reception' in inspect.getsource(group.Room.admit),'requires deployed standby room')
    def test_group_event_is_intercepted_once_before_qzone_or_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=standby.State(Path(tmp)/'state.sqlite3');state.health(False,2)
            room=group.Room(Path(tmp)/'room');room.members_safe=Mock(return_value=True);room.send=Mock();room.generate=Mock()
            event={'post_type':'message','message_type':'group','group_id':group.GROUP,'user_id':group.OWNER,
                'self_id':group.ACCOUNTS['codex'],'message_id':1,'time':1700000000,
                'message':[{'type':'text','data':{'text':'你们给我最新一条说说点赞'}}]}
            try:
                with patch.object(standby,'State',return_value=state):
                    self.assertTrue(room.admit(event))
                    self.assertFalse(room.admit({**event,'self_id':group.ACCOUNTS['harness'],'message_id':2}))
                room.send.assert_called_once();self.assertEqual(room.send.call_args.args[0],'harness')
                self.assertIn('不开功能',room.send.call_args.args[1]);self.assertEqual(room.pending,[])
                room.generate.assert_not_called()
            finally:room.close()


if __name__=='__main__':unittest.main()
