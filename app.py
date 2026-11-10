"""주간 공지 도우미: Python 3.10+, Playwright. 외부 서비스 계정 불필요."""
import json
import sqlite3
import threading
import queue
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
DEFAULT = dict(url='', title='Core Time 활동계획서 업데이트 공지',
    body='각 팀별 차주 활동계획서를 아래 폴더에 금일 14:00까지 업데이트하시기 바랍니다.\n\n{폴더}',
    folder='', weekday=4, at='09:00', title_selector='', body_selector='',
    submit_selector='', success_selector='', frame_selector='', enabled=False)


def load():
    p = ROOT / 'settings.json'
    return DEFAULT | (json.loads(p.read_text(encoding='utf-8')) if p.exists() else {})


def validate(c, posting=False):
    datetime.strptime(c['at'], '%H:%M')
    if not 0 <= int(c['weekday']) <= 6:
        raise ValueError('요일을 선택하세요.')
    if not c['title'].strip() or not c['body'].strip():
        raise ValueError('제목과 내용을 입력하세요.')
    if posting:
        u = urlsplit(c['url'])
        if u.scheme not in ('http', 'https') or not u.netloc:
            raise ValueError('게시판 글쓰기 페이지의 http 또는 https 주소가 필요합니다.')
        for key in ('title_selector', 'body_selector', 'submit_selector', 'success_selector'):
            if not c[key].strip():
                raise ValueError('제목·본문·등록·등록완료 확인 요소를 모두 설정하세요.')
        if not c['folder'].strip():
            raise ValueError('공지에 넣을 폴더 주소를 입력하세요.')


def rendered(c, now=None):
    now = now or datetime.now(KST)
    return c['body'].replace('{폴더}', c['folder']).replace('{날짜}', now.strftime('%Y-%m-%d'))


def due(c, now):
    # 같은 분 동안만 실행. 꺼져 있는 동안 놓친 공지를 뒤늦게 올리지 않음.
    return c['enabled'] and now.weekday() == c['weekday'] and now.strftime('%H:%M') == c['at']


def claim(key):
    with sqlite3.connect(ROOT / 'history.db') as db:
        db.execute('CREATE TABLE IF NOT EXISTS runs (key TEXT PRIMARY KEY, state TEXT, detail TEXT)')
        try:
            db.execute('INSERT INTO runs VALUES (?, ?, ?)', (key, '진행 중', ''))
            return True
        except sqlite3.IntegrityError:
            return False


def finish(key, state, detail=''):
    with sqlite3.connect(ROOT / 'history.db') as db:
        db.execute('UPDATE runs SET state=?, detail=? WHERE key=?', (state, detail, key))


def fill_one(scope, selector, text):
    element = scope.locator(selector)
    if element.count() != 1:
        raise ValueError('입력 요소가 없거나 여러 개입니다: ' + selector)
    element.fill(text)


def fill_page(page, c):
    scope = page.frame_locator(c['frame_selector']) if c['frame_selector'].strip() else page
    fill_one(scope, c['title_selector'], c['title'])
    fill_one(scope, c['body_selector'], rendered(c))
    return scope


def publish(page, c):
    scope = fill_page(page, c)
    button = scope.locator(c['submit_selector'])
    if button.count() != 1:
        raise ValueError('등록 버튼은 한 개만 지정해야 합니다.')
    success = page.locator(c['success_selector'])
    if success.is_visible():
        raise ValueError('완료 표시가 등록 전에 보입니다. 등록 후에만 나타나는 요소를 지정하세요.')
    button.click()
    success.wait_for(state='visible', timeout=20000)


def browser_job(c, action, log):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(ROOT / 'browser_profile'), headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(20000)
            page.goto(c['url'], wait_until='domcontentloaded')
            if action == 'login':
                log('브라우저에서 직접 로그인하세요. 완료 후 브라우저 창을 닫으세요.')
                while context.pages:
                    try:
                        page.wait_for_timeout(500)
                    except Exception:
                        break
            elif action == 'inspect':
                log('검사 창의 Pick locator로 입력칸·버튼을 선택하고 locator 문자열을 복사하세요. Resume 후 종료됩니다.')
                page.pause()
            elif action == 'preview':
                fill_page(page, c)
                log('입력 시험 완료. 등록 버튼은 누르지 않았습니다. 내용을 확인하고 브라우저를 닫으세요.')
                while context.pages:
                    try:
                        page.wait_for_timeout(500)
                    except Exception:
                        break
            else:
                publish(page, c)
                log('등록완료 표시 확인. 게시판에서도 게시물을 확인하세요.')
        finally:
            context.close()


