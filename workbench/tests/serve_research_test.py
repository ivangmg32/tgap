"""Loopback researcher-browser fixture with artificial records, never public."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_workbench import app,TEMP
from test_research import ResearchTests
fixture=ResearchTests();fixture.setUp()
import sandbox.security
sandbox.security.generate_answer=lambda:'ABC234'
(Path(__file__).resolve().parents[1]/'verification'/'research-browser-fixture.json').write_text(json.dumps(dict(home=str(TEMP),session=fixture.tag,job=fixture.jobs[0])))
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8095,access_log=False,proxy_headers=False)
