import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from chat_delivery import bubbles
from heart_memory import turn


class HeartMemoryTests(unittest.TestCase):
    def test_private_recall_and_forgetting(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = (Path(folder)/name for name in ('a.sqlite3','b.sqlite3'))
            phrase = '我很喜欢你在我难过的时候陪着我'
            turn(a,phrase)
            turn(a,phrase)
            self.assertEqual([row['words'] for row in turn(a,'今天有点低落')],[phrase])
            self.assertEqual(turn(b,'今天有点低落'),[])
            turn(a,'忘掉关于难过的记忆')
            self.assertEqual(turn(a,'今天有点低落'),[])

    def test_operational_content_never_enters_index(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'notes'
            turn(path,'今天过得还行')
            for line in ['帮我画图，我很喜欢陪伴感','调试服务器时我觉得很安心',
                         '我难过的时候，加班后请生成三张照片','我最喜欢在会议上有人听我说']:
                turn(path,line)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('select count(*) from memories').fetchone()[0],0)

    def test_two_bubbles_keep_content(self):
        text='我记得你那天说的话。'*20
        pieces=bubbles(text)
        self.assertEqual(len(pieces),2)
        self.assertEqual(''.join(pieces),text)
        self.assertEqual(bubbles('我在。'),['我在。'])
