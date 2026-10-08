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
        if os.name != 'nt':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(1500*1024*1024,1500*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(35,35))
        from sandbox.engine import execute
        request = json.loads(incoming.read_text(encoding='utf-8'))
        result = execute(request['spec'],request['tgap_source'],request['data_root'])
        payload = {'ok':True,'result':result}
    except Exception as error:
        payload = {'ok':False,'error':f'{type(error).__name__}: {str(error)[:1500]}'}
    outgoing.write_text(json.dumps(payload,allow_nan=False),encoding='utf-8')
