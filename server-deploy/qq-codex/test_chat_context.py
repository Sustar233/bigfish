import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bridge
from chat_context import prepare_history, public_url, search_mode, wants_archive
from qq_data import Data

NOW = 1794828600.0


class ContextTests(unittest.TestCase):
    def test_yesterday_is_not_current_context_and_archive_survives(self):
        with tempfile.TemporaryDirectory() as td:
            s = bridge.Store(Path(td)/'chat.db')
            try:
                s.data.record('old/user', 'user', '明天考试', occurred=NOW-86400)
                with patch.object(bridge.time, 'time', return_value=NOW-86400):
                    s.append_turn('明天考试', '加油')
                history, runtime = s.context(now=NOW)
                self.assertEqual(history, [])
                self.assertEqual(runtime['session_state'], 'new')
                self.assertEqual(runtime['gap_seconds'], 86400)
                self.assertEqual(len(s.data.search('考试')), 1)
            finally:
                s.close()

    def test_soft_idle_reduces_window_and_reports_shanghai_time(self):
        messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': str(i),
                     'occurred': NOW-3*3600+i} for i in range(12)]
        history, runtime = prepare_history(messages, NOW)
        self.assertEqual(len(history), 4)
        self.assertEqual(runtime['session_state'], 'soft')
        self.assertEqual(runtime['timezone'], 'Asia/Shanghai')
        self.assertTrue(history[0]['sent_at'].endswith('+08:00'))

    def test_midnight_does_not_erase_recent_chat_but_old_session_stays_out(self):
        messages = [{'role': 'user', 'content': '昨天的旧话题', 'occurred': NOW-86400},
                    {'role': 'user', 'content': '刚才的新话题', 'occurred': NOW-120}]
        history, runtime = prepare_history(messages, NOW)
        self.assertEqual([m['content'] for m in history], ['刚才的新话题'])
        self.assertEqual(runtime['session_state'], 'continuing')

    def test_old_schema_migrates_without_fabricating_message_time(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'chat.db'
            with sqlite3.connect(p) as db:
                db.execute('CREATE TABLE history(id INTEGER PRIMARY KEY,role TEXT,content TEXT)')
                db.execute("INSERT INTO history(role,content) VALUES('user','旧消息')")
            s = bridge.Store(p)
            try:
                self.assertEqual(s.history(), [])
                self.assertEqual(s.db.execute('SELECT content FROM history').fetchone()[0], '旧消息')
                self.assertEqual(len(s.data.search('旧消息')), 1)
            finally:
                s.close()

    def test_archive_intent_is_explicit_and_results_include_original_date(self):
        self.assertFalse(wants_archive('刚吃完饭'))
        self.assertTrue(wants_archive('接着昨天的考试聊'))
        with tempfile.TemporaryDirectory() as td:
            d = Data(td, 'test')
            try:
                d.record('old', 'user', '昨天考试有点紧张', occurred=NOW-86400)
                self.assertIn('+08:00', d.recall_archive('考试'))
                d.record('secret', 'user', '考试密码：do-not-recall', occurred=NOW-86400)
                self.assertNotIn('do-not-recall', d.recall_archive('考试'))
            finally:
                d.close()

    def test_unrelated_events_are_not_always_injected_as_profile(self):
        with tempfile.TemporaryDirectory() as td:
            d = Data(td, 'test')
            try:
                d.add_memory('明天有考试', 'old')
                d.add_memory('喜欢简短回复', 'profile')
                self.assertNotIn('考试', d.recall('晚上好'))
                self.assertIn('简短', d.recall('晚上好'))
                self.assertIn('记录于', d.recall('考试'))
            finally:
                d.close()


class SearchTests(unittest.TestCase):
    def test_routing_distinguishes_chat_general_search_and_fresh_queries(self):
        self.assertEqual(search_mode('今天心情不太好'), 'disabled')
        self.assertEqual(search_mode('查一下黑洞是什么'), 'cached')
        self.assertEqual(search_mode('帮我查今天长沙天气'), 'live')
        self.assertEqual(search_mode('今天 DeepSeek 最新版本是什么'), 'live')
        self.assertEqual(search_mode('读一下 https://www.python.org/'), 'cached')

    def test_private_addresses_and_credentials_are_not_forwarded(self):
        for url in ['http://127.0.0.1/', 'http://169.254.169.254/latest/',
                    'http://[::1]/', 'http://192.168.1.2/', 'http://localhost/',
                    'http://user:password@example.com/', 'http://example.com:8080/',
                    'http://127.1/', 'http://service.internal/']:
            self.assertFalse(public_url(url), url)
            self.assertEqual(search_mode('查一下 '+url), 'blocked')
        with patch.object(bridge.subprocess, 'run') as run:
            self.assertEqual(bridge.public_search('查一下 token=private-secret', {})['status'], 'blocked')
            run.assert_not_called()

    def test_search_requires_actual_tool_event_and_sources(self):
        def fake(command, **kwargs):
            output = Path(command[command.index('--output-last-message')+1])
            output.write_text(json.dumps({'answer': 'A factual answer', 'sources': [
                {'title': 'Python', 'url': 'https://www.python.org/'}]}))
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(bridge.subprocess, 'run', side_effect=fake):
            self.assertEqual(bridge.public_search('查一下 Python', {})['status'], 'unavailable')

    def test_isolated_search_receives_only_current_query(self):
        captured = []
        def fake(command, **kwargs):
            captured.append((command, kwargs['input']))
            output = Path(command[command.index('--output-last-message')+1])
            output.write_text(json.dumps({'answer': 'Python is a language', 'sources': [
                {'title': 'Python', 'url': 'https://www.python.org/'}]}))
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                'type': 'item.completed', 'item': {'type': 'web_search'}}), stderr='')
        with patch.object(bridge.subprocess, 'run', side_effect=fake):
            result = bridge.public_search('查一下 Python', {'PATH': '/usr/bin'})
        self.assertEqual(result['status'], 'ok')
        command, prompt = captured[0]
        self.assertIn('web_search="cached"', command)
        self.assertIn('shell_tool', command)
        self.assertNotIn('persona', prompt)
        self.assertNotIn('memory_candidates', prompt)

    def test_final_synthesis_still_has_no_search_or_shell_and_sources_are_returned(self):
        captured = []
        evidence = {'status': 'ok', 'answer': 'Fact', 'sources': [
            {'title': 'Source', 'url': 'https://example.com/'}]}
        def fake(command, **kwargs):
            captured.append((command, kwargs))
            output = Path(command[command.index('--output-last-message')+1])
            output.write_text(json.dumps({'reply': '查到了。', 'memory_candidates': []}))
            return SimpleNamespace(returncode=0, stderr='')
        with patch.object(bridge, 'public_search', return_value=evidence), \
             patch.object(bridge.subprocess, 'run', side_effect=fake):
            reply = bridge.model_reply([], '查一下资料', memory='private-memory')
        self.assertIn('https://example.com/', reply)
        self.assertIn('web_search="disabled"', captured[0][0])
        self.assertIn('shell_tool', captured[0][0])
        self.assertIn('private-memory', captured[0][1]['input'])


if __name__ == '__main__':
    unittest.main()
