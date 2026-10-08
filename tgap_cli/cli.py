"""Bootstrap a separate environment; no third-party imports before installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
import zipfile


def home_path(value=None):
    return Path(value or os.environ.get('TGAP_HOME',Path.home()/'.tgap')).expanduser().resolve()


def python_path(home):
    return home/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def source_path():
    return Path(__file__).resolve().parents[1]


def execute(args,cwd=None):
    subprocess.run([str(a) for a in args],cwd=cwd,check=True)


def question(message):
    return input(message+' [y/N] ').strip().lower() in ('y','yes')


def unpack(home,source=None):
    destination=(home/'workbench').resolve()
    destination.mkdir(parents=True,exist_ok=True)
    if source:
        source=Path(source).resolve()
        if not (source/'sandbox'/'app.py').is_file():
            raise ValueError('The sandbox source directory must contain sandbox/app.py.')
        for directory in ('sandbox','static','fixtures','publication'):
            if (source/directory).exists():
                shutil.copytree(source/directory,destination/directory,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(source/'requirements.txt',destination/'requirements.txt')
    else:
        bundle=Path(__file__).with_name('data')/'sandbox.zip'
        expected=bundle.with_suffix('.sha256').read_text(encoding='utf-8').strip()
        if hashlib.sha256(bundle.read_bytes()).hexdigest()!=expected:
            raise ValueError('Workbench bundle checksum does not match; restore the distribution before installing.')
        with zipfile.ZipFile(bundle) as archive:
            for item in archive.infolist():
                target=(destination/item.filename).resolve()
                if not target.is_relative_to(destination):
                    raise ValueError('Invalid archive member.')
            archive.extractall(destination)
    data=destination/'data'/'datasets'
    data.mkdir(parents=True,exist_ok=True)
    if (destination/'fixtures').exists():
        for fixture in (destination/'fixtures').glob('*.json'):
            shutil.copy2(fixture,data/fixture.name)
    return destination


def register_launcher(home):
    scripts=home/'bin'
    scripts.mkdir(exist_ok=True)
    py=python_path(home)
    if os.name=='nt':
        launcher=scripts/'tgap.cmd'
        launcher.write_text('@echo off\r\n"'+str(py)+'" -m tgap_cli --home "'+str(home)+'" %*\r\n',encoding='utf-8')
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
            try: old,_=winreg.QueryValueEx(key,'Path')
            except FileNotFoundError: old=''
            if str(scripts).lower() not in [p.lower() for p in old.split(';')]:
                winreg.SetValueEx(key,'Path',0,winreg.REG_EXPAND_SZ,old.rstrip(';')+';'+str(scripts))
        # Existing terminals retain their original environment. Refresh shell notification.
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x1A,0,'Environment',2,5000,None)
        print('Added tgap to your user PATH. Open a new terminal to use it by name.')
    else:
        import shlex
        launcher=scripts/'tgap'
        launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(py))+' -m tgap_cli --home '+shlex.quote(str(home))+' "$@"\n',encoding='utf-8')
        launcher.chmod(0o755)
        local_bin=Path.home()/'.local'/'bin'
        local_bin.mkdir(parents=True,exist_ok=True)
        link=local_bin/'tgap'
        if not link.exists() or link.is_symlink():
            link.unlink(missing_ok=True)
            link.symlink_to(launcher)
        print('Command installed in ~/.local/bin. If needed: export PATH="$HOME/.local/bin:$PATH"')


def install(args,home):
    root=source_path()
    home.mkdir(parents=True,exist_ok=True)
    target=unpack(home,args.sandbox_source)
    py=python_path(home)
    print(f'TGAP installation directory: {home}')
    tgn=args.tgn or (not args.yes and question('Install optional TGN libraries (Torch and PyTorch Geometric)?'))
    finance=args.finance or (not args.yes and question('Install optional finance libraries (yfinance and statsmodels)?'))
    previous_path=home/'installation.json'
    previous=json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    if not py.exists():
        print('Creating an isolated Python environment…')
        venv.EnvBuilder(with_pip=True).create(home/'.venv')
    execute([py,'-m','pip','install','--upgrade','pip'])
    execute([py,'-m','pip','install','-r',target/'requirements.txt'])
    # Keep the research checkout editable, including scripts and documentation.
    execute([py,'-m','pip','install','--no-deps','-e',root])
    if tgn:
        execute([py,'-m','pip','install','torch','--index-url','https://download.pytorch.org/whl/cpu'])
        execute([py,'-m','pip','install','torch_geometric'])
    if finance:
        execute([py,'-m','pip','install','yfinance','statsmodels'])
    config=target/'config.json'
    existing=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    existing.update(tgap_source=str(root),host=existing.get('host','127.0.0.1'),port=existing.get('port',8080),secure_cookies=existing.get('secure_cookies',False))
    config.write_text(json.dumps(existing,indent=2),encoding='utf-8')
    users=target/'users.txt'
    if not users.exists():
        password=secrets.token_urlsafe(15)
        users.write_text('# username:password:role\n# Roles: admin or participant. No colon in username/password.\nresearcher:'+password+':admin\n',encoding='utf-8')
        print('\nFirst account: researcher\nPassword: '+password+'\n')
        if os.name!='nt': users.chmod(0o600)
    execute([py,'-m','pip','freeze'],cwd=root) if args.verbose else None
    (home/'installation.json').write_text(json.dumps(dict(source=str(root),workbench=str(target),tgn=tgn or previous.get('tgn',False),finance=finance or previous.get('finance',False)),indent=2),encoding='utf-8')
    if not args.no_path:
        register_launcher(home)
    print(f'\nInstalled. Accounts: {users}\nStart: tgap start\nStop: tgap stop\nYou can also use the original checkout launcher immediately.')


def setup(home):
    info=home/'installation.json'
    if not info.exists() or not python_path(home).exists():
        raise ValueError('Run tgap install first (or .\\tgap.cmd install on Windows).')
    return json.loads(info.read_text(encoding='utf-8'))


def runtime(target):
    path=target/'data'/'runtime.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def health(config):
    host='127.0.0.1' if config['host']=='0.0.0.0' else config['host']
    url=f"http://{host}:{config['port']}"
    try:
        with urllib.request.urlopen(url+'/api/health',timeout=2) as response:
            return json.load(response).get('service')=='tgap-laboratory',url
    except (urllib.error.URLError,TimeoutError,OSError):
        return False,url


def service(args,home):
    info=setup(home)
    target=Path(info['workbench'])
    config=json.loads((target/'config.json').read_text(encoding='utf-8'))
    data=target/'data'
    data.mkdir(exist_ok=True)
    if args.command=='start':
        if args.port:
            config['port']=args.port
        if args.host:
            config['host']=args.host
        alive,url=health(config)
        if alive:
            print('TGAP is already running: '+url)
            return
        import socket
        with socket.socket() as sock:
            try: sock.bind((config['host'],config['port']))
            except OSError: raise ValueError(f"Port {config['port']} is already in use. Choose --port 8090.")
        (target/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        (data/'service.stopped').unlink(missing_ok=True)
        command=[str(python_path(home)),str(target/'sandbox'/'serve.py'),'--home',str(target)]
        flags=(subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS) if os.name=='nt' else 0
        with open(data/'launcher.log','ab') as log:
            proc=subprocess.Popen(command,cwd=target,stdout=log,stderr=log,stdin=subprocess.DEVNULL,
                                  creationflags=flags,start_new_session=os.name!='nt')
        for _ in range(40):
            alive,url=health(config)
            if alive:
                print('TGAP is running: '+url)
                print('Your environment is managed automatically. Use tgap stop to close it.')
                if not args.no_browser:webbrowser.open(url)
                return
            if proc.poll() is not None:break
            time.sleep(.5)
        raise ValueError(f'Could not start TGAP. Read {data / "launcher.log"} and {data / "server.log"}.')
    elif args.command=='stop':
        (data/'service.stopped').write_text('Stopped by user.\n',encoding='utf-8')
        record=runtime(target)
        if record:
            # psutil is available inside the installed environment. Do not kill a reused PID.
            script='''import json,sys,psutil
from pathlib import Path
p=psutil.Process(int(sys.argv[1]))
command=p.cmdline()
if not any('serve.py' in s for s in command) or str(Path(sys.argv[2]).resolve()).lower() not in ' '.join(command).lower():
    raise SystemExit('Refusing to stop an unrelated process.')
for child in p.children(recursive=True):
    child.terminate()
p.terminate()
'''
            subprocess.run([str(python_path(home)),'-c',script,str(record['supervisor_pid']),str(target)],check=False)
        print('TGAP stopped. Accounts, experiments and the environment were kept.')
    else:
        alive,url=health(config)
        print(('Running: ' if alive else 'Stopped: ')+url)
        print('Accounts: '+str(target/'users.txt'))


def research(args,home):
    info=setup(home)
    mapping={'examples':['examples.py','--no-show'],'evaluation':['evaluation.py'],'paper':['paper_evaluation.py'],
             'download':['-m','realdata.download'],'real-data':['-m','realdata.run_real_data'],
             'compare':['-m','realdata.compare_datasets'],'ncommunity':['-m','realdata.run_ncommunity'],
             'tgn':['-m','realdata.run_tgn'],'tgn-stability':['-m','realdata.run_tgn_stability'],
             'publication':['-m','realdata.make_publication'],'tests':['-m','unittest','discover','-s','tests'],
             'finance':['finance/experimentationDatamining.py']}
    if args.workflow.startswith('tgn') and not info['tgn']:
        raise ValueError('TGN was not installed. Run tgap install --tgn --yes.')
    if args.workflow=='finance' and not info['finance']:
        raise ValueError('Finance libraries were not installed. Run tgap install --finance --yes.')
    execute([python_path(home),*mapping[args.workflow],*args.arguments],cwd=info['source'])


def main(argv=None):
    parser=argparse.ArgumentParser(prog='tgap',description='Install and run TGAP in its own environment.')
    parser.add_argument('--home',help='Installation directory (default: ~/.tgap or TGAP_HOME).')
    subs=parser.add_subparsers(dest='command',required=True)
    installer=subs.add_parser('install',help='Create the environment and ask about optional libraries.')
    installer.add_argument('--yes',action='store_true',help='Noninteractive base installation; optional groups require explicit flags.')
    installer.add_argument('--tgn',action='store_true')
    installer.add_argument('--finance',action='store_true')
    installer.add_argument('--sandbox-source',help='Developer override for the sibling web application source.')
    installer.add_argument('--verbose',action='store_true')
    installer.add_argument('--no-path',action='store_true',help='Do not modify the user PATH (useful for temporary installations).')
    starter=subs.add_parser('start',help='Start the managed local TGAP service.')
    starter.add_argument('--port',type=int)
    starter.add_argument('--host',help='Default: 127.0.0.1. Use 0.0.0.0 only for intentional remote access.')
    starter.add_argument('--no-browser',action='store_true')
    subs.add_parser('stop',help='Stop the service, keeping accounts and results.')
    subs.add_parser('status',help='Show service status and account file.')
    runner=subs.add_parser('run',help='Run a research workflow using the managed Python environment.')
    runner.add_argument('workflow',choices=['examples','evaluation','paper','download','real-data','compare','ncommunity','tgn','tgn-stability','publication','tests','finance'])
    runner.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    if args.command=='start' and args.port is not None and not 1<=args.port<=65535:
        parser.error('Port must be between 1 and 65535.')
    try:
        home=home_path(args.home)
        if args.command=='install':install(args,home)
        elif args.command=='run':research(args,home)
        else:service(args,home)
    except (ValueError,OSError,subprocess.CalledProcessError,KeyboardInterrupt) as error:
        print('TGAP: '+str(error),file=sys.stderr)
        raise SystemExit(1)
