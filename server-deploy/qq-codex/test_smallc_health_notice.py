import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import qq_maintenance as health
from smallc_health_notice import notify


class Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        mock = patch('smallc_health_notice.PENDING', Path(temp.name)/'offer')
        mock.start()
        self.addCleanup(mock.stop)

    def test_fixed_owner_and_uncertain_send(self):
        api=Mock(return_value={'message_id':123})
        self.assertEqual(notify(api,False),123)
        args=api.call_args.args
        self.assertEqual(args[0],'harness');self.assertEqual(args[2]['user_id'],1000000001)
        self.assertIn('二维码',args[2]['message'][0]['data']['text'])
        with self.assertRaises(RuntimeError):notify(Mock(return_value={}),False)
    def run_health(self,folder,harness_ready=True,smallc_ready=False):
        def state(label,account):return 'ready' if (harness_ready if label=='harness' else smallc_ready) else 'unavailable'
        with patch.object(health,'ROOT',Path(folder)),patch.object(health,'onebot_health',side_effect=state),patch.object(health,'mail') as mail,patch.object(health,'api',return_value={'message_id':123}) as api,patch.object(health.subprocess,'check_output',return_value=''):
            health.health()
            return mail,api,json.loads((Path(folder)/'health.json').read_text())
    def test_smallc_offline_uses_whale_not_mail(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'health.json').write_text(json.dumps({'codex':{'failures':1}}))
            mail,api,state=self.run_health(folder)
            mail.assert_not_called();api.assert_called_once();self.assertTrue(state['codex']['alert_active'])
    def test_whale_offline_pending_never_mail_for_smallc(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'health.json').write_text(json.dumps({'codex':{'failures':1}}))
            mail,api,state=self.run_health(folder,False)
            api.assert_not_called();self.assertTrue(state['codex']['qq_notification_pending']);self.assertEqual(state['codex']['alerted_at'],0)
            mail,api,state=self.run_health(folder,True)
            mail.assert_not_called();api.assert_called_once()
    def test_cooldown_then_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'health.json').write_text(json.dumps({'codex':{'failures':1}}))
            self.run_health(folder)
            mail,api,state=self.run_health(folder)
            mail.assert_not_called();api.assert_not_called()
            mail,api,state=self.run_health(folder,smallc_ready=True)
            mail.assert_not_called();api.assert_called_once();self.assertFalse(state['codex']['alert_active'])


if __name__=='__main__':unittest.main()
