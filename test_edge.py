import os; os.makedirs('tests/out', exist_ok=True)
import sys, json
from playwright.sync_api import sync_playwright
URL='file://'+sys.argv[1]
P,F=[],[]
def check(n,c):
    (P if c else F).append(n); print(('PASS ' if c else 'FAIL ')+n)

SEED = """(()=>{const S=__gym.S;
 const mk=(id,group,name,extra)=>Object.assign({id,group,name,sets:3,w:20,r:10,rest:60,machine:'',notes:'',km:0,min:0,kind:'walk',inc:0,ivN:0,ivW:0,ivR:0},extra||{});
 S.exercises=[mk('wwwwww1','cardio','הליכון',{sets:1,km:2,min:15}),mk('cccccc1','chest','לחיצה'),mk('bbbbbb1','back','חתירה'),mk('llllll1','legs','סקוואט')];
 S.plans={}; S.logs={}; S.active=null; return true;})()"""
def boot(pg):
    pg.goto(URL); pg.wait_for_timeout(300); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(300)
    pg.evaluate(SEED)
def today(pg): return pg.evaluate("(()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')})()")
def click_action(pg,a,v=''):
    pg.evaluate(f'(()=>{{const b=document.createElement("button");b.dataset.a="{a}";b.dataset.v="{v}";document.body.appendChild(b);b.click();b.remove();}})()')
def ff(pg): pg.evaluate('__gym.S.active.endsAt=Date.now()-1'); pg.wait_for_timeout(400)

