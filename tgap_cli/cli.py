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


def child_environment(home=None):
    ''' The environment every TGAP child process gets.

    TEMP/TMP/TMPDIR point at a folder inside the TGAP home, because system
    temp folders are a frequent cause of failed installs on Windows (full,
    locked by antivirus, or a user name with non-ASCII letters). UTF-8
    output means a single non-ASCII character can never crash a run on a
    cp1252 Windows console. '''
    env=dict(os.environ)
    if home is not None:
        temporary=Path(home)/'tmp'
        try:
            temporary.mkdir(parents=True,exist_ok=True)
            for name in ('TEMP','TMP','TMPDIR'):
                env[name]=str(temporary)
            env['MPLCONFIGDIR']=str(Path(home)/'matplotlib')
        except OSError:
            pass                                 # fall back to the system temp
    env.update(PYTHONIOENCODING='utf-8',PYTHONUTF8='1',MPLBACKEND='Agg',
               PYTHONDONTWRITEBYTECODE='1',
               PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INPUT='1')
    return env


HOME_FOR_CHILDREN=None


def execute(args,cwd=None,extra_env=None):
    env=child_environment(HOME_FOR_CHILDREN)
    env.update(extra_env or {})
    subprocess.run([str(a) for a in args],cwd=cwd,check=True,env=env)


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


def _is_windows():
    ''' One place that decides which launcher layout to use (tests switch it
    to exercise the Windows logic on any machine). '''
    return os.name=='nt'


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.expanduser(str(path))))


def _on_path(directory, path_value=None):
    entries=(path_value if path_value is not None else os.environ.get('PATH','')).split(os.pathsep)
    return _norm(directory) in {_norm(p) for p in entries if p.strip()}


def _is_ours(target):
    ''' Never overwrite somebody else's "tgap": only a missing file, a
    symlink, or a launcher that we wrote ourselves. '''
    target=Path(target)
    if not target.exists() and not target.is_symlink():
        return True
    if target.is_symlink():
        return True
    try:
        return 'tgap_cli' in target.read_text(encoding='utf-8',errors='ignore')
    except OSError:
        return False


def _place(target,launcher,text):
    ''' Put a tgap command at `target`: a symlink to the launcher where the
    system allows it, otherwise a small copy of the launcher script. '''
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_symlink() or target.exists():
        target.unlink()
    if not _is_windows():
        try:
            target.symlink_to(launcher)
            return
        except OSError:
            pass
    target.write_text(text,encoding='utf-8')
    if not _is_windows():
        target.chmod(0o755)


def _windows_user_path_add(directory):
    ''' Add `directory` to the user PATH in the registry (new terminals). '''
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
        try:
            old,kind=winreg.QueryValueEx(key,'Path')
        except FileNotFoundError:
            old,kind='',winreg.REG_EXPAND_SZ
        entries=[p for p in old.split(';') if p.strip()]
        if _norm(directory) in {_norm(os.path.expandvars(p)) for p in entries}:
            return False
        entries.append(str(directory))
        winreg.SetValueEx(key,'Path',0,kind if kind in (winreg.REG_SZ,winreg.REG_EXPAND_SZ)
                          else winreg.REG_EXPAND_SZ,';'.join(entries))
    try:                                    # tell Explorer: new windows see it
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x1A,0,'Environment',2,5000,None)
    except Exception:
        pass
    return True


SHELL_MARKER='# Added by TGAP: the tgap command'


def _unix_profile_add(directory):
    ''' Make `directory` part of PATH in new terminals, via the startup
    files of the usual shells. Idempotent: a marked line is added once. '''
    line=f'export PATH="{directory}:$PATH"  {SHELL_MARKER}'
    home=Path.home()
    changed=[]
    for name in ('.profile','.bashrc','.zshrc','.bash_profile'):
        rc=home/name
        if name!='.profile' and not rc.exists():
            continue
        try:
            text=rc.read_text(encoding='utf-8') if rc.exists() else ''
            if SHELL_MARKER in text:
                continue
            with open(rc,'a',encoding='utf-8') as handle:
                handle.write(('\n' if text and not text.endswith('\n') else '')+line+'\n')
            changed.append(str(rc))
        except OSError:
            continue
    fish=home/'.config'/'fish'/'conf.d'
    if fish.parent.is_dir():
        try:
            fish.mkdir(exist_ok=True)
            (fish/'tgap.fish').write_text(f'fish_add_path -g "{directory}"  {SHELL_MARKER}\n',encoding='utf-8')
            changed.append(str(fish/'tgap.fish'))
        except OSError:
            pass
    return changed


