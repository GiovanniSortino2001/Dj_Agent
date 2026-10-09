"""Actual HTTP loopback transport with a fake server, no language model."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
import time
import unittest
from dj.planner import QwenPlanner


class HttpPlannerTests(unittest.TestCase):
    def test_loopback_http_and_timeout(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if self.path=='/slow': time.sleep(.25)
                self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
                try: self.wfile.write(json.dumps({'choices':[{'message':{'content':'{"candidate":0}'}}]}).encode())
                except (BrokenPipeError,ConnectionResetError): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        plans=[dict(score=.8,duration=8,confidence=.9)]
        try:
            root=f'http://127.0.0.1:{server.server_port}'
            q=QwenPlanner(root+'/v1/chat/completions',timeout=1)
            self.assertEqual(q.choose(plans),plans[0]); self.assertEqual(q.last_status,'qwen_selected')
            self.assertEqual(seen[0]['model'],'Qwen/Qwen3-4B')
            q=QwenPlanner(root+'/slow',timeout=.1)
            start=time.monotonic(); self.assertEqual(q.choose(plans),plans[0])
            self.assertEqual(q.last_status,'deterministic_fallback')
            self.assertLess(time.monotonic()-start,1)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
