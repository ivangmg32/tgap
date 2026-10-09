# Install and run TGAP

[Documentation index](README.md) · [Project overview](../README.md)

This guide takes you from a fresh checkout to a running local workbench. TGAP
installs into its own Python environment, so you do not need to create or
activate a virtual environment yourself.

## Before you begin

- A TGAP source checkout.
- Windows: no Python setup is needed; the installer can offer the official
  Python installer if it cannot find Python.
- Linux or macOS: Python 3.10 or newer, with `venv` support. Some Linux
  distributions provide `venv` in a separate package.
- Internet access during installation to download Python packages.

## 1. Install TGAP

Run the checkout launcher once. It creates the managed environment, installs
the local workbench, asks whether to add optional research packages, and creates
a first account.

**Windows — PowerShell, from the TGAP checkout:**

```powershell
.\tgap.cmd install
```

**Linux or macOS — from the TGAP checkout:**

```sh
sh ./tgap install
```

The first account is named `researcher`. The installer prints its generated
password once. Save it securely. The account file is stored in your TGAP home
folder; do not commit or share it.

The installer adds the `tgap` command to your user PATH. Open a new terminal
after installation. On Linux/macOS, if the command is still unavailable, add
`~/.local/bin` to PATH in the current terminal and continue there:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

## 2. Start the workbench

In a terminal where the updated PATH is available, run:

```text
tgap start
```

TGAP starts the local service and opens the browser. Visit
`http://127.0.0.1:8080` if the browser does not open, then sign in with the
account printed by the installer.

The service listens on your own computer only by default. Your experiments and
account stay in your TGAP home folder. To check service state or stop it:

```text
tgap status
tgap stop
```

Stopping the service keeps your account, experiments, and installed packages.
Start it again any time with `tgap start`.

## 3. Try a research example

```text
tgap run examples
```

This runs the included examples in the managed Python environment. Other
available workflows include:

```text
tgap run evaluation
tgap run paper
tgap run download
tgap run real-data email_eu_core
tgap run compare
tgap run ncommunity email_eu_core
tgap run publication
tgap run tests
```

Some workflows download data or write generated results into the checkout.
Check the workflow documentation before starting a large run.

## Optional research packages

During installation, TGAP asks whether you want the optional TGN and finance
packages. You can install either group later:

```text
tgap install --tgn --yes
tgap install --finance --yes
```

Or install only the base workbench without prompts:

```text
tgap install --yes
```

TGN workflows need the TGN group:

```text
tgap run tgn email_eu_core
tgap run tgn-stability email_eu_core
```

The finance workflow needs the finance group:

```text
tgap run finance --graphs 20
```

The TGN group installs CPU PyTorch and PyTorch Geometric. On some Windows
systems, PyTorch also needs the Microsoft VC++ runtime. Finance workflows use
yfinance and statsmodels.

## Common commands

| Command | What it does |
| --- | --- |
| `tgap install` | Create or update the managed environment |
| `tgap start` | Start the workbench and open the browser |
| `tgap start --port 8090` | Start on another port |
| `tgap start --no-browser` | Start without opening a browser |
| `tgap status` | Show whether the workbench is running |
| `tgap stop` | Stop the service and keep local data |
| `tgap run examples` | Run the introductory examples |
| `tgap --help` | Show command help |

For the first install, use the checkout launcher: `.\tgap.cmd install` in
PowerShell or `sh ./tgap install` on Linux/macOS. After that, run commands
using `tgap` from a new terminal.

## Choose a different installation folder

By default, TGAP stores its environment and workbench data in `~/.tgap` (on
Windows, under your user profile). Choose a custom home during the first
installation by putting `--home` before `install`:

```powershell
.\tgap.cmd --home D:\TGAP install
```

Then use the launcher created in that folder:

```powershell
D:\TGAP\bin\tgap.cmd start
D:\TGAP\bin\tgap.cmd status
D:\TGAP\bin\tgap.cmd stop
```

You can also set `TGAP_HOME`. `--no-path` skips PATH registration. `--host` can
change the address that the service listens on; keep the default loopback
address unless you intend to make the service reachable from other computers
and have configured appropriate network security.

## Troubleshooting

**`tgap` is not recognized or not found**

Open a new terminal after installation. If it is still unavailable, run the
checkout launcher to install again, or add `~/.local/bin` to PATH on
Linux/macOS.

**The installer says Python 3.10 or later is missing, but it is installed**

Close and reopen PowerShell so it reloads your PATH. Check which interpreter
Windows can find:

```powershell
py -3 --version
python --version
python3 --version
```

At least one command should report Python 3.10 or later. The checkout launcher
checks each of these commands and uses the first supported version. If none is
available, add your Python installation to PATH or allow TGAP to install its
own Python runtime.

**Port 8080 is already in use**

Choose another port:

```text
tgap start --port 8090
```

**The service did not start**

Check `launcher.log` and `server.log` in the workbench data folder under your
TGAP home directory.

**I lost the generated password**

The account file is `users.txt` under the workbench folder in your TGAP home.
It contains account credentials; keep it private.

**An optional workflow says its packages are missing**

Install the needed group with `tgap install --tgn --yes` or
`tgap install --finance --yes`, then run the workflow again.

## More help

- [TGAP overview and examples](../README.md)
- [Study dashboard and exports](15-research-dashboard.md) (researcher role)
- [Real data workflows](../realdata/README.md)
- [Self-hosting and deployment notes](13-sandbox-and-self-hosting-knowledge.md)
