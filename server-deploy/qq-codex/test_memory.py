import json
from pathlib import Path
import tempfile
import unittest
from qq_data import Data, approved_persona
from qq_maintenance import session_messages
import bridge
from unittest.mock import patch


class MemoryTests(unittest.TestCase):
    def test_context_reset_and_trimming_do_not_remove_archive(self):
        with tempfile.TemporaryDirectory() as td:
            store=bridge.Store(Path(td)/'chat.sqlite3')
            try:
                for n in range(60):
                    store.data.record(str(n),'user',f'message {n}')
                    store.append_turn(str(n),'reply')
                store.clear()
                self.assertEqual(store.history(),[])
                self.assertEqual(store.data.db.execute('select count(*) from messages').fetchone()[0],60)
            finally:store.close()

    def test_duplicate_inputs_do_not_duplicate_archive(self):
        with tempfile.TemporaryDirectory() as td:
            data=Data(td,'one')
            try:
                for _ in range(3):data.record('same','user','one')
                self.assertEqual(data.db.execute('select count(*) from messages').fetchone()[0],1)
            finally:data.close()

    def test_pending_memories_require_confirmation_and_forget_removes_recall(self):
        with tempfile.TemporaryDirectory() as td:
            data=Data(td,'one')
            try:
                mid=data.add_memory('喜欢简短中文回答','msg',state='pending')
                self.assertEqual(data.recall('回答'), '')
                data.change_memory(mid,'active')
                self.assertIn('简短',data.recall('回答'))
                data.change_memory(mid,'forgotten')
                self.assertEqual(data.recall('回答'),'')
                with self.assertRaises(ValueError):data.add_memory('密码：supersecret','msg')
            finally:data.close()

    def test_accounts_are_isolated_and_literal_search_is_safe(self):
        with tempfile.TemporaryDirectory() as td:
            one=Data(Path(td)/'one','one');two=Data(Path(td)/'two','two')
            try:
                one.record('a','user','独有秘密 <script>alert(1)</script>')
                one.add_memory('喜欢音乐','a')
                self.assertEqual(two.search('秘密'),[])
                self.assertEqual(two.recall('音乐'),'')
                self.assertEqual(one.search('%'),[])
                html=one.export('html').read_text(encoding='utf-8')
                self.assertIn('&lt;script&gt;',html)
                self.assertNotIn('<script>',html)
                rows=[json.loads(x) for x in one.export('jsonl').read_text(encoding='utf-8').splitlines()]
                self.assertEqual(rows[0]['account'],'one')
                with self.assertRaises(ValueError):one.export('md','../../oops')
            finally:one.close();two.close()

    def test_persona_is_unused_without_explicit_hash_approval(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'persona.md').write_text('test persona')
            self.assertEqual(approved_persona(p),'')
            (p/'persona-approved.json').write_text(json.dumps({'approved':True,'sha256':hashlib.sha256((p/'persona.md').read_bytes()).hexdigest()}))
            self.assertEqual(approved_persona(p),'test persona')
            (p/'persona.md').write_text('changed')
            self.assertEqual(approved_persona(p),'')

    def test_archive_recall_recovers_old_relevant_messages_without_current_echo(self):
        with tempfile.TemporaryDirectory() as td:
            data=Data(td,'one')
            try:
                data.record('old','user','我们约定去小岛咖啡店讨论项目。')
                data.record('new','user','小岛咖啡店怎么走？')
                found=data.recall_archive('小岛咖啡店',exclude_key='new')
                self.assertIn('约定',found)
                self.assertNotIn('怎么走',found)
                self.assertEqual(data.recall_archive('xyzunrelated'), '')
            finally:data.close()

    def test_harness_export_omits_reasoning_tools_and_runtime_context(self):
        self.assertIsNone(session_messages({'type':'system/message','data':{}}))
        self.assertIsNone(session_messages({'type':'user/message','data':{'source':{'kind':'runtime-context'}}}))
        record={'type':'assistant/message','data':{'message':{'id':'a','role':'assistant','content':[
            {'type':'reasoning','text':'hidden reasoning'},{'type':'text','text':'visible reply'}]}}}
        result=session_messages(record)
        self.assertEqual(result[2],'visible reply')
        self.assertNotIn('hidden reasoning',json.dumps(result))

    def test_clear_command_retains_archive_and_file_destination_is_fixed(self):
        with tempfile.TemporaryDirectory() as td:
            store=bridge.Store(Path(td)/'chat.sqlite3')
            try:
                b=bridge.Bridge({'owner_qq':'17162047','bot_qq':'1103828665','onebot_url':'http://127.0.0.1:13001','onebot_token':'test'},store)
                store.data.record('one','user','saved')
                self.assertIn('档案',b.command('/清空','cmd')[0])
                self.assertEqual(len(store.data.search('saved')),1)
                path=store.data.export('md')
                with patch.object(b,'request') as request:
                    b.send_file(path)
                    self.assertEqual(request.call_args.args[0],'upload_private_file')
                    self.assertEqual(request.call_args.args[1]['user_id'],17162047)
            finally:store.close()

    def test_harness_commands_do_not_reset_codex_context(self):
        with tempfile.TemporaryDirectory() as td:
            store=bridge.Store(Path(td)/'chat.sqlite3')
            try:
                store.append_turn('current','reply')
                b=bridge.Bridge({'harness_records':str(Path(td)/'harness')},store)
                self.assertIn('Harness',b.command('/清空 Harness','cmd')[0])
                self.assertEqual(len(store.history()),2)
                self.assertIn('DeepSeek',b.command('/状态 Harness','cmd')[0])
            finally:store.close()

    def test_group_memory_management_and_export_stay_separate(self):
        with tempfile.TemporaryDirectory() as td:
            store=bridge.Store(Path(td)/'chat.sqlite3')
            try:
                root=Path(td)/'group'
                b=bridge.Bridge({'group_records':str(root)},store)
                b.command('/记住 群 群里喜欢短回复','cmd')
                self.assertEqual(store.data.memory_rows(),[])
                self.assertIn('短回复',b.command('/查看记忆 群','list')[0])
                data=Data(root,'628128804');data.record('group','user','group-only');data.close()
                _,path=b.command('/导出 群 jsonl','export')
                self.assertIn('group-only',path.read_text())
                self.assertEqual(store.data.search('group-only'),[])
            finally:store.close()


if __name__=='__main__':unittest.main()
