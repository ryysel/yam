"""Host-only migration/autostart fixture; no speaker, native audio or real LEDs."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

daemon = str(Path(sys.argv[1]).resolve())
with tempfile.TemporaryDirectory(prefix='yam-services-fixture-') as temp:
    root = Path(temp)
    (root/'settings.toml').write_text('''allow_plugin_binaries = true
[led]
profile = "custom"
count = 1
sysfs_root = "/nonexistent-yam-lifecycle-led"
path_template = "{root}/{channel}-{index}"
[web]
ui = false
api = true
[updates]
enabled = false
interval_minutes = 360
''')
    package=root/'plugins'/'fixture'
    package.mkdir(parents=True)
    (package/'plugin.toml').write_text('''id="fixture"
name="fixture"
version="1"
entry="worker.sh"
permissions=["exec"]
[launch]
kind="binary"
mode="service"
path="worker.sh"
interpreter="sh"
''')
    (package/'worker.sh').write_text('#!/bin/sh\ntrap "exit 0" TERM INT\nwhile :; do sleep 0.1; done\n')
    (root/'plugins'/'enabled.json').write_text('["fixture"]')
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}/api'
    def request(path, post=False):
        r=urllib.request.Request(base+path, data=b'' if post else None, method='POST' if post else 'GET')
        with urllib.request.urlopen(r, timeout=5) as response:
            data=response.read()
            return json.loads(data) if data else None
    def info(): return next(p for p in request('/plugins') if p['manifest']['id']=='fixture')
    def wait(pred):
        last=None
        for _ in range(100):
            try:
                value=info()
                if pred(value): return value
            except Exception as e: last=e
            time.sleep(.05)
        raise AssertionError(f'lifecycle did not settle: {last}')
    def start():
        p=subprocess.Popen([daemon,'--listen',f'127.0.0.1:{port}','--data-dir',str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait(lambda _:True)
        return p
    p=start()
    try:
        wait(lambda x:x['enabled'] and x['service_enabled'] and x['running'])
        assert json.loads((root/'plugins'/'services.json').read_text())==['fixture']
        request('/plugins/fixture/stop', True)
        wait(lambda x:x['enabled'] and x['service_enabled'] and not x['running'])
        request('/plugins/fixture/service/start', True)
        wait(lambda x:x['running'])
        request('/plugins/fixture/service/disable', True)
        wait(lambda x:x['enabled'] and not x['service_enabled'] and not x['running'])
        p.terminate(); p.wait(timeout=10)
        p=start()
        wait(lambda x:x['enabled'] and not x['service_enabled'] and not x['running'])
        request('/plugins/fixture/service/enable', True)
        wait(lambda x:x['enabled'] and x['service_enabled'] and x['running'])
        request('/plugins/fixture/toggle', True)
        wait(lambda x:not x['enabled'] and not x['service_enabled'] and not x['running'])
    finally:
        if p.poll() is None:
            try: request('/plugins/fixture/stop',True)
            except Exception: pass
            p.terminate(); p.wait(timeout=10)
print('SERVICE_MIGRATION_AUTOSTART_STOP_ENABLE_PASS')
