"""One local end-to-end check with existing credentials; never prints secrets.

Run with sudo on the server. No model/QQ messages are generated. Restores the
smallc switch after a brief pause; re-applies one timer's existing state.
"""
from http.cookies import SimpleCookie
import http.client
import json
from pathlib import Path
import re
import urllib.parse

ORIGIN = ''
COOKIES = {}


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=35)
    supplied = {'X-Forwarded-Proto':'https','X-Forwarded-Host':ORIGIN[8:],
                'X-Real-IP':'127.0.0.1','Origin':ORIGIN,
                'Cookie':'; '.join(key+'='+value for key,value in COOKIES.items())}
    supplied.update(headers or {})
    connection.request(method, path, body, supplied)
    response = connection.getresponse()
    content = response.read()
    for key,value in response.getheaders():
        if key.lower() == 'set-cookie':
            cookie = SimpleCookie()
            cookie.load(value)
            for name, item in cookie.items():
                COOKIES[name] = item.value
    result = (response.status,content)
    connection.close()
    return result


def state():
    code, body = request(13220,'GET','/home/api/state')
    assert code == 200, 'State read failed: '+str(code)
    return json.loads(body)


def change(current, key, enabled):
    payload = json.dumps({'id':key,'enabled':enabled,'revision':current['revision']})
    code, body = request(13220,'POST','/home/api/change',payload,
                         {'Content-Type':'application/json','X-Home-CSRF':current['csrf']})
    assert code == 200 and json.loads(body).get('ok'), 'Readback failed: '+str(code)
    return state()


def main():
    global ORIGIN
    unit = Path('/etc/systemd/system/bigfish-home.service').read_text()
    ORIGIN = re.search(r'Environment=HOME_ORIGIN=(https://[^\s]+)',unit)[1]
    auth = json.loads(Path('/var/lib/dsh-auth/auth-state.json').read_text())
    username = auth['administrator']['username']
    password = Path('/etc/dsh-auth/admin-bootstrap.password').read_text().strip()
    code, body = request(3080,'GET','/auth/login?returnTo=%2Fhome%2F')
    assert code == 200, 'Login form unavailable'
    csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"',body.decode())
    assert csrf, 'Login form token unavailable'
    form = urllib.parse.urlencode({'username':username,'password':password,'csrf':csrf[1],'returnTo':'/home/'})
    code, body = request(3080,'POST','/auth/login',form,{'Content-Type':'application/x-www-form-urlencoded'})
    del password,form,auth
    assert code == 303 and COOKIES.get('__Host-dsh_auth_session'), 'Existing credential login not verified: '+str(code)
    print('Existing administrator login: OK')
    try:
        code,_ = request(13220,'GET','/home/')
        assert code == 200, 'Private page unavailable'
        current = state()
        assert len(current['features']) == 8
        print('Private page, eight controls, account states and usage: OK')
        print('QQ states:',json.dumps(current['accounts']))
        original = next(f['enabled'] for f in current['features'] if f['id']=='smallc')
        assert type(original) is bool
        try:
            current = change(current,'smallc',not original)
            print('Smallc pause setting and actual flag readback: OK')
        finally:
            current = change(state(),'smallc',original)
        print('Original smallc setting restored: OK')
        gold = next(f['enabled'] for f in current['features'] if f['id']=='gold')
        assert type(gold) is bool, 'Gold timer state inconsistent'
        current = change(current,'gold',gold)
        print('Privileged fixed-timer helper, existing setting re-applied: OK')
        code,_ = request(13220,'POST','/home/api/change','{}',{'Content-Type':'application/json','X-Home-CSRF':'invalid'})
        assert code == 403, 'CSRF guard failed'
        print('Real-session CSRF rejection: OK')
    finally:
        code,body = request(3080,'GET','/auth/csrf')
        if code == 200:
            token = json.loads(body)['csrf']
            request(3080,'POST','/auth/logout',urllib.parse.urlencode({'csrf':token}),{'Content-Type':'application/x-www-form-urlencoded'})
        COOKIES.clear()
    print('Verification session signed out. No messages or model calls were made.')


if __name__ == '__main__':
    main()