def register_launcher(home):
    ''' Make the word `tgap` work in a terminal - as soon as possible, on
    any system - and say honestly what happened.

    The launcher itself always lives in <home>/bin. Then, in order:
      Windows: a copy in %LOCALAPPDATA%\\Microsoft\\WindowsApps, which Windows
               keeps on every user's PATH, so `tgap` works at once - even in
               this terminal; plus <home>/bin added to the user PATH in the
               registry as a backup for new terminals.
      macOS / Linux: a link in a folder that is ALREADY on PATH and writable
               (~/.local/bin, ~/bin, /usr/local/bin, /opt/homebrew/bin);
               otherwise ~/.local/bin plus a PATH line in the shell startup
               files, for new terminals.
    Nothing here can fail the installation: every step is best effort, and
    the full path of the launcher is always printed as a fallback.
    Returns a report dict (used by tests and by `tgap path`). '''
    scripts=home/'bin'
    scripts.mkdir(parents=True,exist_ok=True)
    py=python_path(home)
    report={'launcher':None,'works_now':False,'new_terminal':False,'where':[],'problems':[]}
    if _is_windows():
        text='@echo off\r\n"'+str(py)+'" -B -m tgap_cli --home "'+str(home)+'" %*\r\n'
        launcher=scripts/'tgap.cmd'
        launcher.write_text(text,encoding='utf-8')
        report['launcher']=str(launcher)
        apps=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'Microsoft'/'WindowsApps'
        if apps.is_dir():
            target=apps/'tgap.cmd'
            if _is_ours(target):
                try:
                    _place(target,launcher,text)
                    report['where'].append(str(target))
                    report['works_now']=report['works_now'] or _on_path(apps)
                except OSError as failure:
                    report['problems'].append(f'could not write {target} ({failure})')
            else:
                report['problems'].append(f'{target} belongs to another program; left alone')
        try:
            if _windows_user_path_add(scripts):
                report['new_terminal']=True
            report['where'].append(str(scripts)+' (user PATH)')
        except Exception as failure:
            report['problems'].append(f'could not update the user PATH ({failure})')
        if _on_path(scripts):
            report['works_now']=True
    else:
        import shlex
        text='#!/bin/sh\nexec '+shlex.quote(str(py))+' -B -m tgap_cli --home '+shlex.quote(str(home))+' "$@"\n'
        launcher=scripts/'tgap'
        launcher.write_text(text,encoding='utf-8')
        launcher.chmod(0o755)
        report['launcher']=str(launcher)
        candidates=[Path.home()/'.local'/'bin',Path.home()/'bin',Path('/usr/local/bin'),Path('/opt/homebrew/bin')]
        for directory in candidates:
            if not _on_path(directory):
                continue
            target=directory/'tgap'
            try:
                if not _is_ours(target):
                    report['problems'].append(f'{target} belongs to another program; left alone')
                    continue
                if not directory.exists():
                    if Path.home() not in directory.parents:
                        continue
                    directory.mkdir(parents=True,exist_ok=True)
                if not os.access(directory,os.W_OK):
                    continue
                _place(target,launcher,text)
                report['where'].append(str(target))
                report['works_now']=True
                break
            except OSError as failure:
                report['problems'].append(f'could not write {target} ({failure})')
        if not report['works_now']:
            local=Path.home()/'.local'/'bin'
            try:
                if _is_ours(local/'tgap'):
                    _place(local/'tgap',launcher,text)
                    report['where'].append(str(local/'tgap'))
                changed=_unix_profile_add(local)
                report['new_terminal']=bool(changed) or _on_path(local)
                if changed:
                    report['where'].append('PATH line added to '+', '.join(changed))
            except OSError as failure:
                report['problems'].append(f'could not set up ~/.local/bin ({failure})')
    return report


