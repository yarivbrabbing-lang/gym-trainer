"""v1.4 tests: free navigation/skip + colors, workout duration timer, daily summary, comparisons with charts.
Usage: python tests/test_v14.py "$PWD/index.html" """
import os, sys, time
os.makedirs('tests/out', exist_ok=True)
from playwright.sync_api import sync_playwright
URL = 'file://' + sys.argv[1]
P, F = [], []
def check(n, c):
    (P if c else F).append(n); print(('PASS ' if c else 'FAIL ') + n)

SEED = """(()=>{const S=__gym.S;
 const mk=(id,group,name,x)=>Object.assign({id,group,name,sets:2,w:50,r:10,rest:40,machine:'',notes:'',km:0,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0},x||{});
 S.exercises=[mk('wwwwww1','cardio','הליכון',{sets:1,min:0,km:2}),mk('cccccc1','chest','לחיצת חזה',{w:60}),mk('llllll1','legs','סקוואט',{w:80}),mk('bbbbbb1','back','חתירה<b>',{w:40})];
 const L=(ex,w,n,hb,ha)=>({exId:ex.id,name:ex.name,group:ex.group,machine:'',notes:'',rest:40,hrB:hb||0,hrA:ha||0,role:'',skipped:false,
   t:{sets:ex.sets,w:ex.w,r:10,km:ex.km,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0},
   sets:Array.from({length:n},()=>ex.group==='cardio'?{w:0,r:0,km:2,min:20,inc:0,spd:5,iv:0,at:1}:{w,r:10,km:0,min:0,inc:0,spd:0,iv:0,at:1})});
 const [w,c,l,b]=S.exercises,base=Date.now()-20*86400000;
 S.logs['2026-10-20']={startedAt:base,finishedAt:base+50*60000,items:[L(w,0,1,82,150),L(c,55,2),L(l,75,2),L(w,0,1,0,148)]};
 S.logs['2026-10-27']={startedAt:base+7*86400000,finishedAt:base+7*86400000+45*60000,items:[L(w,0,1,80,146),L(c,57.5,2),L(l,80,2),L(w,0,1,0,144)]};
 const d=new Date(),k=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
 S.plans[k]={name:'',warm:'wwwwww1',cool:'wwwwww1',items:['cccccc1','llllll1','bbbbbb1']};
 S.updatedAt=Date.now();return k;})()"""
def act(pg, a, v=''):
    pg.evaluate(f'(()=>{{const b=document.createElement("button");b.dataset.a="{a}";b.dataset.v="{v}";document.body.appendChild(b);b.click();b.remove();}})()')
