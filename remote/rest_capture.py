"""Bounded, read-only localhost GET capture. Parsing happens on the VPS."""
import asyncio
import json
import time
import urllib.request

PATHS = ('/rest/sessions/weather','/rest/sessions','/rest/garage/getPlayerGarageData','/rest/garage/UIScreen/RepairAndRefuel','/rest/strategy/pitstop-estimate')


class RestCapture:
    def __init__(self):
        self.records = {}
        self.task = None

    def fetch(self,path):
        # No configurable destination, redirects or proxy; credentials never enter
        # this channel. A missing LMU REST service cannot block shared memory.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        try:
            with opener.open('http://127.0.0.1:6397'+path,timeout=.25) as response:
                raw = response.read(131073)
            if len(raw)>131072:
                raise ValueError('REST response exceeds cap')
            return {'ok':True,'capturedAt':time.time()*1000,'data':json.loads(raw)}
        except Exception:
            return {'ok':False,'capturedAt':time.time()*1000}

    async def loop(self):
        while True:
            for path in PATHS:
                self.records[path] = await asyncio.to_thread(self.fetch,path)
            await asyncio.sleep(1)

    def start(self):
        self.task = asyncio.create_task(self.loop())

    def close(self):
        if self.task:
            self.task.cancel()
