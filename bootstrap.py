"""Run the standard-library CLI from a checkout before pip installation."""
import sys

# Keep the checkout free of __pycache__ folders.
sys.dont_write_bytecode = True
from pathlib import Path

if sys.version_info < (3,10):
    version='.'.join(map(str,sys.version_info[:3]))
    raise SystemExit(f'TGAP requires Python 3.10 or later, but the launcher selected Python {version} at {sys.executable}. Install a newer Python or fix your PATH and retry.')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tgap_cli.cli import main

if __name__ == '__main__':
    main()
