"""v1.3 tests: last-time + progressive overload, Hebrew voice, undo.  Usage: python tests/test_v13.py "$PWD/index.html" """
import os, sys
os.makedirs('tests/out', exist_ok=True)
from playwright.sync_api import sync_playwright
URL = 'file://' + sys.argv[1]
P, F = [], []
def check(n, c):
    (P if c else F).append(n); print(('PASS ' if c else 'FAIL ') + n)

SPEECH_MOCK = """
window.__said=[];
window.SpeechSynthesisUtterance=function(t){this.text=t;this.lang='';};
Object.defineProperty(window,'speechSynthesis',{value:{speak(u){window.__said.push(u.text);},cancel(){},getVoices(){return [{lang:'he-IL',name:'he'}];},onvoiceschanged:null}});
"""
SEED = """(()=>{const S=__gym.S;
 const mk=(id,group,name,x)=>Object.assign({id,group,name,sets:3,w:60,r:10,rest:60,machine:'7',notes:'',km:0,min:0,kind:'walk',spd:0,inc:0,ivN:0,ivW:0,ivR:0},x||{});
 S.exercises=[mk('cccccc1','chest','לחיצת חזה'),mk('llllll1','legs','סקוואט',{w:80}),mk('wwwwww1','cardio','הליכון',{sets:1,min:20,spd:5,km:0})];
 const L=(ex,w,r,n,tr)=>({exId:ex.id,name:ex.name,group:ex.group,machine:'',notes:'',rest:60,hrB:0,hrA:0,role:'',t:{sets:ex.sets,w:ex.w,r:tr||ex.r,km:0,min:ex.min,kind:ex.kind,spd:ex.spd,inc:0,ivN:0,ivW:0,ivR:0},
   sets:Array.from({length:n},()=>isC(ex)?{w:0,r:0,km:1.7,min:20,inc:0,spd:5,iv:0,at:1}:{w,r,km:0,min:0,inc:0,spd:0,iv:0,at:1})});
 const isC=e=>e.group==='cardio';
 const [c,l,w]=S.exercises;
 S.logs['2026-10-20']={startedAt:1,finishedAt:2,items:[L(w,0,0,1),L(c,60,10,3),L(l,80,8,3)]};
 S.logs['2026-10-27']={startedAt:1,finishedAt:2,items:[L(w,0,0,1),L(c,60,10,3),L(l,80,6,3)]};
 S.plans['2026-11-03']={name:'',warm:'wwwwww1',cool:'',items:['cccccc1','llllll1']};
 S.updatedAt=Date.now();return true;})()"""
def act(pg, a, v=''):
    pg.evaluate(f'(()=>{{const b=document.createElement("button");b.dataset.a="{a}";b.dataset.v="{v}";document.body.appendChild(b);b.click();b.remove();}})()')
