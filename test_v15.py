"""v1.5 tests: daily tab, edit set / delete workout, RPE, body metrics, Spotify, backup reminder, tap targets, CSP, update checks.
Usage: python tests/test_v15.py "$PWD/index.html"   (the update test serves a temp copy on localhost:8766)"""
import os, sys, json, shutil, subprocess, tempfile, time
os.makedirs('tests/out', exist_ok=True)
from playwright.sync_api import sync_playwright
SRC = sys.argv[1]; URL = 'file://' + SRC
P, F = [], []
def check(n, c):
    (P if c else F).append(n); print(('PASS ' if c else 'FAIL ') + n)

SEED = """(()=>{const S=__gym.S;
 const mk=(id,group,name,x)=>Object.assign({id,group,name,sets:2,w:50,r:10,rest:30,machine:'',notes:'',km:0,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0},x||{});
 S.exercises=[mk('wwwwww1','cardio','הליכון',{sets:1,min:0,km:2}),mk('cccccc1','chest','לחיצת חזה',{w:60})];
 const L=(ex,w,rpe)=>({exId:ex.id,name:ex.name,group:ex.group,machine:'',notes:'',rest:30,hrB:0,hrA:0,role:'',skipped:false,
   t:{sets:ex.sets,w:ex.w,r:10,km:ex.km,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0},
   sets:Array.from({length:ex.sets},()=>ex.group==='cardio'?{w:0,r:0,km:2,min:20,inc:0,spd:5,iv:0,rpe:0,at:1}:{w,r:10,km:0,min:0,inc:0,spd:0,iv:0,rpe,at:1})});
 const [w,c]=S.exercises,t0=Date.now()-30*86400000;
 S.logs['2026-10-10']={startedAt:t0,finishedAt:t0+40*60000,items:[L(w),L(c,60,7)]};
 S.logs['2026-10-17']={startedAt:t0+7*86400000,finishedAt:t0+7*86400000+42*60000,items:[L(w),L(c,60,9)]};
 const d=new Date(),k=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
 S.plans[k]={name:'',warm:'',cool:'',items:['cccccc1']};S.settings.lastBackup=0;S.settings.backupSnooze=0;
 S.updatedAt=Date.now();return k;})()"""
def act(pg, a, v=''):
    pg.evaluate(f'(()=>{{const b=document.createElement("button");b.dataset.a="{a}";b.dataset.v="{v}";document.body.appendChild(b);b.click();b.remove();}})()')
