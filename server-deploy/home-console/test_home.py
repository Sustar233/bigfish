import http.client
import json
from pathlib import Path
import tempfile
import sqlite3
import sys
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import app
import control
from install import patched_sources


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patches = [patch.object(app, 'DATA', self.data), patch.object(app, 'ORIGIN', 'https://home.test'),
                        patch.object(control, 'FLAGS', self.data/'flags'), patch.object(control, 'GROUP_DB', self.data/'group.sqlite3')]
        for p in self.patches:
            p.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = '__Host-dsh_auth_session=test'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def request(self, path, body=None, origin='https://home.test', token=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        headers = {'Cookie': self.cookie}
        if body is not None:
            headers.update({'Content-Type':'application/json', 'Origin':origin, 'X-Home-CSRF':token or app.csrf(self.cookie)})
        conn.request('POST' if body is not None else 'GET', path, json.dumps(body) if body is not None else None, headers)
        r = conn.getresponse()
        raw = r.read()
        result = (r.status, dict(r.getheaders()), json.loads(raw) if raw and r.getheader('Content-Type','').startswith('application/json') else raw)
        conn.close()
        return result

    def test_unauthenticated_requests_do_not_read_or_change_state(self):
        with patch.object(app, 'authenticate', return_value=(False,None)), patch.object(app,'state') as read, patch.object(control,'change') as change:
            self.assertEqual(self.request('/home/')[0],303)
            self.assertEqual(self.request('/home/api/state')[0],401)
            self.assertEqual(self.request('/home/api/change', {'id':'smallc','enabled':False})[0],401)
            read.assert_not_called()
            change.assert_not_called()

    def test_forged_identity_headers_are_not_authentication(self):
        with patch.object(app.OPENER, 'open', side_effect=OSError('offline')):
            self.assertEqual(app.authenticate(self.cookie,'GET','/home/'),(False,None))

    def test_non_admin_session_denied(self):
        class Response:
            status=204
            headers={'X-Dsh-Auth-Roles':'user'}
            def __enter__(self): return self
            def __exit__(self,*_): pass
        with patch.object(app.OPENER,'open',return_value=Response()):
            self.assertEqual(app.authenticate(self.cookie,'GET','/home/')[0],False)

    def test_admin_session_accepted(self):
        class Response:
            status=204
            headers={'X-Dsh-Auth-Roles':'user,admin'}
            def __enter__(self): return self
            def __exit__(self,*_): pass
        with patch.object(app.OPENER,'open',return_value=Response()):
            self.assertTrue(app.authenticate(self.cookie,'GET','/home/')[0])

    def test_original_origin_forwarded_to_session_verifier(self):
        with patch.object(app.OPENER,'open',side_effect=OSError('test')) as open_request:
            app.authenticate(self.cookie,'POST','/home/api/change',origin='https://home.test')
            request = open_request.call_args.args[0]
            self.assertEqual(request.get_header('Origin'),'https://home.test')
            self.assertEqual(request.get_header('X-original-method'),'POST')

    def test_origin_and_csrf_rejected_before_mutation(self):
        with patch.object(app,'authenticate',return_value=(True,None)), patch.object(control,'change') as change:
            self.assertEqual(self.request('/home/api/change',{},origin='https://other.test')[0],403)
            self.assertEqual(self.request('/home/api/change',{},token='bad')[0],403)
            change.assert_not_called()

    def test_invalid_feature_and_non_boolean_rejected(self):
        with patch.object(app,'authenticate',return_value=(True,None)), patch.object(control,'change') as change:
            for body in ({'id':'ssh','enabled':False},{'id':'smallc','enabled':'false'}):
                self.assertEqual(self.request('/home/api/change',body)[0],400)
            change.assert_not_called()

    def test_stale_revision_cannot_overwrite_settings(self):
        rows=[dict(id='smallc',enabled=True,actual='active',saved='enabled')]
        with patch.object(app,'authenticate',return_value=(True,None)), patch.object(control,'snapshot',return_value=rows), patch.object(control,'change') as change:
            self.assertEqual(self.request('/home/api/change',{'id':'smallc','enabled':False,'revision':'old'})[0],409)
            change.assert_not_called()

    def test_write_readback_and_audit(self):
        rows=[dict(id='smallc',enabled=True,actual='active',saved='enabled')]
        after=[dict(id='smallc',enabled=False,actual='active',saved='paused')]
        with patch.object(app,'authenticate',return_value=(True,None)), patch.object(control,'snapshot',side_effect=[rows,after]):
            response=self.request('/home/api/change',{'id':'smallc','enabled':False,'revision':control.revision(rows)})
        self.assertEqual(response[0],200)
        self.assertTrue((self.data/'flags/smallc.paused').exists())
        self.assertEqual(app.history()[0]['result'],'verified')
        self.assertIn('no-store',response[1]['Cache-Control'])

    def test_false_success_is_not_reported(self):
        rows=[dict(id='smallc',enabled=True,actual='active',saved='enabled')]
        with patch.object(app,'authenticate',return_value=(True,None)), patch.object(control,'snapshot',return_value=rows), patch.object(control,'change'):
            self.assertEqual(self.request('/home/api/change',{'id':'smallc','enabled':False,'revision':control.revision(rows)})[0],503)
        self.assertEqual(app.history()[0]['result'],'unconfirmed')

    def test_assets_are_allowlisted(self):
        with patch.object(app,'authenticate',return_value=(True,None)):
            self.assertEqual(self.request('/home/../../app.py')[0],404)
            self.assertEqual(self.request('/home/app.py')[0],404)
            self.assertEqual(self.request('/home/')[0],200)

    def test_pause_enable_is_persistent_and_idempotent(self):
        control.change('smallc',False)
        control.change('smallc',False)
        self.assertTrue((control.FLAGS/'smallc.paused').exists())
        control.change('smallc',True)
        control.change('smallc',True)
        self.assertFalse((control.FLAGS/'smallc.paused').exists())

    def test_group_qq_pause_and_web_pause_share_state(self):
        from contextlib import closing
        with closing(sqlite3.connect(control.GROUP_DB)) as db, db:
            db.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT)')
            db.execute("INSERT INTO state VALUES('epoch','5')")
        control.change('group',False)
        with closing(sqlite3.connect(control.GROUP_DB)) as db:
            self.assertEqual(db.execute("SELECT value FROM state WHERE key='paused'").fetchone()[0],'1')
            self.assertEqual(db.execute("SELECT value FROM state WHERE key='epoch'").fetchone()[0],'6')
        control.change('group',True)
        with closing(sqlite3.connect(control.GROUP_DB)) as db:
            self.assertEqual(db.execute("SELECT value FROM state WHERE key='paused'").fetchone()[0],'0')

    def test_privileged_helper_rejects_arbitrary_commands(self):
        with patch.object(sys,'argv',['helper','ssh','off']), patch.object(control,'run') as run:
            with self.assertRaises(SystemExit):
                control.timer_main()
            run.assert_not_called()

    def test_timer_change_uses_fixed_unit(self):
        with patch.object(control,'run') as run:
            run.return_value.returncode=0
            control.change('weather',False)
            run.assert_called_once_with(['sudo','-n','/usr/local/sbin/bigfish-home-timer','weather','off'])

    def test_timer_helper_exact_command(self):
        with patch.object(sys,'argv',['helper','weather','off']), patch.object(control,'run') as run:
            run.return_value.returncode=0
            with self.assertRaises(SystemExit) as code:
                control.timer_main()
            self.assertEqual(code.exception.code,0)
            run.assert_called_once_with(['/usr/bin/systemctl','disable','--now','changsha-weather.timer'])


if __name__ == '__main__':
    unittest.main()