def _print_path_report(report):
    print()
    if report['works_now']:
        print('  The tgap command is ready: type  tgap start')
    elif report['new_terminal']:
        print('  The tgap command works in NEW terminals. Open a new terminal, then type:  tgap start')
    else:
        print('  The tgap command could not be put on your PATH automatically.')
    for problem in report['problems']:
        print('  (note: '+problem+')')
    print('  Always works, in any terminal:')
    quoted=f'"{report["launcher"]}"' if ' ' in report['launcher'] else report['launcher']
    print('    '+('& ' if _is_windows() and ' ' in report['launcher'] else '')+quoted+' start'
          +('      (PowerShell)' if _is_windows() and ' ' in report['launcher'] else ''))
    print('    or, from the TGAP folder:  '+('py run.py start' if _is_windows() else 'python3 run.py start'))


class StepFailed(Exception):
    ''' An install step failed; the message is already user-facing. '''


def quiet_step(title,args,home,log_name):
    ''' Run one install step with ONE line on screen; pip's full output goes
    to a log file. On failure, show the last lines of that log and explain. '''
    logs=home/'logs'
    logs.mkdir(parents=True,exist_ok=True)
    log=logs/f'{log_name}.log'
    print(f'  {title} ...',end='',flush=True)
    with open(log,'w',encoding='utf-8',errors='replace') as handle:
        result=subprocess.run([str(a) for a in args],stdout=handle,stderr=subprocess.STDOUT,
                              env=child_environment(home))
    if result.returncode==0:
        print(' done')
        return
    print(' FAILED',flush=True)
    text=log.read_text(encoding='utf-8',errors='replace')
    tail=[line for line in text.splitlines() if line.strip()][-6:]
    lower=text.lower()
    # "(from versions: none)" means pip saw NO versions at all: it could not
    # reach the package index. A genuinely unsupported Python lists the
    # versions it did see.
    if 'from versions: none' in lower or any(k in lower for k in (
            'proxyerror','connection','timed out','getaddrinfo','name resolution',
            'network is unreachable','could not fetch','max retries')):
        why='No internet connection reached the Python package index (pypi.org). Check you are online; behind a proxy, set HTTPS_PROXY=http://proxy:port first.'
    elif 'ssl' in lower or 'certificate' in lower:
        why='A security certificate check failed, usually because a company network intercepts HTTPS. Try another network, or set PIP_CERT to your company certificate.'
    elif 'no matching distribution' in lower or 'requires-python' in lower:
        why=f'These libraries are not published for Python {sys.version.split()[0]}. Install Python 3.11 or 3.12 and run the install again.'
    elif 'permission' in lower or 'access is denied' in lower:
        why='A file is locked - usually antivirus or another terminal running TGAP. Close other TGAP windows and run the install again.'
    elif 'no space' in lower or 'errno 28' in lower:
        why='The disk is full. TGAP needs about 1 GB free.'
    else:
        why='See the last lines of the log below.'
    raise StepFailed(f'{title} failed. {why}\n    Last lines of {log}:\n      '+'\n      '.join(tail)+
                     '\n    Fix the cause and run the same install command again - it continues safely.')


