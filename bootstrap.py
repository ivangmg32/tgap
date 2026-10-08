"""Run the standard-library CLI from a checkout before pip installation."""
import sys
from pathlib import Path

if sys.version_info < (3,10):
    raise SystemExit('TGAP requires Python 3.10 or later. Install a newer Python and retry.')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tgap_cli.cli import main

if __name__ == '__main__':
    main()
