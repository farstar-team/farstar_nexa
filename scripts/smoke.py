"""Exercise an explicitly selected development deployment without external provider traffic."""
import http.cookiejar
import json
import os
import secrets
import time
import urllib.request
from pathlib import Path

base = os.environ.get("SMOKE_URL", "http://localhost:8080")
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def request(path, method="GET", data=None):
    csrf = next((cookie.value for cookie in cookies if cookie.name == "nexa_csrf"), "")
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type":"application/json", "X-CSRF-Token":csrf},method=method)
    with client.open(req, timeout=15) as response:
        return json.load(response)


def ready():
    for _ in range(90):
        try:
            if request('/ready')['status']=='ready':return
        except OSError:
            time.sleep(2)
    raise SystemExit('Deployment did not become ready')


def main():
    ready()
    assert request('/api/config')['mock_mode'], 'Smoke checks require explicit mock mode'
    state=Path('runtime/smoke-state.json')
    if state.exists():
        data=json.loads(state.read_text())
        request('/api/auth/login','POST',data['login'])
        assert request('/api/dashboard')['counts']['messages']==2
        assert len(request('/api/accounts'))==1
        print('Persistent data survived restart/restore.')
        return
    login={'username':'smoke_'+secrets.token_hex(4),'password':secrets.token_urlsafe(32)}
    request('/api/auth/register','POST',{**login,'email':login['username']+'@example.com'})
    request('/api/auth/login','POST',login)
    account=request('/api/accounts/mock','POST',{'name':'CI mock account'})
    request('/api/automations','POST',{'name':'CI keyword reply','account_id':account['id'],
            'keywords':['قیمت'],'response':'سلام از نکسا'})
    incoming={'account_id':account['id'],'sender':'ci_customer','text':'قیمت','event_id':'ci-first-event'}
    assert request('/api/messages/simulate','POST',incoming)['accepted']
    assert not request('/api/messages/simulate','POST',incoming)['accepted']
    for _ in range(30):
        if request('/api/dashboard')['counts']['messages']==2:break
        time.sleep(1)
    conversation=request('/api/conversations')[0]
    messages=request('/api/conversations/'+conversation['id']+'/messages')
    assert len(messages)==2 and messages[1]['text']=='سلام از نکسا' and messages[1]['status']=='sent'
    assert request('/api/executions')[0]['status']=='sent'
    state.write_text(json.dumps({'login':login}));state.chmod(0o600)
    print('Registration, login, mock provider, automation, idempotency and inbox passed.')


if __name__=='__main__':main()
