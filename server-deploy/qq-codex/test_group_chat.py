import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import group_chat as g


def event(**updates):
    e={'post_type':'message','message_type':'group','group_id':628128804,
       'user_id':17162047,'self_id':1103828665,'message_id':42,'time':1700000000,
       'message':[{'type':'text','data':{'text':'大家晚上好'}}]}
    e.update(updates)
    return e


class GroupTests(unittest.TestCase):
    def test_only_owner_in_this_group_can_trigger(self):
        self.assertIsNotNone(g.parse_group(event()))
        for change in ({'user_id':1103828665},{'user_id':2223525305},{'user_id':9},
                       {'group_id':9},{'message_type':'private'},{'post_type':'message_sent'},
                       {'self_id':9},{'time':None}):
            self.assertIsNone(g.parse_group(event(**change)))

    def test_two_feeds_deduplicate_even_if_message_ids_differ(self):
        with tempfile.TemporaryDirectory() as td:
            room=g.Room(td)
            try:
                self.assertTrue(room.admit(event()))
                self.assertFalse(room.admit(event(self_id=2223525305,message_id=88)))
                self.assertEqual(len(room.pending),1)
            finally:room.close()

    def test_natural_replies_do_not_require_mentions_and_are_bounded(self):
        self.assertEqual(g.participants('晚上好',[],1),['codex'])
        self.assertEqual(g.participants('晚上好',[],2),['harness'])
        self.assertEqual(len(g.participants('晚上好',[],3)),2)
        self.assertEqual(g.participants('你们觉得呢',[],4),['harness','codex'])
        self.assertEqual(g.participants('好困', ['2223525305'],1),['harness'])

    def test_call_budget_survives_restart_and_no_duplicate_bot_turn(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'control.db';c=g.Control(path)
            self.assertIsNotNone(c.reserve('r','codex',1000))
            self.assertIsNone(c.reserve('r','codex',1000))
            self.assertIsNotNone(c.reserve('r','harness',1000))
            self.assertIsNone(c.reserve('r','third',1000))
            for n in range(4):self.assertIsNotNone(c.reserve(str(n),'codex',1000))
            c.close();c=g.Control(path)
            try:self.assertIsNone(c.reserve('new','codex',1001))
            finally:c.close()

    def test_hourly_and_rolling_daily_caps(self):
        with tempfile.TemporaryDirectory() as td:
            c=g.Control(Path(td)/'control.db')
            try:
                with c.db:
                    c.db.executemany('insert into calls(at,round,bot,status) values(?,?,?,?)',[(1000,str(i),'codex','failed') for i in range(60)])
                self.assertIsNone(c.reserve('blocked','harness',2000))
                with c.db:
                    c.db.executemany('insert into calls(at,round,bot,status) values(?,?,?,?)',[(1000,'d'+str(i),'codex','sent') for i in range(240)])
                self.assertIsNone(c.reserve('dayblocked','harness',10000))
                self.assertIsNotNone(c.reserve('nextday','harness',90000))
            finally:c.close()

    def test_pause_blocks_generation_and_resume_does_not_replay(self):
        with tempfile.TemporaryDirectory() as td:
            room=g.Room(td)
            try:
                room.admit(event())
                room.admit(event(message_id=43,time=1700000001,message=[{'type':'text','data':{'text':'暂停群聊'}}]))
                self.assertEqual(room.pending,[])
                self.assertEqual(room.control.get('paused'),'1')
                self.assertIsNone(room.control.reserve('r','codex'))
                room.admit(event(message_id=44,time=1700000002,message=[{'type':'text','data':{'text':'继续群聊'}}]))
                self.assertEqual(room.control.get('paused'),'0')
                self.assertEqual(room.pending,[])
            finally:room.close()

    def test_bot_messages_cannot_open_more_work_after_two_replies(self):
        with tempfile.TemporaryDirectory() as td:
            endpoint=Mock();endpoint.request.return_value={'online':True}
            room=g.Room(td,endpoints={'codex':endpoint,'harness':endpoint})
            try:
                room.members_safe=Mock(return_value=True)
                room.generate=Mock(return_value='收到。');room.send=Mock()
                room.process([('owner/test','你们互相聊一句',[])])
                self.assertEqual(room.generate.call_count,2)
                self.assertEqual(room.send.call_count,2)
                for bot in (1103828665,2223525305):self.assertFalse(room.admit(event(user_id=bot)))
                self.assertEqual(room.pending,[])
            finally:room.close()

    def test_pause_then_resume_during_generation_cancels_old_reply(self):
        with tempfile.TemporaryDirectory() as td:
            endpoint=Mock();endpoint.request.return_value={'online':True}
            room=g.Room(td,endpoints={'codex':endpoint,'harness':endpoint})
            try:
                room.members_safe=Mock(return_value=True)
                def reply(*a,**kw):
                    room.control.set('epoch',1)
                    return 'obsolete'
                room.generate=Mock(side_effect=reply);room.send=Mock()
                room.process([('owner/test','你们聊聊',[])])
                room.send.assert_not_called()
                self.assertEqual(room.generate.call_count,1)
            finally:room.close()

    def test_group_destination_cannot_be_changed_by_model(self):
        with tempfile.TemporaryDirectory() as td:
            endpoint=Mock();room=g.Room(td,endpoints={'codex':endpoint})
            try:
                room.members_safe=Mock(return_value=True)
                room.send('codex','[CQ:at,qq=42]')
                action,payload=endpoint.request.call_args.args
                self.assertEqual(action,'send_group_msg')
                self.assertEqual(payload['group_id'],628128804)
                self.assertEqual(payload['message'][0]['type'],'text')
            finally:room.close()

    def test_private_retrieval_not_used_when_room_has_extra_member(self):
        with tempfile.TemporaryDirectory() as td:
            endpoint=Mock();endpoint.request.return_value=[{'user_id':v} for v in (17162047,1103828665,2223525305,42)]
            room=g.Room(td,endpoints={'codex':endpoint})
            try:
                room.generate=Mock();room.send=Mock()
                room.process([('test','大家好',[])])
                room.generate.assert_not_called()
                room.send.assert_not_called()
            finally:room.close()

    def test_new_human_message_preempts_second_bot(self):
        with tempfile.TemporaryDirectory() as td:
            endpoint=Mock();endpoint.request.return_value={'online':True}
            room=g.Room(td,endpoints={'codex':endpoint,'harness':endpoint})
            try:
                room.members_safe=Mock(return_value=True)
                room.generate=Mock(return_value='ok')
                room.send=Mock(side_effect=lambda *a:room.pending.append(('new','新话题',[])))
                room.process([('owner/test','你们聊聊',[])])
                self.assertEqual(room.generate.call_count,1)
                self.assertEqual(len(room.pending),1)
            finally:room.close()

    def test_private_retrieval_uses_actual_topic_and_only_own_account(self):
        with tempfile.TemporaryDirectory() as td:
            roots={k:Path(td)/k for k in g.ACCOUNTS}
            for label,content in [('codex','咖啡店约在明天见'),('harness','咖啡店约在下周见')]:
                d=g.Data(roots[label],g.ACCOUNTS[label]);d.record('one','user',content);d.close()
            room=g.Room(Path(td)/'room')
            try:
                with patch.dict(g.PRIVATE,roots),patch.object(g,'model_reply',return_value='ok') as model:
                    room.generate('codex',[],'只接一句',query='咖啡店')
                    memory=model.call_args.kwargs['memory']
                    self.assertIn('明天',memory)
                    self.assertNotIn('下周',memory)
                    self.assertEqual(model.call_args.kwargs['channel'],'group')
            finally:room.close()

    def test_group_cannot_execute_private_export_commands(self):
        with tempfile.TemporaryDirectory() as td:
            room=g.Room(td)
            try:
                room.notice=Mock()
                room.admit(event(message=[{'type':'text','data':{'text':'/导出 Harness md'}}]))
                self.assertEqual(room.pending,[])
                self.assertIn('私聊',room.notice.call_args.args[0])
                self.assertFalse((Path(td)/'records/exports').exists())
            finally:room.close()


if __name__=='__main__':unittest.main()