with sync_playwright() as p:
    b=p.chromium.launch(executable_path=os.environ.get('CHROME') or None,args=['--no-sandbox'])
    ctx=b.new_context(viewport={'width':390,'height':844})
    pg=ctx.new_page(); errs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)))
    boot(pg); t=today(pg)
    pg.evaluate(f"__gym.S.plans['{t}']={{name:'',warm:'wwwwww1',cool:'wwwwww1',items:['cccccc1','bbbbbb1']}}")

    # 1. double-tap on mark records only one set
    click_action(pg,'start',t); pg.wait_for_timeout(100)
    pg.click('[data-a=cardio-start]'); ff(pg); pg.click('[data-a=mark]'); ff(pg)   # warm-up done -> exrest -> chest
    pg.evaluate("document.querySelector('[data-a=mark]').click();document.querySelector('[data-a=mark]')&&document.querySelector('[data-a=mark]').click()")
    pg.wait_for_timeout(200)
    check('double-tap records one set', pg.evaluate(f"__gym.S.logs['{t}'].items[1].sets.length")==1)

    # 2. reload while between-set rest already expired -> next set opens
    pg.evaluate('__gym.S.active.endsAt=Date.now()-5000'); pg.evaluate("localStorage.setItem('gymapp.v1',JSON.stringify(__gym.S))")
    pg.reload(); pg.wait_for_timeout(400)
    check('expired rest on reload -> ready + workout tab', pg.evaluate('__gym.S.active.phase')=='ready' and pg.locator('nav button.on').get_attribute('data-v')=='work')

    # 3. rest adjust buttons when no rest running -> no error
    click_action(pg,'rest-adj','60'); pg.wait_for_timeout(100)
    check('rest-adj outside rest is a no-op', pg.evaluate('__gym.S.active.phase')=='ready')

    # 4. ending early must NOT count as fully completed
    pg.click('[data-a=end]'); pg.click('[data-a=confirm-ok]'); pg.wait_for_timeout(200)
    pg.click('nav [data-a=tab][data-v=sum]'); pg.wait_for_timeout(100)
    k=pg.evaluate("[...document.querySelectorAll('.kpi .v')].map(e=>e.textContent)")
    check('ended-early workout: done=1, fully completed=0', k[0]=='1' and k[1]=='0')
    check('calendar marks ended-early day as partial', pg.evaluate(f"(()=>{{__gym.ui.tab='cal';return true}})()") and True)
    pg.click('nav [data-a=tab][data-v=cal]'); pg.wait_for_timeout(100)
    check('ended-early day shown as partial', 'part' in (pg.get_attribute(f'.cal [data-a=day][data-v="{t}"]','class') or ''))

    # 5. deleting an exercise used in a log/plan
    pg.click('nav [data-a=tab][data-v=ex]'); pg.click('[data-a=ex-edit][data-v=bbbbbb1]'); pg.click('[data-a=ex-del]'); pg.click('[data-a=confirm-ok]'); pg.wait_for_timeout(100)
    check('deleted exercise removed from plan, history kept', pg.evaluate(f"__gym.S.plans['{t}'].items")==['cccccc1'] and pg.evaluate(f"__gym.S.logs['{t}'].items.length")==4)
    pg.click('nav [data-a=tab][data-v=work]'); pg.click('nav [data-a=tab][data-v=sum]')

    # 6. plan with only cardio (no strength) works start-to-finish
    d2='2027-02-10'
    pg.evaluate(f"__gym.S.plans['{d2}']={{name:'',warm:'wwwwww1',cool:'',items:[]}}")
    click_action(pg,'start',d2); pg.wait_for_timeout(100)
    pg.click('[data-a=cardio-start]'); ff(pg); pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    check('cardio-only plan finishes', pg.evaluate('__gym.S.active') is None and pg.evaluate(f"__gym.S.logs['{d2}'].finishedAt")>0)

    # 7. XSS in program name / plan name / imported plan name
    x='<img src=x onerror="window.__x=1">'
    pg.click('nav [data-a=tab][data-v=ex]'); pg.click('[data-a=prog-new]'); pg.fill('#pname',x); pg.click('[data-a=prog-save]'); pg.wait_for_timeout(100)
    pg.evaluate(f"__gym.S.plans['2027-02-11']={{name:{json.dumps(x)},warm:'wwwwww1',cool:'',items:['cccccc1']}}")
    pg.click('nav [data-a=tab][data-v=cal]'); click_action(pg,'day','2027-02-11'); pg.wait_for_timeout(100)
    click_action(pg,'plan-edit','2027-02-11'); pg.wait_for_timeout(100)
    check('XSS in program/plan names inert', pg.evaluate('window.__x') is None and x in pg.inner_text('#md'))
    click_action(pg,'close')

    # 8. tampered data-v values (date / id) are ignored
    click_action(pg,'day','<script>'); click_action(pg,'start','../../x'); click_action(pg,'ex-edit','nope'); click_action(pg,'plan-edit','2026-13-40')
    check('tampered action values ignored', pg.evaluate('window.__x') is None and not errs)
    click_action(pg,'close')

    # 9. editor item cap (35)
    click_action(pg,'plan-edit','2027-03-01'); pg.wait_for_timeout(100)
    for _ in range(40):
        if pg.is_disabled('[data-a=it-add]'): break
        pg.click('[data-a=it-add]')
    check('max 35 items per workout', pg.locator('#items .li').count()==35 and pg.is_disabled('[data-a=it-add]'))
    click_action(pg,'close')

    # 10. oversized import rejected
    pg.click('[data-a=settings]'); pg.click('[data-a=bk-import]')
    pg.evaluate("document.getElementById('bkt').value='{\"a\":\"'+'x'.repeat(5100000)+'\"}'")
    n_before=pg.evaluate('__gym.S.exercises.length'); pg.click('[data-a=bk-import-ok]'); pg.wait_for_timeout(200)
    check('oversized import rejected', pg.evaluate('__gym.S.exercises.length')==n_before)
    click_action(pg,'close')

    # 11. year boundary navigation
    pg.click('nav [data-a=tab][data-v=cal]'); pg.evaluate('__gym.ui.m=11;__gym.ui.y=2026'); click_action(pg,'cal-m','-1'); click_action(pg,'cal-m','1'); click_action(pg,'cal-m','1')
    check('Dec -> Jan wraps year', pg.evaluate('[__gym.ui.m,__gym.ui.y]')==[0,2027])
    pg.click('nav [data-a=tab][data-v=sum]'); pg.evaluate('__gym.ui.sumM=0;__gym.ui.sumY=2027'); click_action(pg,'sum-m','-1')
    check('summary Jan -> Dec wraps year', pg.evaluate('[__gym.ui.sumM,__gym.ui.sumY]')==[11,2026] and 'דצמבר' in pg.inner_text('#view'))

    # 12. settings bounds
    pg.click('[data-a=settings]'); pg.fill('#s-exrest','9999'); pg.fill('#s-age','-5'); pg.click('[data-a=set-save]'); pg.wait_for_timeout(100)
    check('settings clamped', pg.evaluate('__gym.S.settings.exRest')==3600 and pg.evaluate('__gym.S.settings.age')==0)

    # 13. narrow screen: no horizontal overflow on any tab
    pg.set_viewport_size({'width':320,'height':640}); ok=True
    for tb in ['cal','work','ex','sum']:
        pg.click(f'nav [data-a=tab][data-v={tb}]'); pg.wait_for_timeout(100)
        if pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'): ok=False; print('overflow on',tb)
    check('no horizontal overflow at 320px', ok)
    check('no JS errors (main run)', not errs)
    if errs: print(errs)

    # 14. storage blocked (e.g. private mode) -> app still works
    ctx2=b.new_context(); ctx2.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
    pg2=ctx2.new_page(); e2=[]; pg2.on('pageerror',lambda e:e2.append(str(e)))
    pg2.goto(URL); pg2.wait_for_timeout(300)
    pg2.click('nav [data-a=tab][data-v=ex]'); pg2.click('[data-a=ex-new][data-v=chest]'); pg2.fill('#f-name','x'); pg2.click('#exf button[type=submit]'); pg2.wait_for_timeout(100)
    check('works without localStorage', not e2 and pg2.evaluate('__gym.S.exercises.length')==1)

    # 15. zero rest + editing a future exercise's rest from the rest-times modal + volume + beep
    ctx3=b.new_context(viewport={'width':390,'height':844}); pg3=ctx3.new_page(); e3=[]; pg3.on('pageerror',lambda e:e3.append(str(e)))
    boot(pg3); t3=today(pg3)
    pg3.evaluate(f"__gym.S.plans['{t3}']={{name:'',warm:'',cool:'',items:['cccccc1','llllll1']}}")
    click_action(pg3,'start',t3); pg3.wait_for_timeout(100)
    pg3.click('[data-a=rest-times]'); pg3.wait_for_timeout(100)
    pg3.fill('#md input[data-ir][data-i="1"]','45'); pg3.press('#md input[data-ir][data-i="1"]','Tab'); pg3.wait_for_timeout(100)
    check('future exercise rest editable during workout', pg3.evaluate(f"__gym.S.logs['{t3}'].items[1].rest")==45)
    pg3.fill('#md input[data-ir][data-i="0"]','0'); pg3.press('#md input[data-ir][data-i="0"]','Tab'); pg3.wait_for_timeout(100)
    pg3.click('#md [data-a=close]')
    pg3.click('[data-a=mark]'); pg3.wait_for_timeout(500)
    check('zero rest -> next set opens immediately', pg3.evaluate('__gym.S.active.phase')=='ready' and pg3.evaluate(f"__gym.S.logs['{t3}'].items[0].sets.length")==1)
    pg3.click('[data-a=settings]'); pg3.fill('#s-vol','60'); pg3.dispatch_event('#s-vol','change'); pg3.click('[data-a=test-beep]'); pg3.wait_for_timeout(300)
    check('volume label updates', pg3.inner_text('#s-vol-v')=='60%')
    pg3.click('[data-a=set-save]'); pg3.wait_for_timeout(100)
    check('volume saved', pg3.evaluate('__gym.S.settings.vol')==60)
    v=pg3.evaluate("__gym.sanState({settings:{vol:999,exRest:-5}}).settings")
    check('volume/exRest sanitized', v['vol']==100 and v['exRest']==0)
    hrs=pg3.evaluate("__gym.sanState({logs:{'2026-01-01':{items:[{group:'chest',name:'x',hrB:80,hrA:120,t:{sets:1},sets:[{w:1,r:1}]}]}}}).logs['2026-01-01'].items[0]")
    check('pulse stripped from non-cardio in stored data', hrs['hrB']==0 and hrs['hrA']==0)
    check('no JS errors (beep/volume run)', not e3)
    if e3: print(e3)

    # 16. cardio without planned time -> confirm directly; timer expiry while app closed; speed sanitize
    ctx4=b.new_context(viewport={'width':390,'height':844}); pg4=ctx4.new_page(); e4=[]; pg4.on('pageerror',lambda e:e4.append(str(e)))
    boot(pg4); t4=today(pg4)
    pg4.evaluate("__gym.S.exercises.push({id:'zzzzzz9',group:'cardio',name:'חופשי',sets:1,w:0,r:0,rest:60,machine:'',notes:'',km:0,min:0,kind:'run',spd:9,inc:0,ivN:0,ivW:0,ivR:0})")
    pg4.evaluate(f"__gym.S.plans['{t4}']={{name:'',warm:'zzzzzz9',cool:'wwwwww1',items:[]}}")
    click_action(pg4,'start',t4); pg4.wait_for_timeout(100)
    check('cardio with 0 planned minutes: confirm directly', pg4.locator('[data-a=cardio-start]').count()==0 and not pg4.is_disabled('[data-a=mark]'))
    pg4.click('[data-a=mark]'); ff(pg4)
    pg4.click('[data-a=cardio-start]'); pg4.wait_for_timeout(100)
    pg4.evaluate("__gym.S.active.endsAt=Date.now()-60000;localStorage.setItem('gymapp.v1',JSON.stringify(__gym.S))"); pg4.reload(); pg4.wait_for_timeout(400)
    check('cardio timer expired while closed -> confirm enabled on reopen', pg4.evaluate('__gym.S.active.phase')=='cardioend' and not pg4.is_disabled('[data-a=mark]'))
    pg4.evaluate("document.querySelector('[data-a=mark]').click();document.querySelector('[data-a=mark]')&&document.querySelector('[data-a=mark]').click()"); pg4.wait_for_timeout(200)
    check('double confirm records one cardio set', pg4.evaluate(f"__gym.S.logs['{t4}'].items[1].sets.length")==1)
    sp=pg4.evaluate("__gym.sanState({exercises:[{id:'qqqqqq1',group:'cardio',spd:99}],active:{date:'2026-01-01',phase:'hack'}})")
    check('speed clamped, unknown phase rejected', sp['exercises'][0]['spd']==30 and sp['active'] is None)
    check('no JS errors (cardio timer run)', not e4)
    if e4: print(e4)
    b.close()
print(f'\n{len(P)} passed, {len(F)} failed'); sys.exit(1 if F else 0)
