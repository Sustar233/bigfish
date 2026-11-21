"""Production Room admission tests; all external requests and sends are mocked."""
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import group_chat as g


class QzoneRoomTests(unittest.TestCase):
    def test_owner_command_runs_both_once_across_two_feeds_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots = {label: Path(tmp) / label for label in g.ACCOUNTS}
            for p in roots.values():
                p.mkdir()
            calls = {label: 0 for label in g.ACCOUNTS}
            states = {label: False for label in g.ACCOUNTS}
            endpoints = {}
            for label, account in g.ACCOUNTS.items():
                def request(action, data, label=label, account=account):
                    if action == 'get_login_info':
                        return {'user_id': account}
                    if action == 'get_qzone_msg_list':
                        return {'msglist': [{'tid': 'fixture', 'user_id': g.OWNER, 'time': 1700000000,
                            'content': 'fixture', 'feed': {'cell_common': {'app_id': 311},
                            'cell_like': {'liked': states[label]}}}]}
                    self.assertEqual(action, 'like_qzone')
                    self.assertEqual(data['target_uin'], g.OWNER)
                    calls[label] += 1
                    states[label] = True
                endpoints[label] = types.SimpleNamespace(
                    config={'owner_qq': g.OWNER, 'bot_qq': account}, request=request)
            room = g.Room(Path(tmp) / 'room', endpoints=endpoints)
            room.members_safe = Mock(return_value=True)
            room.send = Mock()
            room.generate = Mock(side_effect=AssertionError('model must not run'))
            event = {'post_type': 'message', 'message_type': 'group', 'group_id': g.GROUP,
                'user_id': g.OWNER, 'self_id': g.ACCOUNTS['codex'], 'message_id': 1, 'time': 1700000000,
                'message': [{'type': 'text', 'data': {'text': '你们给我最新一条说说点赞'}}]}
            try:
                with patch.dict(g.PRIVATE, roots):
                    self.assertTrue(room.admit(event))
                    self.assertFalse(room.admit({**event, 'self_id': g.ACCOUNTS['harness'], 'message_id': 2}))
                    for user in [g.ACCOUNTS['codex'], g.ACCOUNTS['harness'], '9']:
                        self.assertFalse(room.admit({**event, 'user_id': user, 'time': 1700000001}))
                self.assertEqual(calls, {label: 1 for label in g.ACCOUNTS})
                self.assertEqual(room.send.call_count, 2)
                self.assertEqual(room.pending, [])
                room.generate.assert_not_called()
            finally:
                room.close()


if __name__ == '__main__':
    unittest.main()
