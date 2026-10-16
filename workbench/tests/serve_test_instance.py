"""Loopback-only browser fixture. Never use this deterministic CAPTCHA server publicly."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_workbench import app,TEMP
import sandbox.security
sandbox.security.generate_answer=lambda:'ABC234'
(Path(__file__).resolve().parents[1]/'verification'/'browser-test-home.txt').write_text(str(TEMP))
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8093,access_log=False,proxy_headers=False)
