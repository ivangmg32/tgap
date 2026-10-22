"""One process per experiment. Reads/writes only paths chosen by the server."""
import json
import os
from pathlib import Path
import sys

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
                temporary = progress_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(dict(stage=stage,message=message)),encoding='utf-8')
                os.replace(temporary,progress_path)
            result = execute_guided(request['spec'],request['tgap_source'],request['data_root'],progress)
        else:
            from sandbox.engine import execute
            result = execute(request['spec'],request['tgap_source'],request['data_root'])
        payload = {'ok':True,'result':result}
    except Exception as error:
        payload = {'ok':False,'error':f'{type(error).__name__}: {str(error)[:1500]}'}
    outgoing.write_text(json.dumps(payload,allow_nan=False),encoding='utf-8')
