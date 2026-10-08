"""Small supervisor, compatible with Windows Task Scheduler and systemd."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',required=True)
    args=parser.parse_args()
    home=Path(args.home).resolve()
    data=home/'data'
    data.mkdir(parents=True,exist_ok=True)
    stop=data/'service.stopped'
    runtime=data/'runtime.json'
    child=None
    def shutdown(*_):
        if child and child.poll() is None:child.terminate()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    try:
        while not stop.exists():
            config=json.loads((home/'config.json').read_text(encoding='utf-8'))
            log=data/'server.log'
            if log.exists() and log.stat().st_size>5*1024*1024:
                log.replace(data/'server.previous.log')
            env=dict(os.environ,TGAP_SANDBOX_HOME=str(home),PYTHONUNBUFFERED='1')
            with log.open('ab') as output:
                child=subprocess.Popen([sys.executable,'-m','uvicorn','sandbox.app:app','--host',config['host'],'--port',str(config['port']),
                        '--no-access-log','--timeout-graceful-shutdown','5','--no-proxy-headers',
                        '--limit-concurrency','64','--backlog','128','--timeout-keep-alive','5'],cwd=home,env=env,stdout=output,stderr=output,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                runtime.write_text(json.dumps(dict(supervisor_pid=os.getpid(),server_pid=child.pid,port=config['port'],started=time.time())),encoding='utf-8')
                while child.poll() is None and not stop.exists():time.sleep(1)
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=8)
                    except subprocess.TimeoutExpired:child.kill()
            if not stop.exists():time.sleep(3)
    finally:
        if child and child.poll() is None:child.terminate()
        runtime.unlink(missing_ok=True)


if __name__=='__main__':main()
