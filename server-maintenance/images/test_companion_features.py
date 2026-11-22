import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server-deploy/qq-codex'))
import image_service
from companion_care import care_turn, deliver_due, LOCAL
from heart_memory import turn
from image_commands import parse
from group_pictures import Pictures


class Features(unittest.TestCase):
    def test_second_image_two_versions_and_isolation(self):
        bot=next(iter(image_service.ACCOUNTS))
        with tempfile.TemporaryDirectory() as tmp:
            gen=Mock(return_value=b'\x89PNG\r\n\x1a\n'+bytes(200))
            service=image_service.Service(Path(tmp)/'alice',gen)
            service.ready=Mock()
            service.request=Mock(side_effect=[{'message_id':i} for i in range(5)])
            service.submit(bot,'draw','画三张小猫')
            for _ in range(3): self.assertTrue(service.run_one())
            with service.db() as db:
                second=Path(db.execute("select image_path from jobs where message_id='1'").fetchone()[0])
            prompt='第二张，背景换成夜景，再给我两个版本'
            kind,_=parse(prompt)
            service.submit(bot,'revise',prompt,kind)
            for _ in range(2):
                self.assertTrue(service.run_one())
                self.assertEqual(gen.call_args.kwargs['inputs'],[second])
            self.assertFalse(service.run_one())
            other=image_service.Service(Path(tmp)/'bob',gen)
            with self.assertRaisesRegex(ValueError,'missing_image'):
                other.submit(bot,'guess',prompt,kind,message_id='1')
            service.submit(bot,'quote','按这张改',kind,message_id='1')
            with service.db() as db:
                db.execute('update jobs set updated=0')
            with self.assertRaisesRegex(ValueError,'missing_image'):
                service.submit(bot,'expired',prompt,kind,message_id='1')

    def test_memory_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'memory'
            turn(p,'那次告别我很难过')
            self.assertIn('操作结果',turn(p,'上次我难过，其实是因为告别')[0])
            turn(p,'这件事以后别再提了')
            self.assertEqual(turn(p,'今天有点难过'),[])
            turn(p,'把这段忘了')
            with closing(sqlite3.connect(p)) as db:
                self.assertEqual(db.execute('select count(*) from memories').fetchone()[0],0)

    def test_opt_in_and_quiet_hours_and_cancellation(self):
        now=datetime(2026,11,22,10,tzinfo=LOCAL)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'care'
            with closing(sqlite3.connect(p)) as db,db:
                care_turn(db,'明天我上台，有点紧张',now)
                self.assertIsNone(db.execute('select due from care').fetchone()[0])
                care_turn(db,'可以主动关心我',now)
                care_turn(db,'免打扰 20点到9点',now)
                care_turn(db,'明天我上台，有点紧张',now)
            send=Mock()
            deliver_due(p,send,now+timedelta(days=1,hours=11))
            send.assert_not_called()
            deliver_due(p,send,now+timedelta(days=2))
            deliver_due(p,send,now+timedelta(days=2))
            send.assert_called_once()
            with closing(sqlite3.connect(p)) as db,db:
                care_turn(db,'明天我上台，有点紧张',now)
                care_turn(db,'上台很顺利',now)
            deliver_due(p,send,now+timedelta(days=2))
            send.assert_called_once()

    def test_group_private_media_ignored(self):
        pictures=Pictures()
        event=dict(post_type='message',message_type='private',group_id='room',user_id='owner',
                   self_id='bot',message_id=123,message=[{'type':'image','data':{'file':'a'}}])
        pictures.observe(event,'room',{'owner'},'bot')
        self.assertFalse(pictures.items)
        pictures.observe(dict(event,message_type='group'),'room',{'owner'},'bot')
        self.assertEqual(len(pictures.items),1)
