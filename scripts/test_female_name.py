from playwright.sync_api import sync_playwright, expect
from pathlib import Path
import json
OUT=Path(__file__).resolve().parents[1]/'test-results'/'female'; OUT.mkdir(exist_ok=True)
BASE='http://localhost:3010'
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 c=b.new_context(viewport={'width':1672,'height':1040})
 c.route('**/api/auth/me',lambda r:r.fulfill(status=401,body='{}',content_type='application/json'))
 page=c.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
 def advance_to_input(pg):
  for _ in range(3):
   button=pg.get_by_role('button',name='继续对话')
   expect(button).to_be_visible(); pg.wait_for_timeout(850); button.click(); pg.wait_for_timeout(200)
  expect(pg.get_by_role('textbox',name='玩家姓名')).to_be_visible()
 def finish_reply(pg):
  for _ in range(3):
   button=pg.get_by_role('button',name='继续对话')
   expect(button).to_be_visible(); pg.wait_for_timeout(850); button.click(); pg.wait_for_timeout(200)
  pg.wait_for_url('**/female')
 page.goto(BASE+'/select')
 page.get_by_role('link',name='书页间的邂逅').click()
 page.wait_for_url('**/female/name')
 expect(page.get_by_role('button',name='继续对话')).to_be_visible()
 page.screenshot(path=str(OUT/'intro.png'))
 advance_to_input(page)
 field=page.get_by_role('textbox',name='玩家姓名'); start=page.get_by_role('button',name='开始故事')
 field.fill('   '); start.click(); expect(page.locator('#female-name-error')).to_contain_text('名字')
 field.fill('一'*13); start.click(); expect(page.locator('#female-name-error')).to_contain_text('12')
 field.fill('小雨'); field.dispatch_event('compositionstart'); field.press('Enter')
 expect(field).to_be_visible(); field.dispatch_event('compositionend')
 page.screenshot(path=str(OUT/'name-desktop.png'))
 field.fill('  小雨  '); field.press('Enter')
 expect(page.get_by_role('button',name='继续对话')).to_contain_text('小雨……')
 # Confirmed name survives refresh before the reply has completed.
 page.reload(); expect(page.get_by_role('button',name='继续对话')).to_contain_text('小雨……')
 finish_reply(page)
 expect(page.get_by_role('heading',name='女性向主界面')).to_be_visible()
 profiles=page.evaluate("Object.entries(localStorage).filter(([k])=>k.startsWith('galstudy.profile.'))")
 record=json.loads(profiles[0][1]); assert record['playerName']=='小雨' and record['hasCompletedNameEntry']
 assert all(k in record for k in ['userId','storyPreference','createdAt','updatedAt'])
 page.goto(BASE+'/female/name'); page.wait_for_url('**/female')
 page.get_by_role('link',name='返回',exact=True).click(); page.wait_for_url('**/select')
 page.get_by_role('link',name='放学后的约定').click(); page.wait_for_url('**/study')
 assert page.evaluate("localStorage.getItem('galstudy.playerName.male')")==None
 # Existing male route still serves and its save remains untouched.
 page.goto(BASE+'/male/name'); expect(page.get_by_role('textbox',name='玩家姓名')).to_be_enabled()
 # New accounts are scoped independently, preserving previous female data.
 c.route('**/api/auth/me',lambda r:r.fulfill(body='{"email":"second@example.test"}',content_type='application/json'))
 page.goto(BASE+'/female/name'); advance_to_input(page)
 field=page.get_by_role('textbox',name='玩家姓名'); field.fill('美咲'); field.press('Enter'); finish_reply(page)
 assert len(page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('galstudy.profile.'))"))==2
 # Mobile portrait, reduced motion, English, storage failure and successful retry.
 m=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,reduced_motion='reduce')
 m.route('**/api/auth/me',lambda r:r.fulfill(status=401,body='{}',content_type='application/json'))
 phone=m.new_page(); phone.goto(BASE+'/female/name'); advance_to_input(phone)
 assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth')
 phone.get_by_role('textbox',name='玩家姓名').fill('Alice')
 phone.screenshot(path=str(OUT/'name-mobile.png'),full_page=True)
 phone.evaluate("() => { window.originalSet=Storage.prototype.setItem; Storage.prototype.setItem=function(){throw new Error('blocked')}; }")
 phone.get_by_role('button',name='开始故事').click(); expect(phone.locator('#female-name-error')).to_contain_text('保存')
 phone.evaluate('() => { Storage.prototype.setItem=window.originalSet; }')
 phone.get_by_role('button',name='开始故事').click(); finish_reply(phone)
 assert not errors, errors
 print(json.dumps({'passed':['selection transition','intro dialogue','Chinese name','IME Enter guard','blank and length validation','dynamic reply','refresh during reply','completion and reentry','male compatibility','account isolation','Japanese name','English name','mobile portrait','reduced motion','storage failure retry'],'pageErrors':errors},ensure_ascii=False))
 b.close()


