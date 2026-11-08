"""Google Drive sync tests with a mocked Google Identity Services + Drive REST API.
Run:  python -m http.server 8765 &   then   python tests/test_cloud.py"""
import os, json, re
os.makedirs('tests/out', exist_ok=True)
from playwright.sync_api import sync_playwright

URL = 'http://localhost:8765/'
CID = '123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com'
P, F = [], []
def check(n, c):
    (P if c else F).append(n); print(('PASS ' if c else 'FAIL ') + n)

MOCK_GIS = """
window.__gis={requests:0,revoked:0,cfg:null};
window.google={accounts:{oauth2:{
  initTokenClient(cfg){window.__gis.cfg=cfg;return {requestAccessToken(o){window.__gis.requests++;window.__gis.prompt=o&&o.prompt;
     setTimeout(()=>cfg.callback(window.__gis.deny?{error:'access_denied'}:{access_token:'tok-'+window.__gis.requests,expires_in:3600}),20);}}},
  revoke(t,cb){window.__gis.revoked++;cb&&cb({successful:true});}}}};
"""

class Drive:
    def __init__(self): self.files = {}; self.calls = []; self.bad_auth = 0
    def handle(self, route, req):
        url = req.url; auth = req.headers.get('authorization', '')
        self.calls.append((req.method, url, auth))
        if not auth.startswith('Bearer tok-'): self.bad_auth += 1; return route.fulfill(status=401, body='{}')
        if req.method == 'GET' and '/drive/v3/files?' in url:
            return route.fulfill(status=200, content_type='application/json', body=json.dumps({'files': [{'id': k} for k in self.files]}))
        m = re.search(r'/drive/v3/files/([A-Za-z0-9_-]+)\?alt=media', url)
        if req.method == 'GET' and m:
            return route.fulfill(status=200, content_type='application/json', body=self.files[m.group(1)])
        if req.method == 'POST' and 'uploadType=multipart' in url:
            body = req.post_data_buffer.decode('utf-8', 'replace')
            assert "appDataFolder" in body
            data = body[body.rfind('{"v":'):]; data = data[:data.rfind('}') + 1]
            fid = 'file_abcdef123456'; self.files[fid] = data
            return route.fulfill(status=200, content_type='application/json', body=json.dumps({'id': fid}))
        m = re.search(r'/upload/drive/v3/files/([A-Za-z0-9_-]+)\?uploadType=media', url)
        if req.method == 'PATCH' and m:
            self.files[m.group(1)] = req.post_data; return route.fulfill(status=200, body='{}')
        return route.fulfill(status=404, body='{}')

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox'])
    ctx = b.new_context(viewport={'width': 390, 'height': 844})
    ctx.add_init_script(MOCK_GIS)
    drive = Drive(); ctx.route('https://www.googleapis.com/**', drive.handle)
    external = []
    ctx.on('request', lambda r: (not r.url.startswith(('http://localhost', 'data:', 'blob:', 'https://www.googleapis.com'))) and external.append(r.url))
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(400); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(400)

    # 1. Client ID validation
    pg.click('[data-a=settings]')
    check('cloud section shown in installed app', 'סנכרון ל-Google Drive' in pg.inner_text('#md'))
    pg.fill('#gcid', '<img src=x onerror=alert(1)>'); pg.click('[data-a=cloud-save-id]'); pg.wait_for_timeout(100)
    check('invalid Client ID rejected', pg.evaluate('__gym.S.settings.gcid') == '')
    pg.fill('#gcid', CID); pg.click('[data-a=cloud-save-id]'); pg.wait_for_timeout(200)
    check('valid Client ID saved', pg.evaluate('__gym.S.settings.gcid') == CID)
    pg.click('#md [data-a=close]')
    check('header shows sync chip', pg.inner_text('#sync') == '☁️ סנכרן')

    # 2. connect + first upload creates file in appDataFolder
    pg.evaluate("""__gym.S.exercises=[{id:'cccccc1',group:'chest',name:'לחיצה',sets:3,w:20,r:10,rest:60,machine:'',notes:'',km:0,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0}];__gym.S.updatedAt=Date.now();""")
    pg.click('#sync'); pg.wait_for_timeout(800)
    check('scope is drive.appdata only', pg.evaluate('__gis.cfg.scope') == 'https://www.googleapis.com/auth/drive.appdata')
    check('first connect asks for consent', pg.evaluate('__gis.prompt') == 'consent')
    check('file created in Drive', len(drive.files) == 1 and 'לחיצה' in list(drive.files.values())[0])
    check('header shows synced', pg.inner_text('#sync') == '☁️ מסונכרן')
    check('token never persisted', 'tok-' not in pg.evaluate("localStorage.getItem('gymapp.v1')"))

    # 3. local change auto-syncs (PATCH)
    pg.click('nav [data-a=tab][data-v=ex]'); pg.click('[data-a=ex-new][data-v=back]'); pg.fill('#f-name', 'חתירה'); pg.click('#exf button[type=submit]')
    pg.wait_for_timeout(4800)
    check('auto-sync after change uploads new data', 'חתירה' in list(drive.files.values())[0] and any(c[0] == 'PATCH' for c in drive.calls))

    # 4. remote newer data merges into local (other device added a workout + exercise)
    remote = json.loads(list(drive.files.values())[0])
    remote['exercises'].append({'id': 'llllll1', 'group': 'legs', 'name': 'סקוואט', 'sets': 3, 'w': 40, 'r': 8, 'rest': 90})
    remote['logs']['2026-10-01'] = {'items': [{'exId': 'cccccc1', 'name': 'לחיצה', 'group': 'chest', 't': {'sets': 1}, 'sets': [{'w': 20, 'r': 10}]}], 'finishedAt': 5}
    remote['updatedAt'] = remote['updatedAt'] + 100000
    drive.files[list(drive.files)[0]] = json.dumps(remote)
    pg.evaluate("__gym.S.logs['2026-10-02']={items:[{exId:'cccccc1',name:'לחיצה',group:'chest',machine:'',notes:'',rest:60,hrB:0,hrA:0,role:'',t:{sets:1,w:20,r:10,km:0,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0},sets:[{w:20,r:10,km:0,min:0,inc:0,spd:0,iv:0,at:1}]}],startedAt:1,finishedAt:2}")
    pg.click('#sync'); pg.wait_for_timeout(800)
    st = pg.evaluate('__gym.S')
    check('remote exercise merged in', any(e['name'] == 'סקוואט' for e in st['exercises']))
    check('workouts from both devices kept', '2026-10-01' in st['logs'] and '2026-10-02' in st['logs'])
    check('merged result uploaded back', '2026-10-02' in list(drive.files.values())[0])

    # 5. malicious remote payload is sanitized
    evil = json.loads(list(drive.files.values())[0])
    evil['exercises'][0]['name'] = '<img src=x onerror="window.__pwn=1">'
    evil['plans']['__proto__'] = {'items': ['cccccc1']}
    evil['settings']['gcid'] = 'evil'; evil['updatedAt'] += 10**7
    drive.files[list(drive.files)[0]] = json.dumps(evil).replace('"plans": {', '"plans": {"__proto__": {"items": ["cccccc1"]},', 1)
    pg.click('#sync'); pg.wait_for_timeout(800)
    pg.click('nav [data-a=tab][data-v=ex]'); pg.wait_for_timeout(100)
    check('remote XSS not executed, shown as text', pg.evaluate('window.__pwn') is None and 'onerror' in pg.inner_text('#view'))
    check('no prototype pollution from remote', pg.evaluate('({}).items') is None)
    check('remote cannot change local Client ID', pg.evaluate('__gym.S.settings.gcid') == CID)

    # 6. expired token -> no API calls, chip asks to reconnect; reconnect without consent prompt
    pg.evaluate("1")
    n = len(drive.calls)
    pg.evaluate("(()=>{const b=document.createElement('button');b.dataset.a='close';document.body.appendChild(b);b.click();b.remove();})()")
    pg.evaluate("document.querySelector('#sync')")
    pg.evaluate("Date.now=((orig)=>()=>orig()+2*3600*1000)(Date.now)")
    pg.click('nav [data-a=tab][data-v=cal]'); pg.evaluate("__gym.S.updatedAt=1"); pg.wait_for_timeout(4500)
    check('expired token: no background calls', len(drive.calls) == n)
    pg.click('#sync'); pg.wait_for_timeout(800)
    check('reconnect without forcing consent', pg.evaluate('__gis.prompt') == '' and len(drive.calls) > n)

    # 7. denied consent handled
    pg.evaluate('__gis.deny=true'); pg.evaluate("Date.now=((orig)=>()=>orig()+4*3600*1000)(Date.now)")
    pg.click('#sync'); pg.wait_for_timeout(400)
    check('denied consent shows message, no crash', 'נכשלה' in pg.inner_text('#sync') and not errs)
    pg.evaluate('__gis.deny=false')

    # 8. disconnect revokes
    pg.click('#sync'); pg.wait_for_timeout(700)
    pg.click('[data-a=settings]'); pg.click('[data-a=cloud-off]'); pg.click('[data-a=confirm-ok]'); pg.wait_for_timeout(200)
    check('disconnect revokes token', pg.evaluate('__gis.revoked') >= 1 and pg.inner_text('#sync') == '☁️ סנכרן')

    check('all Drive calls authenticated', drive.bad_auth == 0)
    check('no requests to unexpected hosts', not external)
    if external: print(external[:5])
    check('no JS errors', not errs)
    if errs: print(errs)
    pg.screenshot(path='tests/out/cloud.png')
    b.close()
print(f'\n{len(P)} passed, {len(F)} failed')