def main():
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Tk()
    root.title('주간 공지 자동등록 도우미')
    root.geometry('900x860')
    c = load()
    events = queue.Queue()
    busy = threading.Lock()
    fields = {}
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='주간 공지 자동등록', font=('', 19, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='회사 게시판 연결 전 설정이 필요합니다. 예약은 이 프로그램과 PC가 켜져 있을 때 작동합니다.').pack(anchor='w', pady=7)
    form = ttk.Frame(frame)
    form.pack(fill='x')
    labels = [('url','글쓰기 페이지 주소'), ('title','공지 제목'), ('folder','공유폴더 주소'),
              ('at','게시 시각 (한국시간 HH:MM)'), ('title_selector','제목 입력 요소'),
              ('body_selector','본문 입력 요소'), ('submit_selector','등록 버튼 요소'),
              ('success_selector','등록완료 표시 요소'), ('frame_selector','글쓰기 iframe 요소 (없으면 빈칸)')]
    for i, (key,label) in enumerate(labels):
        ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=3)
        fields[key] = tk.StringVar(value=c[key])
        ttk.Entry(form, textvariable=fields[key], width=72).grid(row=i, column=1, sticky='ew', padx=10)
    form.columnconfigure(1, weight=1)
    weekdays = ['월요일','화요일','수요일','목요일','금요일','토요일','일요일']
    day = ttk.Combobox(form, values=weekdays, state='readonly')
    day.current(c['weekday'])
    ttk.Label(form,text='매주 게시 요일 (기본: 금요일)').grid(row=9,column=0,sticky='w')
    day.grid(row=9,column=1,sticky='w',padx=10)
    enabled = tk.BooleanVar(value=c['enabled'])
    ttk.Checkbutton(frame, text='예약 자동 게시 켜기 — 먼저 입력 시험과 실제 1회 등록을 확인하세요', variable=enabled).pack(anchor='w',pady=8)
    ttk.Label(frame,text='공지 내용 — {폴더}: 공유폴더 주소, {날짜}: 게시일').pack(anchor='w')
    body = tk.Text(frame,height=7,wrap='word',font=('',12))
    body.insert('1.0',c['body'])
    body.pack(fill='x',pady=5)
    status = tk.StringVar(value='기본값: 매주 금요일 09:00 / 예약 꺼짐 / 게시판 연결 미설정')
    ttk.Label(frame,textvariable=status,wraplength=840).pack(anchor='w',pady=6)
    def log(text):
        events.put(text)
    def collect():
        return {key:var.get().strip() for key,var in fields.items()} | dict(body=body.get('1.0','end-1c'), weekday=day.current(), enabled=enabled.get())
    def save():
        try:
            cfg = collect()
            validate(cfg, posting=cfg['enabled'])
            path = ROOT / 'settings.json'
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(path)
            log('설정 저장 완료. 예약 ' + ('켜짐' if cfg['enabled'] else '꺼짐'))
            return cfg
        except Exception as e:
            messagebox.showerror('설정 확인',str(e))
    def run(action, cfg=None, key=None):
        cfg = cfg or collect()
        try:
            if action in ('login','inspect'):
                u = urlsplit(cfg['url'])
                if u.scheme not in ('http','https') or not u.netloc:
                    raise ValueError('글쓰기 페이지 주소를 먼저 입력하세요.')
            else:
                validate(cfg, posting=True)
        except Exception as e:
            if key:
                finish(key,'실패',str(e)); log(str(e))
            else:
                messagebox.showerror('설정 확인',str(e))
            return
        if not busy.acquire(False):
            log('브라우저 작업 중입니다. 기존 창을 닫고 다시 실행하세요.')
            if key:
                finish(key,'건너뜀','다른 브라우저 작업 진행 중')
            return
        def work():
            try:
                browser_job(cfg,action,log)
                if key: finish(key,'완료')
            except Exception as e:
                log('중단: ' + str(e)[:300] + ' / 등록 여부를 게시판에서 확인하세요. 자동 재시도하지 않습니다.')
                if key: finish(key,'확인 필요',str(e)[:300])
            finally:
                busy.release()
        threading.Thread(target=work,daemon=True).start()
    def manual():
        cfg=collect()
        if messagebox.askyesno('실제 게시', '설정한 회사 게시판에 공지를 지금 1회 등록할까요?'):
            now=datetime.now(KST)
            key=now.date().isoformat()
            if claim(key): run('post',cfg,key)
            else: messagebox.showinfo('중복 방지','오늘의 게시 시도 기록이 있습니다. 기록과 실제 게시판을 확인하세요. 오늘 자동으로 다시 게시하지 않습니다.')
    buttons=ttk.Frame(frame); buttons.pack(fill='x',pady=8)
    for label,cmd in [('설정 저장',save),('① 로그인',lambda:run('login')),('② 요소 찾기',lambda:run('inspect')),('③ 입력 시험',lambda:run('preview')),('④ 지금 1회 등록',manual)]:
        ttk.Button(buttons,text=label,command=cmd).pack(side='left',padx=3)
    logs=tk.Text(frame,height=7,state='disabled',wrap='word')
    logs.pack(fill='both',expand=True)
    def tick():
        while not events.empty():
            msg=events.get(); status.set(msg)
            logs.config(state='normal'); logs.insert('end',datetime.now(KST).strftime('%m-%d %H:%M:%S ') + msg+'\n'); logs.see('end'); logs.config(state='disabled')
        try:
            cfg=load(); now=datetime.now(KST)
            if due(cfg,now):
                key=now.date().isoformat()
                if claim(key):
                    log('예약 시각 도달. 게시를 시작합니다.')
                    run('post',cfg,key)
        except Exception as e:
            status.set('예약 확인 오류: '+str(e))
        root.after(1000,tick)
    def close():
        if busy.locked() and not messagebox.askyesno('작업 종료','브라우저 작업 중입니다. 종료하면 게시 상태 확인이 필요할 수 있습니다. 종료할까요?'): return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    tick(); root.mainloop()

if __name__ == '__main__':
    main()
