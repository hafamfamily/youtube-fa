import http.server, json, re, sys, urllib.parse
STATE={"uploads":{},"log":[]}
class H(http.server.BaseHTTPRequestHandler):
    def _send(self,code,obj=None,headers=None):
        b=json.dumps(obj or {}).encode()
        self.send_response(code)
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass
    def body(self):
        n=int(self.headers.get("Content-Length") or 0); return self.rfile.read(n)
    def do_POST(self):
        p=self.path; b=self.body(); STATE["log"].append(("POST",p,len(b)))
        if p.startswith("/token"): return self._send(200,{"access_token":"AT","expires_in":3600})
        if p.startswith("/upload/videos"):
            meta=json.loads(b); STATE["meta"]=meta; STATE["size"]=int(self.headers["X-Upload-Content-Length"]); STATE["got"]=0
            return self._send(200,{},{"Location":f"http://127.0.0.1:{PORT}/session/1"})
        if p.startswith("/upload/thumbnails"): STATE["thumb"]=len(b); return self._send(200,{"items":[{}]})
        if p.startswith("/aparat/upload"):
            STATE["aparat_body"]=len(b); txt=b[:3000].decode("utf-8","replace"); STATE["aparat_fields"]=re.findall(r'name="([^"]+)"',txt)
            return self._send(200,{"uploadpost":{"uid":"abc12"}})
        self._send(404,{"error":{"message":"nf"}})
    def do_PUT(self):
        b=self.body(); STATE["got"]+=len(b); STATE["log"].append(("PUT",self.headers["Content-Range"]))
        if STATE["got"]>=STATE["size"]: return self._send(200,{"id":"VID123","status":STATE["meta"]["status"]})
        self.send_response(308); self.send_header("Range",f"bytes=0-{STATE['got']-1}"); self.send_header("Content-Length","0"); self.end_headers()
    def do_GET(self):
        p=self.path; STATE["log"].append(("GET",p))
        if p.startswith("/api/videos"): return self._send(200,{"items":[{"status":{"privacyStatus":STATE["meta"]["status"]["privacyStatus"]}}]})
        if p.startswith("/api/channels"): return self._send(200,{"items":[{"id":"UC1","snippet":{"title":"کانال تست"},"status":{"longUploadsStatus":"allowed"}}]})
        if p.startswith("/aparat/login"): return self._send(200,{"login":{"username":"tester","ltoken":"LT"}})
        if p.startswith("/aparat/uploadform"): return self._send(200,{"uploadform":{"formAction":f"http://127.0.0.1:{PORT}/aparat/upload","frm-id":"F1"}})
        if p.startswith("/aparat/categories"): return self._send(200,{"categories":[{"id":7,"name":"آموزش"}]})
        if p.startswith("/state"): return self._send(200,{k:v for k,v in STATE.items() if k!="log"})
        self._send(404,{})
PORT=int(sys.argv[1])
http.server.ThreadingHTTPServer(("127.0.0.1",PORT),H).serve_forever()
