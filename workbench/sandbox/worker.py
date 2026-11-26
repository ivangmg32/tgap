"""One process per experiment. Reads/writes only paths chosen by the server."""
import json
import os
from pathlib import Path
import sys
import time

os.environ['MPLBACKEND'] = 'Agg'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    incoming, outgoing = map(Path,sys.argv[1:3])
    try:
        request = json.loads(incoming.read_text(encoding='utf-8'))
        cpu = int(request.get('cpu_seconds',35))
        if os.name != 'nt':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(1500*1024*1024,1500*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
        if request.get('kind') == 'guided':
            from sandbox.guided import execute_guided
            progress_path = outgoing.with_name(outgoing.name.replace('.output.json','.progress.json'))

            def progress(stage, message):
                # Write-then-rename so the server never reads a partial file.
                # On Windows the rename fails while the server is reading the
                # old file, so retry briefly; progress is cosmetic and must
                # never fail the experiment.
                temporary = progress_path.with_suffix('.tmp')
                try:
                    temporary.write_text(json.dumps(dict(stage=stage,message=message)),encoding='utf-8')
                    for attempt in range(20):
                        try:
                            os.replace(temporary,progress_path)
                            return
                        except PermissionError:
                            time.sleep(0.02*(attempt+1))
                except OSError:
                    pass
            result = execute_guided(request['spec'],request['tgap_source'],request['data_root'],progress)
        else:
            from sandbox.engine import execute
            result = execute(request['spec'],request['tgap_source'],request['data_root'])
        payload = {'ok':True,'result':result}
    except Exception as error:
        payload = {'ok':False,'error':f'{type(error).__name__}: {str(error)[:1500]}'}
    outgoing.write_text(json.dumps(payload,allow_nan=False),encoding='utf-8')