def ff(pg): pg.evaluate('__gym.S.active.endsAt=Date.now()-1'); pg.wait_for_timeout(450)
A = lambda pg, e: pg.evaluate('__gym.S.active' + e)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox'])
    ctx = b.new_context(viewport={'width': 390, 'height': 844})
    pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(300); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(300)
    k = pg.evaluate(SEED)
    act(pg, 'start', k); pg.wait_for_timeout(200)
    L = lambda e: pg.evaluate(f"__gym.S.logs['{k}']" + e)

    # ---- duration timer ----
    pg.evaluate(f"__gym.S.logs['{k}'].startedAt=Date.now()-65000"); pg.wait_for_timeout(400)
    check('workout duration timer shows elapsed time', pg.inner_text('#wdur') in ('1:05', '1:06'))
    pg.wait_for_timeout(1100)
    check('duration timer is live', pg.inner_text('#wdur') in ('1:06', '1:07', '1:08'))

    # ---- unlocked + jump ----
    check('no locked exercises; 4 switch buttons', pg.locator('.wi.lock').count() == 0 and pg.locator('[data-a=go-ex]').count() == 4)
    pg.click('[data-a=go-ex][data-v="1"]'); pg.wait_for_timeout(200)
    check('jump: current exercise changes', A(pg, '.idx') == 1)
    check('skipped exercise colored orange', 'skip' in pg.get_attribute('.wi:nth-of-type(1)', 'class') if False else pg.locator('.wi.skip').count() == 1 and L('.items[0].skipped'))
    check('skip pill shown', 'דולג' in pg.inner_text('.wi.skip'))
    pg.click('[data-a=skip-ex]'); pg.wait_for_timeout(200)
    check('skip button -> next pending (legs), chest skipped', A(pg, '.idx') == 2 and L('.items[1].skipped') and pg.locator('.wi.skip').count() == 2)

    # ---- switch requested during rest: rest unchanged, applied at its end ----
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    dur0 = A(pg, '.dur'); end0 = A(pg, '.endsAt')
    check('after set: normal set rest', A(pg, '.phase') == 'rest' and dur0 == 40)
    pg.click('[data-a=go-ex][data-v="3"]'); pg.wait_for_timeout(200)
    check('switch during rest is queued, rest timing unchanged', A(pg, '.next') == 3 and A(pg, '.dur') == dur0 and A(pg, '.endsAt') == end0 and A(pg, '.idx') == 2)
    check('queued exercise highlighted', 'בסיום המנוחה' in pg.inner_text('#view'))
    ff(pg)
    check('rest ends -> queued exercise opens, legs marked skipped', A(pg, '.idx') == 3 and A(pg, '.phase') == 'ready' and L('.items[2].skipped'))

    # ---- finish back -> exercise rest -> next pending; queue during exercise rest ----
    pg.click('[data-a=mark]'); ff(pg); pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    check('all sets done -> exercise rest (not finish while others pending)', A(pg, '.phase') == 'exrest' and A(pg, '.dur') == 600)
    check('done (not skipped) exercise stays red', pg.locator('.wi.done:not(.wasskip)').count() == 1)
    pg.click('[data-a=go-ex][data-v="0"]'); pg.wait_for_timeout(200)
    check('choose next during exercise rest', A(pg, '.next') == 0 and A(pg, '.dur') == 600)
    ff(pg)
    check('exercise rest ends -> chosen exercise opens', A(pg, '.idx') == 0)
    pg.fill('#hr-b-0', '76'); pg.press('#hr-b-0', 'Tab')
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    check('skipped exercise completed -> green', pg.locator('.wi.done.wasskip').count() == 1 and 'אחרי דילוג' in pg.inner_text('.wi.wasskip'))
    ff(pg)
    check('next pending after warm-up = chest', A(pg, '.idx') == 1)
    pg.click('[data-a=mark]'); ff(pg); pg.click('[data-a=mark]'); pg.wait_for_timeout(200); ff(pg)
    check('then legs (partly done before)', A(pg, '.idx') == 2)
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    check('legs completed after 2nd set', L('.items[2].sets.length') == 2)
    ff(pg)
    check('then cool-down', A(pg, '.idx') == 4)
    pg.click('[data-a=mark]'); pg.wait_for_timeout(400)
    check('workout finishes only when everything is done', pg.evaluate('__gym.S.active') is None and L('.finishedAt') > 0)
    pg.fill('#hr-a-4', '140'); pg.press('#hr-a-4', 'Tab'); pg.wait_for_timeout(200)

    # ---- daily summary ----
    txt = pg.inner_text('#view')
    check('daily summary shown after finish', '📋 סיכום האימון' in txt and 'משך האימון' in txt)
    check('summary: done count & skipped count', '5/5' in txt and '(3 דולגו)' in txt)
    check('summary compares to previous workout', 'מול 27.10' in txt)
    check('summary: pulse change shown (76 vs 80 = -4)', '▼ -4' in txt or '▼ ‎-4' in txt or '▼ -4' in txt.replace('‎', ''))
    check('summary: per-exercise weight change (chest 60 vs 57.5)', '▲ +2.5 ק״ג' in txt)
    dur_final = L('.finishedAt') - L('.startedAt')
    check('duration stops at finish', abs(dur_final - 65000) < 30000)
    d1 = pg.inner_text('#wdur'); pg.wait_for_timeout(1300)
    check('finished duration no longer ticks', pg.inner_text('#wdur') == d1)
    pg.screenshot(path='tests/out/v14_summary.png', full_page=True)
    pg.click('nav [data-a=tab][data-v=cal]'); act(pg, 'day', k); pg.wait_for_timeout(200)
    pg.click('#md [data-a=day-sum]'); pg.wait_for_timeout(200)
    check('day modal -> workout summary', 'סיכום אימון' in pg.inner_text('#md') and 'פירוט תרגילים' in pg.inner_text('#md'))
    act(pg, 'close')

    # ---- comparisons & charts ----
    pg.click('nav [data-a=tab][data-v=sum]'); pg.wait_for_timeout(300)
    txt = pg.inner_text('#view')
    check('month workout list with summary buttons', 'האימונים החודש' in txt and pg.locator('[data-a=day-sum]').count() >= 1)
    check('comparison section with 4 charts', 'השוואת אימונים' in txt and pg.locator('svg.chart').count() == 4)
    check('pulse chart has legend (2 series)', 'לפני' in pg.inner_text('.lg') and 'אחרי' in pg.inner_text('.lg'))
    check('every chart has a table view', pg.locator('details.tbl').count() == 4)
    pg.locator('#tip-kg').scroll_into_view_if_needed()
    pg.locator('circle.hit[data-c="kg"]').last.dispatch_event('click'); pg.wait_for_timeout(100)
    check('tap on point shows value', 'ק״ג' in pg.inner_text('#tip-kg'))
    pg.select_option('#cmpEx', label='לחיצת חזה · חזה'); pg.wait_for_timeout(200)
    check('exercise progression: chest weight 55 -> 60 (+5)', '▲ +5 ק״ג' in pg.inner_text('#view'))
    keys = pg.evaluate("[...document.querySelectorAll('#cmpA option')].map(o=>o.value)")
    pg.select_option('#cmpA', keys[-1]); pg.wait_for_timeout(200)
    t2 = pg.inner_text('#view')
    check('two-workout comparison table updates', pg.input_value('#cmpA') == keys[-1] and 'משקל מרבי לפי תרגיל' in t2)
    pg.evaluate("(()=>{const s=document.getElementById('cmpA');const o=document.createElement('option');o.value='<x>';s.appendChild(o);s.value='<x>';s.dispatchEvent(new Event('change',{bubbles:true}));})()")
    check('tampered comparison value ignored', pg.input_value('#cmpA') == keys[-1])
    act(pg, 'day-sum', k); pg.wait_for_timeout(200)
    check('names escaped in summary (literal text, no injected tag)', 'חתירה<b>' in pg.inner_text('#md') and pg.evaluate("[...document.querySelectorAll('#md b')].every(x=>!x.textContent.includes('חתירה'))"))
    act(pg, 'close')
    pg.screenshot(path='tests/out/v14_compare.png', full_page=True)

    # ---- cardio running: switching blocked ----
    ctx2 = b.new_context(viewport={'width': 390, 'height': 844}); pg2 = ctx2.new_page(); pg2.on('pageerror', lambda e: errs.append(str(e)))
    pg2.goto(URL); pg2.wait_for_timeout(300); pg2.evaluate('localStorage.clear()'); pg2.reload(); pg2.wait_for_timeout(300)
    k2 = pg2.evaluate(SEED); pg2.evaluate("__gym.S.exercises[0].min=5")
    act(pg2, 'start', k2); pg2.wait_for_timeout(200)
    pg2.click('[data-a=cardio-start]'); pg2.wait_for_timeout(200)
    pg2.click('[data-a=go-ex][data-v="2"]'); pg2.wait_for_timeout(200)
    check('switch blocked while cardio timer runs', pg2.evaluate('__gym.S.active.idx') == 0 and pg2.evaluate('__gym.S.active.phase') == 'cardio')
    check('toast never blocks taps', pg2.evaluate("getComputedStyle(document.getElementById('toast')).pointerEvents") == 'none')
    s = pg2.evaluate("__gym.sanState({logs:{'2026-01-01':{items:[{group:'chest',name:'x',skipped:'yes',t:{sets:1},sets:[{w:1,r:1}]}]}},active:{date:'2026-01-01',phase:'ready',next:999}})")
    check('skipped flag & next index sanitized', s['logs']['2026-01-01']['items'][0]['skipped'] is False and s['active']['next'] is None)
    check('no JS errors', not errs)
    if errs: print(errs)
    b.close()
print(f'\n{len(P)} passed, {len(F)} failed'); sys.exit(1 if F else 0)
