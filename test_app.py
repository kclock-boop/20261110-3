import unittest
import os
import tempfile
from pathlib import Path
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import app

class Tests(unittest.TestCase):
    def test_schedule(self):
        cfg=app.DEFAULT | {'enabled':True}
        self.assertTrue(app.due(cfg,datetime(2026,11,13,9,0,tzinfo=app.KST)))
        self.assertFalse(app.due(cfg,datetime(2026,11,13,9,1,tzinfo=app.KST)))
        self.assertFalse(app.due(cfg,datetime(2026,11,12,9,0,tzinfo=app.KST)))
        self.assertFalse(app.due(cfg | {'enabled':False},datetime(2026,11,13,9,0,tzinfo=app.KST)))
    def test_ledger(self):
        original=app.ROOT
        try:
            with tempfile.TemporaryDirectory() as d:
                app.ROOT=Path(d)
                self.assertTrue(app.claim('2026-11-13'))
                app.finish('2026-11-13','확인 필요')
                self.assertFalse(app.claim('2026-11-13'))
        finally: app.ROOT=original
    def test_incomplete_blocked(self):
        with self.assertRaises(ValueError): app.validate(app.DEFAULT,True)
    def test_browser(self):
        from playwright.sync_api import sync_playwright
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(app.ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        cfg=app.DEFAULT | dict(url=f'http://127.0.0.1:{server.server_port}/demo.html',folder='연습용 폴더',title_selector='#title',body_selector='#body',submit_selector='#submit',success_selector='#success')
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True, executable_path=os.environ.get("NOTICE_TEST_BROWSER"))
                page=browser.new_page(); page.goto(cfg['url'])
                app.fill_page(page,cfg)
                self.assertEqual(page.locator('#title').input_value(),cfg['title'])
                self.assertIn('연습용 폴더',page.locator('#body').input_value())
                self.assertFalse(page.locator('#success').is_visible())
                app.publish(page,cfg)
                self.assertTrue(page.locator('#success').is_visible())
                self.assertIn(cfg['title'],page.locator('#post').inner_text())
                with self.assertRaises(ValueError): app.publish(page,cfg)
                browser.close()
        finally:
            server.shutdown(); server.server_close()

if __name__=='__main__': unittest.main()
