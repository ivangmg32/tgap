#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
TGAP - one file that sets everything up and runs the project.

    python run.py                  quick tour: check + demos + examples (~2 min)
    python run.py all              the full research pipeline (internet, ~20 min)
    python run.py examples         only the easy examples
    python run.py demos examples   any steps, in the order given
    python run.py --list           list every step
    python run.py reset            delete the private environment and caches
    python run.py --help

On Windows, if `python` is not found, use `py run.py` instead.

What it does for you, so nothing has to be set up by hand:
  1. checks your Python version;
  2. creates a private environment in .venv/ (first run only) and installs
     the libraries from requirements.txt into it - nothing is installed
     into your system Python;
  3. points temporary files and caches at .tgap_cache/ inside the project,
     so a broken, full or non-ASCII system TEMP folder cannot break a run;
  4. runs the steps you asked for, and if one fails, prints in plain English
     what went wrong and how to fix it. The full technical details go to
     output/logs/, never to your screen.

This file uses only the Python standard library, and is written so that even
a very old Python can read it far enough to say "please upgrade".
'''

from __future__ import print_function

import os
import sys

MINIMUM_PYTHON = (3, 9)

ROOT = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
#  Small output helpers. ASCII only: they must print on any console.
# --------------------------------------------------------------------------

LINE = "=" * 70


def say(text=""):
    print(text)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def problem(title, explanation, fixes):
    ''' The ONE way this script reports a problem: what happened, why, and
    what to do - in plain English, never a traceback. '''
    say()
    say("  PROBLEM: " + title)
    for line in explanation.strip().splitlines():
        say("    " + line.strip())
    if fixes:
        say("  HOW TO FIX:")
        for fix in fixes:
            say("    - " + fix)


# --------------------------------------------------------------------------
#  1. Python version - checked before anything else is imported.
# --------------------------------------------------------------------------

if sys.version_info < MINIMUM_PYTHON:
    problem(
        "Python {0}.{1} is too old.".format(*sys.version_info[:2]),
        "TGAP needs Python {0}.{1} or newer.".format(*MINIMUM_PYTHON),
        ["Install a current Python from https://www.python.org/downloads/",
         "Windows: during installation tick 'Add python.exe to PATH', "
         "then open a NEW terminal and run:  py run.py",
         "macOS / Linux: run it with the new version, e.g.  python3.12 run.py"])
    sys.exit(1)

import hashlib            # noqa: E402  (after the version gate on purpose)
import importlib          # noqa: E402
import importlib.util     # noqa: E402
import platform           # noqa: E402
import runpy              # noqa: E402
import shutil             # noqa: E402
import subprocess         # noqa: E402
import tempfile           # noqa: E402
import time               # noqa: E402
import traceback          # noqa: E402
import warnings           # noqa: E402

IS_WINDOWS = os.name == "nt"
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")
# The private environment. TGAP_VENV lets one machine keep several (used to
# test several Python versions side by side); normal users never set it.
VENV = os.environ.get("TGAP_VENV") or os.path.join(ROOT, ".venv")
CACHE = os.path.join(ROOT, ".tgap_cache")
LOGS = os.path.join(ROOT, "output", "logs")
REQUIRED_MODULES = ("networkx", "numpy", "pandas", "matplotlib", "scipy",
                    "plotly", "certifi")


# --------------------------------------------------------------------------
#  2. A clean, predictable process environment.
# --------------------------------------------------------------------------

def _writableDirectory(candidates):
    ''' The first candidate folder we can really create and write into. '''
    for folder in candidates:
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".write-test")
            with open(probe, "w") as handle:
                handle.write("ok")
            os.remove(probe)
            return folder
        except Exception:
            continue
    return None


def prepareEnvironment():
    ''' Set every variable that has caused trouble on someone's machine.

    TEMP / TMP / TMPDIR  a project-local temp folder. System temp folders
        are a frequent source of failures: full disks, antivirus locks,
        corporate permission policies, and user names with non-ASCII
        letters (C:\\Users\\Iv\u00e1n\\AppData\\Local\\Temp).
    MPLCONFIGDIR  matplotlib's font cache; it otherwise lives in the home
        folder, which is sometimes read-only or roaming.
    MPLBACKEND=Agg  draw figures to files only - never try to open a window.
    PYTHONIOENCODING / PYTHONUTF8  print and write text as UTF-8 even on a
        Windows console that defaults to cp1252, so a single non-ASCII
        character can never crash a run.
    PYTHONHASHSEED=0  identical results run after run.
    '''
    temporary = _writableDirectory([
        os.path.join(CACHE, "tmp"),
        os.path.join(tempfile.gettempdir(), "tgap-tmp"),
        os.path.join(os.path.expanduser("~"), ".tgap-tmp"),
    ])
    if temporary is None:
        problem("No folder is writable for temporary files.",
                "Neither the project folder, the system TEMP folder nor your "
                "home folder accepted a test file.",
                ["Move the project to a normal folder you own (for example "
                 "Documents\\tgap), not a protected or read-only location.",
                 "Check the disk is not full."])
        sys.exit(1)
    for name in ("TEMP", "TMP", "TMPDIR"):
        os.environ[name] = temporary
    tempfile.tempdir = temporary

    matplotlibCache = _writableDirectory([os.path.join(CACHE, "matplotlib"),
                                          os.path.join(temporary, "mpl")])
    if matplotlibCache:
        os.environ["MPLCONFIGDIR"] = matplotlibCache
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    os.environ["PIP_NO_INPUT"] = "1"

    # This process too: never die on a character the console cannot show.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Always work from the project folder, wherever the user started from.
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)


# --------------------------------------------------------------------------
#  3. The private environment (.venv) and its libraries.
# --------------------------------------------------------------------------

def venvPython():
    if IS_WINDOWS:
        return os.path.join(VENV, "Scripts", "python.exe")
    return os.path.join(VENV, "bin", "python")


def runningInsideVenv():
    try:
        return os.path.samefile(sys.prefix, VENV)
    except Exception:
        return False


def requirementsFingerprint():
    with open(REQUIREMENTS, "rb") as handle:
        content = handle.read()
    return hashlib.sha256(content + sys.version.encode()).hexdigest()


def markerPath():
    return os.path.join(VENV, "tgap-installed.txt")


def _pythonStarts(python):
    if not os.path.exists(python):
        return False
    try:
        return subprocess.run([python, "-c", "pass"], capture_output=True,
                              timeout=120).returncode == 0
    except Exception:
        return False


def librariesImport(python):
    ''' Do the libraries really import in that interpreter? Asked in a
    separate process, so a broken install cannot crash this one. '''
    code = "import " + ", ".join(REQUIRED_MODULES)
    try:
        result = subprocess.run([python, "-c", code], capture_output=True,
                                text=True, timeout=300)
        return result.returncode == 0, (result.stderr or "").strip()
    except Exception as failure:
        return False, str(failure)


def _removeTree(path):
    ''' rmtree that also deletes read-only files (common on Windows). '''
    import stat

    def onError(function, target, _info):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except Exception:
            pass
    shutil.rmtree(path, onerror=onError)


def _logFile(name):
    os.makedirs(LOGS, exist_ok=True)
    return os.path.join(LOGS, "{0}-{1}.log".format(
        name, time.strftime("%Y%m%d-%H%M%S")))


def _runLogged(command, logName, title):
    ''' Run a setup command with its noisy output going to a log file. '''
    log = _logFile(logName)
    with open(log, "w", encoding="utf-8", errors="replace") as handle:
        handle.write("$ " + " ".join(command) + "\n\n")
        handle.flush()
        result = subprocess.run(command, stdout=handle,
                                stderr=subprocess.STDOUT, cwd=ROOT)
    with open(log, encoding="utf-8", errors="replace") as handle:
        output = handle.read()
    return result.returncode, output, log


def _explainInstallFailure(output, log):
    text = output.lower()
    if any(k in text for k in ("proxyerror", "connection", "timed out",
                               "temporary failure in name resolution",
                               "getaddrinfo", "network is unreachable",
                               "could not fetch", "max retries")):
        problem("Could not download the libraries (no internet connection).",
                "pip could not reach the Python package index (pypi.org).",
                ["Check you are online, then run the same command again.",
                 "Behind a university or company proxy?  Windows: "
                 "set HTTPS_PROXY=http://proxy:port   macOS/Linux: "
                 "export HTTPS_PROXY=http://proxy:port   - then run again."])
    elif "ssl" in text or "certificate" in text:
        problem("A security certificate check failed while downloading.",
                "This usually means a company network intercepts HTTPS.",
                ["Try another network (for example a phone hotspot).",
                 "Or ask IT for the proxy certificate and set "
                 "PIP_CERT=path\\to\\certificate.pem before running."])
    elif "no matching distribution" in text or \
            "requires-python" in text or "could not find a version" in text:
        problem("The libraries are not available for this Python version.",
                "Python {0} is newer (or older) than the published packages "
                "support.".format(platform.python_version()),
                ["Install Python 3.12 from https://www.python.org/downloads/ "
                 "and run:  py -3.12 run.py   (Windows)   or   "
                 "python3.12 run.py   (macOS / Linux)",
                 "Then run:  python run.py reset   and try again."])
    elif "permission" in text or "access is denied" in text:
        problem("Windows / the system refused to write a file.",
                "Another program (often an antivirus, or a second TGAP run) "
                "is holding a file inside .venv/.",
                ["Close other terminals and editors that use this folder.",
                 "Run:  python run.py reset   and then try again."])
    elif "no space" in text or "errno 28" in text:
        problem("The disk is full.", "The libraries need about 500 MB.",
                ["Free some disk space and run again."])
    else:
        problem("Installing the libraries failed.",
                "pip reported an error it did not explain clearly.",
                ["Run:  python run.py reset   and try again.",
                 "If it still fails, send the log file below to the "
                 "TGAP maintainers."])
    say("  Full installer output: " + log)


def ensureEnvironment():
    ''' Make sure .venv exists and holds working libraries. Returns the
    Python to use. Prints friendly messages at every step. '''
    python = venvPython()

    if os.path.isdir(VENV) and not _pythonStarts(python):
        # Missing, or left behind by a Python that was since upgraded or
        # uninstalled (the environment points at the old installation).
        say("  The private environment in .venv/ is incomplete or was made "
            "by another Python; rebuilding it.")
        _removeTree(VENV)

    if not os.path.exists(python):
        say("  First run: creating a private Python environment in .venv/ "
            "(about 10 s).")
        code, output, log = _runLogged(
            [sys.executable, "-m", "venv", VENV], "setup-venv",
            "create environment")
        if code != 0 or not os.path.exists(python):
            if "ensurepip" in output or "python3-venv" in output \
                    or "venv" in output and "apt" in output:
                version = "{0}.{1}".format(*sys.version_info[:2])
                problem(
                    "Python's 'venv' module is missing on this system.",
                    "Some Linux distributions ship Python without the part "
                    "that creates environments.",
                    ["Ubuntu / Debian:  sudo apt install python{0}-venv  "
                     "then run again.".format(version),
                     "Or run without a private environment (you install the "
                     "libraries yourself):  python run.py --no-venv"])
            else:
                problem("Could not create the private environment.",
                        "The 'venv' module failed.",
                        ["Run:  python run.py reset   and try again.",
                         "Or:  python run.py --no-venv   to use your "
                         "current Python and its libraries."])
                say("  Details: " + log)
            sys.exit(1)

    fingerprint = requirementsFingerprint()
    installed = None
    if os.path.exists(markerPath()):
        with open(markerPath(), encoding="utf-8") as handle:
            installed = handle.read().strip()

    if installed != fingerprint or not librariesImport(python)[0]:
        say("  Installing the libraries TGAP needs into .venv/ "
            "(first run only, 1-3 minutes)...")
        _runLogged([python, "-m", "pip", "install", "--upgrade", "pip"],
                   "setup-pip", "upgrade pip")       # best effort only
        code, output, log = _runLogged(
            [python, "-m", "pip", "install", "-r", REQUIREMENTS],
            "setup-libraries", "install libraries")
        if code != 0:
            _explainInstallFailure(output, log)
            sys.exit(1)
        ok, why = librariesImport(python)
        if not ok:
            problem("The libraries installed but do not load.",
                    why.splitlines()[-1] if why else "Unknown import error.",
                    ["Run:  python run.py reset   and try again."])
            sys.exit(1)
        with open(markerPath(), "w", encoding="utf-8") as handle:
            handle.write(fingerprint)
        say("  Libraries installed.")
    return python


def installTorch(python):
    ''' Optional: the learned-model (TGN) steps need PyTorch + PyG. '''
    say("  Installing PyTorch (CPU) and PyTorch Geometric - about 300 MB, "
        "a few minutes...")
    code, output, log = _runLogged(
        [python, "-m", "pip", "install", "torch", "--index-url",
         "https://download.pytorch.org/whl/cpu"], "setup-torch", "torch")
    if code == 0:
        code, output, log = _runLogged(
            [python, "-m", "pip", "install", "torch_geometric"],
            "setup-torch-geometric", "torch_geometric")
    if code != 0:
        _explainInstallFailure(output, log)
        return False
    say("  PyTorch installed.")
    return True


# --------------------------------------------------------------------------
#  4. Turning any exception into a plain-English message.
# --------------------------------------------------------------------------

def explain(failure):
    ''' (title, explanation, fixes) for an exception raised by a step. '''
    name = type(failure).__name__
    message = str(failure)
    import errno
    if isinstance(failure, KeyboardInterrupt):
        return ("Stopped by you (Ctrl+C).",
                "Nothing is broken. Finished steps kept their results.",
                ["Run the same command again whenever you like."])
    if isinstance(failure, ModuleNotFoundError):
        module = getattr(failure, "name", "") or message
        if module and module.split(".")[0] in ("torch", "torch_geometric"):
            return ("PyTorch is not installed.",
                    "This step trains a neural network (TGN) and needs "
                    "PyTorch, which is optional and large.",
                    ["Run:  python run.py tgn --with-torch"])
        return ("A Python library is missing: {0}".format(module),
                "The private environment is incomplete.",
                ["Run:  python run.py reset   then run again."])
    if isinstance(failure, PermissionError):
        return ("A file could not be written: {0}".format(
                    getattr(failure, "filename", "") or message),
                "On Windows this almost always means the file is OPEN in "
                "another program - typically a CSV open in Excel or a "
                "picture open in a viewer.",
                ["Close the file (or Excel), then run the step again."])
    if isinstance(failure, MemoryError):
        return ("The computer ran out of memory.",
                "This step needs more RAM than is free right now.",
                ["Close other programs and run again."])
    if isinstance(failure, OSError) and getattr(failure, "errno", None) == \
            errno.ENOSPC:
        return ("The disk is full.", message,
                ["Free some disk space and run again."])
    try:
        import urllib.error
        import ssl
        if isinstance(failure, ssl.SSLError) or "CERTIFICATE_VERIFY" in \
                message:
            return ("A security certificate check failed while downloading.",
                    "This usually means a company network intercepts HTTPS.",
                    ["Try another network (for example a phone hotspot).",
                     "Or download later; everything else works offline."])
        if isinstance(failure, (urllib.error.URLError, ConnectionError,
                                TimeoutError)) or \
                "getaddrinfo" in message or "timed out" in message:
            return ("Could not download a dataset (no internet connection).",
                    "Real datasets are downloaded once, then cached in "
                    "data/. The download did not get through: " + message,
                    ["Check you are online and run the same step again.",
                     "Behind a proxy? set HTTPS_PROXY=http://proxy:port "
                     "(Windows) / export HTTPS_PROXY=... (macOS/Linux)."])
    except ImportError:
        pass
    if isinstance(failure, FileNotFoundError):
        target = getattr(failure, "filename", "") or message
        hint = ["Check the file name and folder in the PARAMETERS block of "
                "the script you edited."]
        if "data" + os.sep in str(target) or "/data/" in str(target):
            hint.insert(0, "Download the real datasets first:  "
                           "python run.py download")
        return ("A file was not found: {0}".format(target),
                "The step expected this file to exist.", hint)
    if name in ("BadGzipFile", "EOFError", "BadZipFile", "ParserError",
                "EmptyDataError"):
        return ("A data file is damaged or not in the expected format.",
                message,
                ["If it is a downloaded dataset: delete it from data/ and "
                 "run:  python run.py download",
                 "If it is your own CSV: check it has a header row and the "
                 "column names set in the PARAMETERS block."])
    if isinstance(failure, (ValueError, KeyError, TypeError)):
        return ("A setting or input value is not valid.",
                "{0}: {1}".format(name, message),
                ["If you edited a PARAMETERS block, check the value you "
                 "changed (spelling of column names, numbers in range).",
                 "Otherwise send the log file below to the maintainers."])
    return ("Unexpected error: {0}".format(name), message,
            ["Run the same step again.",
             "If it repeats, send the log file below to the maintainers."])


# --------------------------------------------------------------------------
#  5. The steps.
# --------------------------------------------------------------------------

SKIPPED = "SKIPPED"
NCOMMUNITY_DATASETS = ["bitcoin_alpha", "bitcoin_otc", "email_eu_core",
                       "sx_mathoverflow", "tgbl_enron", "tgbl_uci"]


class Skip(Exception):
    ''' A step that cannot run here, for a reason that is not an error. '''


class PartlyFailed(Exception):
    ''' Some parts of a step failed; each was already reported. '''


# The technical log of the current run (set in main).
CURRENT_LOG = None


def reportFailure(failure, where):
    ''' Explain an exception in plain English and log its traceback. '''
    title, explanation, fixes = explain(failure)
    with open(CURRENT_LOG, "a", encoding="utf-8", errors="replace") as handle:
        handle.write("\n\n===== {0} failed =====\n".format(where))
        handle.write(traceback.format_exc())
    problem(title, explanation, fixes)
    say("  Technical details were saved to: " + CURRENT_LOG)


def _withArgv(argv, function):
    saved = sys.argv
    sys.argv = argv
    try:
        return function()
    finally:
        sys.argv = saved


def stepCheck():
    import paths
    say("  Python      : {0} ({1})".format(platform.python_version(),
                                            sys.executable))
    say("  System      : {0} {1} ({2})".format(platform.system(),
                                                platform.release(),
                                                platform.machine()))
    for module in REQUIRED_MODULES:
        loaded = importlib.import_module(module)
        say("  {0:<12s}: {1}".format(module,
                                     getattr(loaded, "__version__", "ok")))
    try:
        import torch    # noqa: F401
        say("  {0:<12s}: {1}  (TGN steps available)".format(
            "torch", torch.__version__))
    except Exception:
        say("  {0:<12s}: not installed (optional; only the TGN steps need "
            "it)".format("torch"))
    say("  Temp folder : " + tempfile.gettempdir())
    say("  Outputs     : " + paths.OUTPUT)
    import core      # the package itself must import cleanly
    say("  TGAP core   : imports OK ({0} public names)".format(
        len([n for n in dir(core) if not n.startswith("_")])))


def stepDemos():
    path = os.path.join(ROOT, "examples", "synthetic_demos.py")
    _withArgv([path, "--no-show"],
              lambda: runpy.run_path(path, run_name="__main__"))


def exampleScripts():
    folder = os.path.join(ROOT, "examples")
    return sorted(os.path.join(folder, name) for name in os.listdir(folder)
                  if name[:2].isdigit() and name.endswith(".py"))


def stepExamples():
    ''' Every example runs on its own: one broken example (for instance a
    PARAMETERS block you are still editing) never stops the others. '''
    scripts = exampleScripts() + [
        os.path.join(ROOT, "examples", "MyCustomTransformation.py")]
    failed = []
    for index, path in enumerate(scripts, 1):
        name = os.path.basename(path)
        say()
        say("  ---- example {0}/{1}: {2} ----".format(index, len(scripts),
                                                    name))
        try:
            _withArgv([path],
                      lambda: runpy.run_path(path, run_name="__main__"))
        except KeyboardInterrupt:
            raise
        except BaseException as failure:      # noqa: B902 - by design
            if isinstance(failure, SystemExit) and not failure.code:
                continue
            reportFailure(failure, "example " + name)
            failed.append(name)
    if failed:
        raise PartlyFailed("{0} of {1} examples need attention: {2}".format(
            len(failed), len(scripts), ", ".join(failed)))


def stepSynthetic():
    from experiments import synthetic_evaluation
    synthetic_evaluation.runAll()


def stepDownload():
    from realdata import download
    download.downloadAll()


def stepRealData():
    from realdata import run_real_data, compare_datasets
    run_real_data.main([])
    compare_datasets.main([])


def stepNCommunity():
    from realdata import run_ncommunity
    run_ncommunity.main(list(NCOMMUNITY_DATASETS))


def stepTgn():
    from core.TgnModel import TORCH_AVAILABLE
    if not TORCH_AVAILABLE:
        raise Skip("PyTorch is not installed (optional). To include the TGN "
                   "steps run:  python run.py tgn --with-torch")
    from realdata import run_tgn, run_tgn_stability
    run_tgn.main([])
    run_tgn_stability.main([])


def stepPublication():
    from realdata import make_publication
    make_publication.main()


def stepTests():
    import unittest
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"),
                                                top_level_dir=ROOT)
    result = unittest.TextTestRunner(verbosity=1, stream=sys.stdout,
                                     warnings="ignore").run(suite)
    if not result.wasSuccessful():
        raise AssertionError("{0} test(s) failed and {1} raised an error; "
                             "see the list above.".format(
                                 len(result.failures), len(result.errors)))


# name: (title, function, writes to)
STEPS = {
    "check": ("Check the environment", stepCheck, None),
    "demos": ("Guided demos on synthetic graphs", stepDemos, None),
    "examples": ("Easy examples (your own data / model / concept)",
                 stepExamples, "output/examples/"),
    "synthetic": ("Synthetic known-truth evaluation (RQ1-RQ8)",
                  stepSynthetic, "output/synthetic/"),
    "download": ("Download the 8 real datasets (once, ~100 MB)",
                 stepDownload, "data/"),
    "realdata": ("TGAP on the 8 real datasets + comparison", stepRealData,
                 "output/real_data/, output/comparison/"),
    "ncommunity": ("N-community sweep (N = 2, 3, 4)", stepNCommunity,
                   "output/ncommunity/"),
    "tgn": ("Learned model (TGN), needs PyTorch", stepTgn,
            "output/tgn/, output/tgn_stability/"),
    "publication": ("Paper figures and tables", stepPublication,
                    "output/publication/"),
    "tests": ("The automatic test suite", stepTests, None),
}
QUICK = ["check", "demos", "examples"]
ALL = ["check", "demos", "examples", "synthetic", "download", "realdata",
       "ncommunity", "tgn", "publication"]


def runStep(name, log):
    title, function, _ = STEPS[name]
    say()
    say(LINE)
    say("  STEP: {0}  ({1})".format(name, title))
    say(LINE)
    start = time.time()
    try:
        with warnings.catch_warnings():
            # Library deprecation notices are not errors and only confuse.
            warnings.simplefilter("ignore")
            function()
        return "OK", time.time() - start
    except Skip as reason:
        say("  Skipped: {0}".format(reason))
        return SKIPPED, time.time() - start
    except PartlyFailed as summary:
        say()
        say("  " + str(summary))
        return "FAILED", time.time() - start
    except KeyboardInterrupt:
        raise
    except BaseException as failure:          # noqa: B902 - by design
        if isinstance(failure, SystemExit) and not failure.code:
            return "OK", time.time() - start
        reportFailure(failure, "step " + name)
        return "FAILED", time.time() - start


def printHelp():
    say(__doc__.split("What it does")[0].rstrip())
    say()
    say("Steps (run any of them by name):")
    for name, (title, _, target) in STEPS.items():
        say("  {0:<12s} {1}{2}".format(
            name, title, "  -> " + target if target else ""))
    say()
    say("Groups:  (nothing) = " + " ".join(QUICK))
    say("         all       = " + " ".join(ALL))
    say()
    say("Options: --with-torch   also install PyTorch for the TGN steps")
    say("         --no-venv      use the current Python and its libraries")
    say("         reset          delete .venv/ and .tgap_cache/, start fresh")


def main(argv):
    argv = list(argv)
    if any(a in ("-h", "--help", "help", "--list", "list") for a in argv):
        printHelp()
        return 0

    if "reset" in argv:
        for folder in (VENV, CACHE):
            if os.path.isdir(folder):
                _removeTree(folder)
        say("Removed .venv/ and .tgap_cache/. The next run sets everything "
            "up again from scratch.")
        return 0

    withTorch = "--with-torch" in argv
    noVenv = "--no-venv" in argv
    names = [a for a in argv if not a.startswith("--")]
    if not names:
        names = list(QUICK)
    # "all" may be combined with other steps (e.g. "all tests"); each step
    # still runs once, in order.
    expanded = []
    for name in names:
        for step in (ALL if name == "all" else [name]):
            if step not in expanded:
                expanded.append(step)
    names = expanded
    unknown = [n for n in names if n not in STEPS]
    if unknown:
        problem("Unknown step: " + ", ".join(unknown),
                "Valid steps are: " + ", ".join(STEPS) + ", all.",
                ["Run:  python run.py --help"])
        return 2

    prepareEnvironment()

    # Not yet inside the private environment: set it up, then hand over to
    # a copy of this script running inside it.
    if not noVenv and not runningInsideVenv():
        say(LINE)
        say("  TGAP - preparing (Python {0} on {1})".format(
            platform.python_version(), platform.system()))
        say(LINE)
        python = ensureEnvironment()
        if withTorch:
            installTorch(python)
        child = subprocess.Popen([python, os.path.abspath(__file__)]
                                 + [a for a in argv if a != "--with-torch"],
                                 cwd=ROOT)
        while True:
            try:
                return child.wait()
            except KeyboardInterrupt:
                # Ctrl+C reaches the inner run too; it stops cleanly and
                # prints the message, so this launcher just waits for it.
                continue

    if noVenv:
        missing = [m for m in REQUIRED_MODULES
                   if importlib.util.find_spec(m) is None]
        if missing:
            problem("Libraries missing in this Python: " + ", ".join(missing),
                    "--no-venv uses your current Python as it is.",
                    ["Install them:  python -m pip install -r "
                     "requirements.txt",
                     "Or drop --no-venv and let run.py manage everything."])
            return 1
        if withTorch:
            installTorch(sys.executable)

    global CURRENT_LOG
    log = CURRENT_LOG = _logFile("run")
    results = []
    try:
        for name in names:
            status, seconds = runStep(name, log)
            results.append((name, status, seconds))
    except KeyboardInterrupt:
        say("\n  Stopped by you (Ctrl+C). Finished steps kept their results.")
        return 130

    say()
    say(LINE)
    say("  SUMMARY")
    say(LINE)
    for name, status, seconds in results:
        target = STEPS[name][2]
        say("  {0:<8s} {1:<12s} {2:>6.0f} s   {3}".format(
            status, name, seconds, target or ""))
    failed = [n for n, s, _ in results if s == "FAILED"]
    say()
    if failed:
        say("  {0} step(s) need attention: {1}. The messages above say "
            "how to fix each one.".format(len(failed), ", ".join(failed)))
        say("  Technical log: " + log)
        return 1
    say("  Everything finished successfully.")
    if "examples" in names:
        say("  Your example outputs (CSV + PNG): " +
            os.path.join(ROOT, "output", "examples"))
    if os.path.exists(log) and os.path.getsize(log) == 0:
        os.remove(log)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        say("\n  Stopped by you (Ctrl+C). Run again whenever you like.")
        sys.exit(130)