def ff(pg): pg.evaluate('__gym.S.active.endsAt=Date.now()-1'); pg.wait_for_timeout(450)
def fresh(b):
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, accept_downloads=True); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(300); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(300)
    return ctx, pg, errs

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox'])
    ctx, pg, errs = fresh(b)
    check('daily tab: empty state before any workout', 'עוד אין אימונים' in (pg.click('nav [data-a=tab][data-v=day]') or pg.inner_text('#view')))
    k = pg.evaluate(SEED); pg.click('nav [data-a=tab][data-v=cal]'); pg.wait_for_timeout(150)

    # ---- backup reminder ----
    check('backup reminder shown (old workouts, never backed up)', 'עדיין לא שמרת גיבוי' in pg.inner_text('#view'))
    pg.click('[data-a=bk-snooze]'); pg.wait_for_timeout(100)
    check('snooze hides reminder', 'שמרת גיבוי' not in pg.inner_text('#view'))
    pg.evaluate('__gym.S.settings.backupSnooze=0'); act(pg, 'tab', 'cal'); pg.wait_for_timeout(100)
    with pg.expect_download(): pg.click('.remind [data-a=bk-file]')
    pg.wait_for_timeout(200)
    check('saving backup records date and clears reminder', pg.evaluate('__gym.S.settings.lastBackup') > 0 and 'גיבוי' not in pg.inner_text('.card'))

    # ---- tap targets ----
    small = pg.evaluate("""[...document.querySelectorAll('header button, .calhead .btn, nav button')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&(r.width<44||r.height<44)}).map(e=>e.textContent.trim())""")
    check('header / month arrows / nav targets >= 44px', small == [])

    # ---- Spotify ----
    a = pg.locator('.today a.music')
    check('Spotify button opens liked songs by default, new tab, noopener', a.get_attribute('href') == 'https://open.spotify.com/collection/tracks' and a.get_attribute('target') == '_blank' and 'noopener' in a.get_attribute('rel'))
    pg.click('[data-a=settings]')
    for bad in ['javascript:alert(1)', 'http://open.spotify.com/playlist/abc', 'https://evil.com/open.spotify.com/playlist/x', 'https://open.spotify.com/playlist/abc"><img src=x>']:
        pg.fill('#s-spot', bad); pg.click('[data-a=set-save]'); pg.wait_for_timeout(80)
    check('invalid Spotify links rejected', pg.evaluate('__gym.S.settings.spotify') == '')
    good = 'https://open.spotify.com/playlist/37i9dQZF1DX76Wlfdnj7AP?si=abc123'
    pg.fill('#s-spot', good); pg.click('[data-a=set-save]'); pg.wait_for_timeout(150)
    check('valid playlist link saved and used', pg.evaluate('__gym.S.settings.spotify') == good and pg.get_attribute('.today a.music', 'href') == good)
    check('stored invalid Spotify link sanitized', pg.evaluate("__gym.sanState({settings:{spotify:'javascript:x'}}).settings.spotify") == '')

    # ---- RPE + hold suggestion ----
    act(pg, 'start', k); pg.wait_for_timeout(200)
    check('workout shows music button', pg.locator('#view a.music').count() == 1)
    check('high effort last time -> hold suggestion instead of increase', 'המאמץ היה 9/10' in pg.inner_text('#view') and 'מומלץ לעלות' not in pg.inner_text('#view'))
    check('RPE selector on current set', pg.locator('#in-rpe-0').count() == 1)
    pg.select_option('#in-rpe-0', '8'); pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    check('RPE saved with set', pg.evaluate(f"__gym.S.logs['{k}'].items[0].sets[0].rpe") == 8)
    check('done row shows RPE + edit button', '· 8' in pg.inner_text('.wi.cur') and pg.locator('.wi.cur [data-a=edit-set]').count() == 1)
    ff(pg); pg.click('[data-a=mark]'); pg.wait_for_timeout(400)
    check('finish -> daily tab', pg.evaluate('__gym.ui.tab') == 'day')
    txt = pg.inner_text('#view')
    check('daily tab shows summary + average effort', 'סיכום האימון' in txt and 'מאמץ ממוצע' in txt)
    check('nav has 5 tabs incl. daily', pg.locator('nav button').count() == 5 and pg.locator('nav [data-v=day].on').count() == 1)

    # ---- edit set ----
    pg.click(f'[data-a=edit-set][data-v="{k}|0|0"]'); pg.wait_for_timeout(150)
    pg.fill('#es-w', '62.5'); pg.fill('#es-r', '8'); pg.select_option('#es-rpe', '10'); pg.click('[data-a=edit-set-ok]'); pg.wait_for_timeout(200)
    st = pg.evaluate(f"__gym.S.logs['{k}'].items[0].sets[0]")
    check('edit set saves weight, reps, effort', st['w'] == 62.5 and st['r'] == 8 and st['rpe'] == 10)
    check('summary reflects edit', '62.5 ק״ג × 8' in pg.inner_text('#view'))
    pg.click(f'[data-a=edit-set][data-v="{k}|0|0"]'); pg.fill('#es-w', '99999'); pg.click('[data-a=edit-set-ok]'); pg.wait_for_timeout(150)
    check('edit values clamped', pg.evaluate(f"__gym.S.logs['{k}'].items[0].sets[0].w") == 1000)
    act(pg, 'edit-set', '2026-99-99|0|0'); act(pg, 'edit-set', f'{k}|9|9')
    check('tampered edit references ignored', not pg.locator('#es-w').is_visible() if pg.locator('#es-w').count() else True)

    # ---- daily navigation ----
    pg.click('[data-a=day-nav][data-v="-1"]'); pg.wait_for_timeout(150)
    check('previous-workout arrow', pg.evaluate('__gym.ui.dayK') == '2026-10-17')
    pg.select_option('#dayPick', '2026-10-10'); pg.wait_for_timeout(150)
    check('date picker selects workout', pg.evaluate('__gym.ui.dayK') == '2026-10-10' and '10 באוקטובר' in pg.inner_text('#view'))

    # ---- delete workout ----
    pg.click('[data-a=log-del]'); pg.click('[data-a=confirm-ok]'); pg.wait_for_timeout(200)
    check('delete workout removes log, keeps others', pg.evaluate("!__gym.S.logs['2026-10-10'] && !!__gym.S.logs['2026-10-17']"))
    act(pg, 'log-del', '<script>'); check('tampered delete ignored', pg.evaluate('Object.keys(__gym.S.logs).length') == 2)

    # ---- body metrics ----
    pg.click('nav [data-a=tab][data-v=sum]'); pg.wait_for_timeout(150)
    check('body metrics card with empty-state hint', 'מדדי גוף' in pg.inner_text('#view'))
    pg.click('[data-a=body-add]'); pg.fill('#bd-d', '2026-10-01'); pg.fill('#bd-w', '84.5'); pg.fill('#bd-bf', '22'); pg.fill('#bd-waist', '95'); pg.click('[data-a=body-save]'); pg.wait_for_timeout(150)
    pg.click('[data-a=body-add]'); pg.fill('#bd-w', '9999'); pg.click('[data-a=body-save]'); pg.wait_for_timeout(100)
    check('invalid body value rejected', pg.locator('#bd-w').count() == 1 and len(pg.evaluate('__gym.S.body')) == 1)
    pg.fill('#bd-w', '82'); pg.fill('#bd-bf', '20.5'); pg.click('[data-a=body-save]'); pg.wait_for_timeout(200)
    txt = pg.inner_text('#view').replace('\u200e', '')
    check('body: latest values + change', '82 ק״ג' in txt and '▼ -2.5 ק״ג' in txt and '▼ -1.5 %' in txt)
    check('body: weight & fat charts', pg.locator('svg.chart').count() >= 2 and pg.locator('#tip-bw').count() == 1 and pg.locator('#tip-bf').count() == 1)
    pg.click('details.tbl:has-text("כל המדידות") summary'); pg.click('[data-a=body-del][data-v="2026-10-01"]'); pg.click('[data-a=confirm-ok]'); pg.wait_for_timeout(150)
    check('delete measurement', len(pg.evaluate('__gym.S.body')) == 1)
    sb = pg.evaluate("__gym.sanState({body:[{d:'2026-01-01',w:80},{d:'bad',w:70},{d:'2026-01-01',w:81},{d:'2026-01-02',w:-5},{d:'__proto__',w:1}]}).body")
    check('body data sanitized (dates, ranges, duplicates)', sb == [{'d': '2026-01-01', 'w': 81}])

    # ---- version / update button (file:// = no service worker) ----
    pg.click('[data-a=settings]')
    check('version shown in settings', 'גרסה 1.5.0' in pg.inner_text('#md'))
    pg.click('[data-a=check-upd]'); pg.wait_for_timeout(150)
    check('update check without SW explains', 'באפליקציה המותקנת' in pg.inner_text('#toast'))
    check('no JS errors (main)', not errs)
    if errs: print(errs)
    pg.screenshot(path='tests/out/v15_settings.png', full_page=True)
    ctx.close()

    # ---- installed app: CSP + update detection on localhost ----
    tmp = tempfile.mkdtemp(); root = os.path.dirname(SRC)
    for f in os.listdir(root):
        if os.path.isfile(os.path.join(root, f)): shutil.copy(os.path.join(root, f), tmp)
    srv = subprocess.Popen(['python3', '-m', 'http.server', '8766'], cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        ctx2 = b.new_context(viewport={'width': 390, 'height': 844}); pg2 = ctx2.new_page(); e2 = []; csp = []
        pg2.on('pageerror', lambda e: e2.append(str(e)))
        pg2.on('console', lambda m: ('Content Security Policy' in m.text or 'Refused to' in m.text) and csp.append(m.text))
        pg2.goto('http://localhost:8766/'); pg2.wait_for_timeout(1500)
        check('CSP meta present in installed app', pg2.locator('meta[http-equiv="Content-Security-Policy"]').count() == 1)
        pg2.evaluate(SEED); pg2.reload(); pg2.wait_for_timeout(800)
        for t in ['cal', 'work', 'day', 'ex', 'sum']:
            pg2.click(f'nav [data-a=tab][data-v={t}]'); pg2.wait_for_timeout(120)
        check('app runs under CSP with no violations', not csp and not e2)
        if csp or e2: print(csp[:3], e2[:3])
        check('SW registered with updateViaCache none', pg2.evaluate("navigator.serviceWorker.getRegistration().then(r=>r&&r.updateViaCache)") == 'none')
        s = open(os.path.join(tmp, 'sw.js')).read().replace("gym-v1.5.0", "gym-v1.5.0-test")
        open(os.path.join(tmp, 'sw.js'), 'w').write(s)
        pg2.click('[data-a=settings]'); pg2.click('[data-a=check-upd]'); pg2.wait_for_timeout(3000)
        check('manual check finds new version -> blue bar', pg2.evaluate("document.getElementById('upd').classList.contains('show')"))
        pg2.click('#upd [data-a=reload-app]'); pg2.wait_for_timeout(2000)
        check('refresh activates new version', pg2.evaluate("caches.keys().then(k=>k.includes('gym-v1.5.0-test'))"))
        s = open(os.path.join(tmp, 'sw.js')).read().replace("gym-v1.5.0-test", "gym-v1.5.0-test2")
        open(os.path.join(tmp, 'sw.js'), 'w').write(s)
        pg2.evaluate("Date.now=((o)=>()=>o()+120000)(Date.now)")
        pg2.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
        pg2.wait_for_timeout(3000)
        check('returning to the app checks for updates automatically', pg2.evaluate("document.getElementById('upd').classList.contains('show')"))
        ctx2.close()
    finally:
        srv.terminate(); shutil.rmtree(tmp, ignore_errors=True)
    b.close()
print(f'\n{len(P)} passed, {len(F)} failed'); sys.exit(1 if F else 0)
