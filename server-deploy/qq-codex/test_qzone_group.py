from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock

from qzone_commands import qzone_command
from qzone_group import handle_group_qzone, plan

OWNER = '1000000001'
GROUP = '1000000004'
ACCOUNTS = {'codex': '1000000002', 'harness': '1000000003'}


class QzoneGroupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.private = {k: Path(self.tmp.name) / k for k in ACCOUNTS}
        for p in self.private.values():
            p.mkdir()
        self.state = {k: {'liked': False, 'writes': 0} for k in ACCOUNTS}
        self.room = Mock()
        self.room.members_safe.return_value = True
        self.room.control.get.return_value = '0'
        self.room.control.reserve.side_effect = lambda key, label: label
        self.room.endpoints = {}
        for label, account in ACCOUNTS.items():
            def request(action, data, label=label, account=account):
                if action == 'get_login_info':
                    return {'user_id': account}
                if action == 'get_qzone_msg_list':
                    self.assertEqual(data, {'target_uin': OWNER, 'format': 'native'})
                    return {'msglist': [{'tid': 'latest', 'user_id': OWNER, 'time': 1700000000,
                        'content': 'fixture', 'feed': {'cell_common': {'app_id': 311},
                        'cell_like': {'liked': self.state[label]['liked']}}}]}
                self.assertEqual(action, 'like_qzone')
                self.assertEqual(data['target_uin'], OWNER)
                self.state[label]['writes'] += 1
                self.state[label]['liked'] = True
            self.room.endpoints[label] = types.SimpleNamespace(
                config={'owner_qq': OWNER, 'bot_qq': account}, request=Mock(side_effect=request))

    def tearDown(self):
        self.tmp.cleanup()

    def handle(self, text='你们给我最新一条说说点赞', mentions=()):
        return handle_group_qzone(self.room, 'fixture', text, mentions, OWNER, GROUP, ACCOUNTS, self.private)

    def test_collective_and_unaddressed_commands_choose_both(self):
        for text in ['你们给我最新一条说说点赞', '你们一起给我说说点赞', '/空间点赞',
                     '小c和大肥鱼给我最新一条说说点赞']:
            self.assertEqual(set(plan(text, [], ACCOUNTS)[1]), set(ACCOUNTS))

    def test_name_or_at_selects_one_but_collective_selects_both(self):
        self.assertEqual(plan('大肥鱼给我说说点赞', [], ACCOUNTS)[1], ['harness'])
        self.assertEqual(plan('给我说说点赞', [ACCOUNTS['codex']], ACCOUNTS)[1], ['codex'])
        self.assertEqual(set(plan('你们给我说说点赞', [ACCOUNTS['codex']], ACCOUNTS)[1]), set(ACCOUNTS))

    def test_questions_and_embedded_text_do_not_act(self):
        for text in ['你们可以给我说说点赞吗', '不要给我说说点赞', '引用：你们给我说说点赞',
                     '大肥鱼给我说说点赞？']:
            self.assertFalse(self.handle(text))
        self.room.members_safe.assert_not_called()

    def test_both_bots_write_and_acknowledge_independently(self):
        self.assertTrue(self.handle())
        self.assertEqual([s['writes'] for s in self.state.values()], [1, 1])
        self.assertEqual(self.room.send.call_count, 2)
        self.assertEqual({c.args[0] for c in self.room.send.call_args_list}, set(ACCOUNTS))
        self.assertTrue(all('核验成功' in c.args[1] for c in self.room.send.call_args_list))

    def test_private_and_group_share_each_bots_dedup_state(self):
        endpoint = self.room.endpoints['codex']
        qzone_command('/空间点赞', endpoint.request, endpoint.config, self.private['codex'])
        self.handle()
        self.assertEqual([s['writes'] for s in self.state.values()], [1, 1])

    def test_one_offline_bot_does_not_block_the_other(self):
        self.room.endpoints['codex'].request.side_effect = ConnectionError('offline')
        self.handle()
        self.assertEqual(self.state['codex']['writes'], 0)
        self.assertEqual(self.state['harness']['writes'], 1)
        self.assertEqual(self.room.send.call_count, 2)

    def test_wrong_endpoint_identity_cannot_write(self):
        self.room.endpoints['codex'].config['bot_qq'] = ACCOUNTS['harness']
        self.handle('小c给我说说点赞')
        self.room.endpoints['codex'].request.assert_not_called()
        self.assertTrue(all(s['writes'] == 0 for s in self.state.values()))

    def test_membership_change_and_pause_block_all_writes(self):
        self.room.members_safe.return_value = False
        self.handle()
        self.room.control.reserve.assert_not_called()
        self.room.control.get.return_value = '1'
        self.handle()
        self.assertTrue(all(s['writes'] == 0 for s in self.state.values()))

    def test_room_budget_is_respected(self):
        self.room.control.reserve.return_value = None
        self.room.control.reserve.side_effect = None
        self.handle()
        self.assertTrue(all(s['writes'] == 0 for s in self.state.values()))
        self.room.notice.assert_called_once()


if __name__ == '__main__':
    unittest.main()
