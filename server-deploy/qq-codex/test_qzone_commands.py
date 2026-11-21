import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from qzone_commands import qzone_command

CONFIG = {'owner_qq': '1000000001', 'bot_qq': '1000000002'}


def post(tid='latest', owner='1000000001', liked=False, at=1700000000, app=311):
    return {'tid': tid, 'user_id': owner, 'time': at, 'content': 'test post',
            'feed': {'cell_common': {'app_id': app}, 'cell_like': {'liked': liked}}}


class QzoneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rows = [post()]
        self.writes = []
        self.fail_write = False
        self.apply_write = True

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, action, data):
        if action == 'get_login_info':
            return {'user_id': CONFIG['bot_qq']}
        if action == 'get_qzone_msg_list':
            self.assertEqual(data, {'target_uin': CONFIG['owner_qq'], 'format': 'native'})
            return {'msglist': copy.deepcopy(self.rows)}
        self.assertEqual(action, 'like_qzone')
        self.assertEqual(data['target_uin'], CONFIG['owner_qq'])
        self.writes.append(data)
        if self.apply_write:
            next(p for p in self.rows if p['tid'] == data['tid'])['feed']['cell_like']['liked'] = True
        if self.fail_write:
            raise TimeoutError('lost acknowledgement')

    def run_command(self, text='/空间点赞', request=None):
        with patch('qzone_commands.time.sleep'):
            return qzone_command(text, request or self.request, CONFIG, self.root)

    def test_question_and_embedded_command_do_not_act(self):
        request = Mock(side_effect=AssertionError('unexpected request'))
        for text in ['小c能给我说说点赞吗', '不要给我最新一条说说点赞',
                     '转发内容：给我最新一条说说点赞', '给我最新一条说说点赞？']:
            self.assertIsNone(self.run_command(text, request))
        self.assertFalse(list(self.root.iterdir()))

    def test_other_target_arguments_are_refused_without_requests(self):
        request = Mock(side_effect=AssertionError('unexpected request'))
        self.assertIn('只处理你本人', self.run_command('/空间点赞 999999999', request))

    def test_wrong_logged_in_account_blocks_write(self):
        request = Mock(return_value={'user_id': '999999999'})
        self.assertIn('身份不匹配', self.run_command(request=request))
        self.assertEqual(request.call_count, 1)

    def test_newest_own_shuoshuo_is_chosen_and_verified(self):
        self.rows = [post('older', at=1600000000), post('other', owner='999999999', at=1800000000),
                     post('album', app=4, at=1800000000), post('latest')]
        self.assertIn('核验成功', self.run_command('给我最新一条说说点赞'))
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0]['tid'], 'latest')
        self.assertEqual(self.writes[0]['abstime'], 1700000000)
        self.assertIn('核验点赞成功', self.run_command('/空间状态'))

    def test_already_liked_does_not_write(self):
        self.rows[0]['feed']['cell_like']['liked'] = True
        self.assertIn('已经点过赞', self.run_command())
        self.assertFalse(self.writes)

    def test_unknown_or_malformed_liked_state_does_not_write(self):
        for value in [None, 'false', 0]:
            self.rows[0]['feed']['cell_like']['liked'] = value
            self.assertIn('读不到', self.run_command())
        self.assertFalse(self.writes)

    def test_lost_acknowledgement_is_verified_without_replaying_write(self):
        self.fail_write = True
        self.assertIn('核验成功', self.run_command())
        self.run_command()
        self.assertEqual(len(self.writes), 1)

    def test_unconfirmed_write_is_not_claimed_successful_or_retried(self):
        self.apply_write = False
        self.fail_write = True
        self.assertIn('没能确认结果', self.run_command())
        self.assertIn('先不重复点赞', self.run_command())
        self.assertEqual(len(self.writes), 1)

    def test_missing_owner_posts_cannot_write(self):
        self.rows = [post(owner='999999999')]
        self.assertIn('没找到', self.run_command())
        self.assertFalse(self.writes)


if __name__ == '__main__':
    unittest.main()
