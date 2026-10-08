# Easy installation and self-hosting

TGAP provides a standard-library bootstrap that creates an isolated Python
environment, installs core/web dependencies, and asks separately about optional
TGN and finance libraries. No manual virtual-environment activation is needed.

## Windows

Open PowerShell in the TGAP checkout for the first install. The checkout
launcher bootstraps Python and installs the `tgap` command:

```powershell
.\tgap.cmd install
```

Answer the two optional-library questions. The launcher offers the official
signed Python installer when Python is missing. Existing Python must be 3.10
or newer. After installation **open a new terminal** so the updated user PATH
is loaded:

```powershell
tgap start
tgap status
tgap stop
```

The first installation prints your generated `researcher` password. Accounts
are in `%USERPROFILE%\.tgap\workbench\users.txt`. Never commit that file.

## Linux / macOS

Install Python 3.10+ first, including venv support on distributions that split
it into a separate package. From the checkout, run the bootstrap launcher once;
after that, use the installed `tgap` command:

```sh
sh ./tgap install
# If ~/.local/bin is not already on PATH:
export PATH="$HOME/.local/bin:$PATH"
tgap start
tgap stop
```

The portable code supports these platforms, but this delivery was executed
and browser-tested on Windows Server. macOS/Linux runtime verification remains
to be performed on those operating systems.

## What start and stop mean

`start` runs the same local web workbench, opens the browser, and supervises
its Python server. It does not launch every expensive research evaluation.
The default is loopback-only `http://127.0.0.1:8080`, protected by the local
account file. Use `tgap start --port 8090` if 8080 is occupied; use
`--no-browser` for terminal-only startup. Intentional remote binding is
available through `--host 0.0.0.0`.

`stop` closes the supervised server and leaves the environment, users and
results intact. PID checks avoid terminating unrelated processes. Automatic
machine-boot startup is configured separately for the VPS deployment, not
silently installed on a participant's own computer.

## Optional dependencies and unattended install

```powershell
tgap install --yes                  # core/web only; no optional prompts
tgap install --yes --tgn            # add CPU Torch and torch_geometric
tgap install --yes --finance        # add yfinance and statsmodels
```

Interactive installation asks about both groups. Previously installed groups
remain recorded on a later install. Torch can require the Microsoft VC++
runtime on Windows. Package downloads require internet; bundled synthetic and
processed real-data examples then run without external dataset requests.

Custom installation directory:

```powershell
.\tgap.cmd --home D:\TGAP install
D:\TGAP\bin\tgap.cmd start
D:\TGAP\bin\tgap.cmd stop
```

`TGAP_HOME` also selects the installation directory. `--no-path` skips PATH
changes for a temporary installation. `--sandbox-source` is an operator/developer
override; regular users consume the bundled workbench automatically.

## Research workflows

```powershell
tgap run examples
tgap run evaluation
tgap run paper
tgap run download
tgap run real-data email_eu_core
tgap run compare
tgap run ncommunity email_eu_core
tgap run tgn email_eu_core
tgap run tgn-stability email_eu_core
tgap run publication
tgap run tests
tgap run finance --graphs 20
```

These run inside the managed environment with the checkout as working directory.
They can overwrite generated research outputs. Raw data is fetched on demand
by download/real-data runners. TGN and finance commands check their installation
flags and explain how to add the optional libraries.

## Deployment and source separation

The VPS website source, accounts and study data are at
`C:\catalyst\tgap-sandbox`, outside this Git repository. The current online
service binds port 8080 and is controlled by that directory's `service.ps1`.
The self-host launcher lives in this repository. Its distribution includes a
deterministic `tgap_cli/data/sandbox.zip` snapshot of the sibling web project.
This makes a TGAP checkout self-contained without requiring the sibling folder
on users' devices. Credentials/config/live data are excluded from the bundle.

After editing the sibling website, refresh its portable snapshot:

```powershell
python scripts/bundle-sandbox.py --source C:/catalyst/tgap-sandbox
```

The archive includes web source, assets, requirements and processed fixtures.
Core TGAP mathematics remains in `core/`; the website imports it through the
configured source path. The wheel exposes the `tgap` entry point, but this
first release's research workflow commands are documented for a source checkout,
which retains finance scripts, tests, and full research documentation.

## Troubleshooting

- **Command not found:** open a new terminal, or use the checkout launcher.
- **Port busy:** choose another port; TGAP never takes over another application.
- **Startup failed:** inspect `.tgap/workbench/data/launcher.log` and `server.log`.
- **Wrong password:** edit your installation's `users.txt`, not repository files.
- **Missing optional group:** rerun installation with its explicit flag.
- **Custom code rejected:** use the documented graph-only Python subset online;
  run complex transformers locally against the full TGAP contract.
- **Reproducibility:** retain seed, dataset cohort metadata, achieved deltas,
  validity flags, and the complete downloaded JSON.