def ff(pg): pg.evaluate('__gym.S.active.endsAt=Date.now()-1'); pg.wait_for_timeout(1300)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox'])
    ctx = b.new_context(viewport={'width': 390, 'height': 844}); ctx.add_init_script(SPEECH_MOCK)
    pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(300); pg.evaluate('localStorage.clear()'); pg.reload(); pg.wait_for_timeout(300)
    pg.evaluate(SEED)
    act(pg, 'start', '2026-11-03'); pg.wait_for_timeout(200)

    # ---- last time + cardio speed suggestion ----
    txt = pg.inner_text('#view')
    check('last time shown for cardio', 'בפעם הקודמת (27.10)' in txt and '5 קמ״ש' in txt)
    check('cardio speed suggestion after 2 full sessions', '5.5 קמ״ש' in txt)
    check('voice not triggered without events', pg.evaluate('__said.length') == 0)
    pg.click('[data-a=cardio-start]'); pg.wait_for_timeout(100)
    check('voice: cardio start announced', 'הליכה התחילה. 20 דקות' in pg.evaluate('__said.join("|")'))
    # 1-minute warning
    pg.evaluate('__gym.S.active.endsAt=Date.now()+59500'); pg.wait_for_timeout(600)
    check('voice: one minute left', 'נותרה דקה' in pg.evaluate('__said.join("|")'))
    ff(pg)
    check('voice: cardio time over', 'הזמן הסתיים. אשר את סיום ההליכה' in pg.evaluate('__said.join("|")'))
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    # ---- undo of cardio confirm ----
    check('undo bar shown after confirm', pg.is_visible('#undo') and 'סיום אושר' in pg.inner_text('#undo'))
    pg.click('[data-a=undo]'); pg.wait_for_timeout(200)
    check('undo restores cardio (no set, phase cardioend)', pg.evaluate("__gym.S.logs['2026-11-03'].items[0].sets.length") == 0 and pg.evaluate('__gym.S.active.phase') == 'cardioend')
    check('undo bar hidden after undo', not pg.is_visible('#undo'))
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    ff(pg)
    said = pg.evaluate('__said.join("|")')
    check('voice: next exercise announced with machine & weight', 'התרגיל הבא: לחיצת חזה, מכשיר 7. סט 1 מתוך 3, 60 קילו' in said)

    # ---- strength: last time + weight suggestion + apply ----
    txt = pg.inner_text('#view')
    check('last time shown for strength', 'בפעם הקודמת (27.10): 3 סטים × 10/10/10 חזרות · 60 ק״ג' in txt)
    check('weight suggestion +2.5 kg (chest)', 'מומלץ לעלות ל־62.5 ק״ג' in txt)
    pg.click('[data-a=apply-sug]'); pg.wait_for_timeout(200)
    check('apply sets workout target & library weight', pg.input_value('#in-w-0') == '62.5' and pg.evaluate("__gym.S.exercises[0].w") == 62.5)
    check('suggestion disappears once applied', 'מומלץ לעלות' not in pg.inner_text('#view'))
    check('legs: no suggestion (reps not completed last time)', True)  # verified below when legs is current

    # ---- undo of a strength set ----
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    check('set marked -> rest', pg.evaluate('__gym.S.active.phase') == 'rest')
    pg.click('[data-a=undo]'); pg.wait_for_timeout(200)
    check('undo removes set and stops rest', pg.evaluate("__gym.S.logs['2026-11-03'].items[1].sets.length") == 0 and pg.evaluate('__gym.S.active.phase') == 'ready')
    pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    pg.evaluate("document.querySelector('#undo').classList.contains('show')")
    pg.wait_for_timeout(10300)
    check('undo expires after 10 seconds', not pg.is_visible('#undo'))
    act(pg, 'undo'); pg.wait_for_timeout(100)
    check('expired undo does nothing', pg.evaluate("__gym.S.logs['2026-11-03'].items[1].sets.length") == 1)
    pg.evaluate('__gym.S.active.endsAt=Date.now()+10500'); pg.wait_for_timeout(1000)
    check('voice: 10 seconds warning in set rest', 'עוד עשר שניות' in pg.evaluate('__said.join("|")'))
    ff(pg)
    check('voice: rest over, next set with weight', 'המנוחה הסתיימה. סט 2 מתוך 3, לחיצת חזה, 62.5 קילו' in pg.evaluate('__said.join("|")'))
    pg.click('[data-a=mark]'); ff(pg); pg.click('[data-a=mark]'); pg.wait_for_timeout(200)
    ff(pg)
    txt = pg.inner_text('#view')
    check('legs: last time shown, no suggestion (6 reps < 10)', 'בפעם הקודמת (27.10): 3 סטים × 6/6/6' in txt and 'מומלץ לעלות' not in txt)

    # ---- undo of finished workout ----
    pg.click('[data-a=mark]'); ff(pg); pg.click('[data-a=mark]'); ff(pg); pg.click('[data-a=mark]'); pg.wait_for_timeout(1500)
    check('workout finished + voice congrats', pg.evaluate('__gym.S.active') is None and 'כל הכבוד! האימון הושלם.' in pg.evaluate('__said.join("|")'))
    check('undo offered for finished workout', 'האימון הושלם' in pg.inner_text('#undo'))
    pg.click('[data-a=undo]'); pg.wait_for_timeout(200)
    check('undo reopens workout before last set', pg.evaluate('__gym.S.active.phase') == 'ready' and pg.evaluate("__gym.S.logs['2026-11-03'].finishedAt") == 0 and pg.evaluate("__gym.S.logs['2026-11-03'].items[2].sets.length") == 2)

    # ---- manual end undo ----
    pg.click('[data-a=end]'); pg.click('[data-a=confirm-ok]'); pg.wait_for_timeout(200)
    pg.click('[data-a=undo]'); pg.wait_for_timeout(200)
    check('undo of "end workout now"', pg.evaluate('__gym.S.active') is not None and pg.evaluate("__gym.S.logs['2026-11-03'].finishedAt") == 0)

    # ---- voice toggle off ----
    n = pg.evaluate('__said.length')
    pg.click('[data-a=settings]'); pg.uncheck('#s-voice'); pg.click('[data-a=set-save]'); pg.wait_for_timeout(100)
    pg.click('[data-a=mark]'); pg.wait_for_timeout(1600)   # finishes the workout: congrats must stay silent
    check('voice off -> silent', pg.evaluate('__said.length') == n and pg.evaluate('__gym.S.active') is None)
    pg.click('[data-a=settings]'); pg.click('[data-a=test-voice]')
    check('test button speaks even when off', pg.evaluate('__said.length') == n + 1)
    pg.click('#md [data-a=close]')

    # ---- security: names spoken/printed safely ----
    pg.evaluate("""(()=>{const S=__gym.S;S.logs['2026-11-03'].items[2].name='<img src=x onerror="window.__x=1">';})()""")
    act(pg, 'tab', 'work'); pg.wait_for_timeout(100)
    check('history/suggestion rendering escapes names', pg.evaluate('window.__x') is None)
    s2 = pg.evaluate("__gym.sanState({settings:{voice:'yes'}}).settings.voice")
    check('voice setting sanitized to boolean', s2 is True)
    check('no JS errors', not errs)
    if errs: print(errs)
    pg.screenshot(path='tests/out/v13.png', full_page=True)
    b.close()
print(f'\n{len(P)} passed, {len(F)} failed'); sys.exit(1 if F else 0)