def install(args,home):
    root=source_path()
    home.mkdir(parents=True,exist_ok=True)
    print(f'Installing TGAP into {home}')
    target=unpack(home,args.sandbox_source)
    py=python_path(home)
    tgn=args.tgn or (not args.yes and question('Install optional TGN libraries (Torch and PyTorch Geometric, ~300 MB)?'))
    finance=args.finance or (not args.yes and question('Install optional finance libraries (yfinance and statsmodels)?'))
    previous_path=home/'installation.json'
    previous=json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    # An environment left behind by a Python that was since upgraded or
    # removed cannot start; rebuild it instead of failing inside pip.
    if py.exists() and subprocess.run([str(py),'-c','pass'],capture_output=True).returncode!=0:
        print('  The existing environment was made by a Python that is no longer available; rebuilding it.')
        shutil.rmtree(home/'.venv',ignore_errors=True)
    if not py.exists():
        print('  Creating an isolated Python environment ...',end='',flush=True)
        venv.EnvBuilder(with_pip=True).create(home/'.venv')
        print(' done')
    quiet_step('Updating pip',[py,'-m','pip','install','--upgrade','pip'],home,'install-pip')
    quiet_step('Installing libraries (first time: 1-3 minutes)',[py,'-m','pip','install','-r',target/'requirements.txt'],home,'install-libraries')
    # Keep the research checkout editable, including scripts and documentation.
    quiet_step('Linking this TGAP checkout',[py,'-m','pip','install','--no-deps','-e',root],home,'install-checkout')
    # Modern editable installs keep their metadata in the environment; the
    # *.egg-info folder setuptools leaves in the checkout is only a build
    # leftover, so remove it to keep the user's folder clean.
    for leftover in root.glob('*.egg-info'):
        shutil.rmtree(leftover,ignore_errors=True)
    if tgn:
        quiet_step('Installing PyTorch (CPU, ~300 MB)',[py,'-m','pip','install','torch','--index-url','https://download.pytorch.org/whl/cpu'],home,'install-torch')
        quiet_step('Installing PyTorch Geometric',[py,'-m','pip','install','torch_geometric'],home,'install-torch-geometric')
    if finance:
        quiet_step('Installing finance libraries',[py,'-m','pip','install','-r',root/'requirements-finance.txt'],home,'install-finance')
    config=target/'config.json'
    existing=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    existing.update(tgap_source=str(root),host=existing.get('host','127.0.0.1'),port=existing.get('port',8080),secure_cookies=existing.get('secure_cookies',False))
    config.write_text(json.dumps(existing,indent=2),encoding='utf-8')
    users=target/'users.txt'
    password=None
    if not users.exists():
        password=secrets.token_urlsafe(15)
        users.write_text('# username:password:role\n# Roles: admin or participant. No colon in username/password.\nresearcher:'+password+':admin\n',encoding='utf-8')
        if os.name!='nt': users.chmod(0o600)
    execute([py,'-m','pip','freeze'],cwd=root) if args.verbose else None
    (home/'installation.json').write_text(json.dumps(dict(source=str(root),workbench=str(target),tgn=tgn or previous.get('tgn',False),finance=finance or previous.get('finance',False)),indent=2),encoding='utf-8')
    path_report=None
    if not args.no_path:
        try:
            path_report=register_launcher(home)
        except Exception as failure:          # never fail an installation here
            print(f'  (could not register the tgap command: {failure})')
    print()
    print('TGAP is installed.')
    if password:
        print()
        print('  Your first account (save the password somewhere private):')
        print('    username: researcher')
        print('    password: '+password)
    print()
    print('  Start the workbench :  tgap start')
    print('  Stop it             :  tgap stop')
    print('  Run the examples    :  tgap run examples')
    print(f'  Accounts file       :  {users}')
    if path_report:
        _print_path_report(path_report)
    else:
        print('\n  (--no-path: the tgap command was not registered. Run it as: '
              + ('py run.py start' if os.name=='nt' else 'python3 run.py start')+')')


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
        import errno
        import socket
        with socket.socket() as sock:
            try: sock.bind((config['host'],config['port']))
            except OSError as failure:
                inUse=failure.errno in (errno.EADDRINUSE,getattr(errno,'WSAEADDRINUSE',10048),10013)
                if inUse:
                    raise ValueError(f"Port {config['port']} is already in use by another program. "
                                     f"Start on another port, for example: tgap start --port {config['port']+10}")
                raise ValueError(f"Cannot listen on {config['host']}:{config['port']} ({failure.strerror or failure}). "
                                 "Check the host in --host (normally 127.0.0.1) and that no firewall or "
                                 "security software blocks it.")
        (target/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        (data/'service.stopped').unlink(missing_ok=True)
        command=[str(python_path(home)),str(target/'sandbox'/'serve.py'),'--home',str(target)]
        flags=(subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS) if os.name=='nt' else 0
        with open(data/'launcher.log','ab') as log:
            proc=subprocess.Popen(command,cwd=target,stdout=log,stderr=log,stdin=subprocess.DEVNULL,
                                  creationflags=flags,start_new_session=os.name!='nt',
                                  env=child_environment(home))
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
    # The easy examples and demos go through run.py, which runs each example
    # on its own and explains any failure in plain English. --no-venv: this
    # managed environment already has every library run.py needs.
    mapping={'examples':['run.py','--no-venv','examples'],'demos':['run.py','--no-venv','demos'],
             'paper':['-m','experiments.synthetic_evaluation'],
             'evaluation':['-m','experiments.synthetic_evaluation'],   # old name, same evaluation
             'download':['-m','realdata.download'],'real-data':['-m','realdata.run_real_data'],
             'compare':['-m','realdata.compare_datasets'],'ncommunity':['-m','realdata.run_ncommunity'],
             'tgn':['-m','realdata.run_tgn'],'tgn-stability':['-m','realdata.run_tgn_stability'],
             'publication':['-m','realdata.make_publication'],'tests':['-m','unittest','discover','-s','tests'],
             'finance':['-m','finance.experimentationDatamining'],
             'finance-tgap':['-m','finance.run_finance']}
    if args.workflow=='script':
        # Run ANY Python file - an example, or your own study written with the
        # wrapper - inside the managed environment, with TGAP importable.
        if not args.arguments:
            raise ValueError('Say which file to run, for example: tgap run script examples/wrapper/01_five_lines.py')
        given=Path(args.arguments[0]).expanduser()
        script=given if given.is_file() else Path(info['source'])/given
        if not script.is_file():
            raise ValueError('There is no file called '+args.arguments[0]+' (looked in the current folder and in the TGAP folder '+str(info['source'])+').')
        existing=os.environ.get('PYTHONPATH')
        execute([python_path(home),str(script.resolve()),*args.arguments[1:]],cwd=info['source'],
                extra_env={'PYTHONPATH':os.pathsep.join([str(info['source'])]+([existing] if existing else []))})
        return
    if args.workflow.startswith('tgn') and not info['tgn']:
        raise ValueError('TGN was not installed. Run tgap install --tgn --yes.')
    # Cached stock prices need no extra library; downloading new ones needs
    # the finance group, and the workflow says so in plain English if missing.
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
    subs.add_parser('path',help='Make the tgap command work in your terminal again (repairs PATH).')
    runner=subs.add_parser('run',help='Run a research workflow using the managed Python environment.')
    runner.add_argument('workflow',choices=['examples','script','demos','paper','evaluation','download','real-data','compare','ncommunity','tgn','tgn-stability','publication','tests','finance','finance-tgap'])
    runner.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    if args.command=='start' and args.port is not None and not 1<=args.port<=65535:
        parser.error('Port must be between 1 and 65535.')
    global HOME_FOR_CHILDREN
    try:
        home=home_path(args.home)
        HOME_FOR_CHILDREN=home
        if args.command in ('install','start','run'):
            # This process too (venv creation and ensurepip run in-process):
            # private temp folder and UTF-8, exactly like the child processes.
            import tempfile
            os.environ.update(child_environment(home))
            tempfile.tempdir=None
        if args.command=='install':install(args,home)
        elif args.command=='path':
            setup(home)
            _print_path_report(register_launcher(home))
        elif args.command=='run':research(args,home)
        else:service(args,home)
    except KeyboardInterrupt:
        print('\nTGAP: stopped by you (Ctrl+C). Nothing is broken; run the command again any time.',file=sys.stderr)
        raise SystemExit(130)
    except StepFailed as error:
        print('\nTGAP: '+str(error),file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        print('TGAP: '+explain_step_failure(args,error),file=sys.stderr)
        raise SystemExit(1)
    except PermissionError as error:
        print(f"TGAP: a file could not be written ({error.filename or error}). On Windows this usually "
              "means it is open in another program (Excel, an editor, a second terminal running TGAP) "
              "or locked by antivirus. Close it and run the command again.",file=sys.stderr)
        raise SystemExit(1)
    except (ValueError,OSError) as error:
        print('TGAP: '+str(error),file=sys.stderr)
        raise SystemExit(1)


def explain_step_failure(args,error):
    ''' A failed child process, in plain English. Its own output is
    already on the screen above this message. '''
    command=' '.join(str(c) for c in error.cmd)
    if args.command=='install':
        if ' pip ' in f' {command} ':
            return ('installing libraries failed (see pip\'s messages above). Most common causes: no '
                    'internet connection, a proxy (set HTTPS_PROXY=http://proxy:port and retry), or '
                    'antivirus locking files. Fix that and run the same install command again - it '
                    'resumes safely.')
        return 'creating the Python environment failed (see the messages above). Run the install again.'
    if args.command=='run':
        return (f"the '{args.workflow}' workflow stopped with an error (see the messages above). "
                'Your earlier results are kept. If the message mentions a missing library, run: '
                'tgap install --yes')
    return f'a step failed: {command} (exit code {error.returncode}).'
