from pathlib import Path
import unittest

from role_registry import roles_from, check_binding


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.data={'owner':'1000000001','accounts':{
            '1000000002':{'name':'小c','config':'/home/ubuntu/qq-codex/bridge/.private/config.json','port':13001},
            '1000000003':{'name':'大肥鱼','config':'/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json','port':13101},
            '1000000005':{'name':'测试角色','role':'demo','port':13301,'model':'deepseek'}}}

    def test_third_role_uses_own_account(self):
        owner,roles=roles_from(self.data)
        self.assertFalse(roles['1000000002'].handles_owner)
        role=roles['1000000005']
        self.assertTrue(role.handles_owner)
        self.assertEqual(role.runtime,Path('/home/ubuntu/qq-roles/demo/napcat-runtime'))
        config=dict(bot_qq='1000000005', owner_qq=owner,onebot_url='http://127.0.0.1:13301')
        check_binding(role,config,'1000000005',owner)
        with self.assertRaises(ValueError):
            check_binding(role,config,'1000000002',owner)

    def test_rejects_cross_role_paths_and_ports(self):
        for change in [dict(role='../qq-codex'),dict(port=13101),dict(config='/etc/passwd')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                roles_from({**self.data,'accounts':{**self.data['accounts'],
                    '1000000005':{**self.data['accounts']['1000000005'],**change}}})
