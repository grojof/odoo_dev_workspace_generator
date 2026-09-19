---
type: how-to
title: "Setting up a WSL Ubuntu 24.04 host"
description: "Step-by-step: install Ubuntu 24.04 on WSL 2 and make it ready to run odoo_dwg."
audience: [developer]
updated: 2026-09-17
---

# Setting up a WSL Ubuntu 24.04 host

`odoo_dwg` runs **on a Linux host** — it never creates one for you. This guide walks through the shortest
supported path on a Windows machine: Ubuntu 24.04 on WSL 2, ready to run the tool and to host the
workspaces it generates.

Every command is copy-paste ready. Nothing is hardcoded: names, users, and passwords are asked for by the
console. Lines starting with `#` are comments and can be pasted along with the rest.

**Prerequisites:** Windows 11, or Windows 10 version 2004 (build 19041) or later.

> Not on Windows? Skip to [step 5](#5-get-the-tool) — on a bare Ubuntu 24.04 server or container the rest
> applies unchanged.

---

## 1. Install WSL and Ubuntu 24.04

Open **PowerShell as Administrator** (right-click → *Run as administrator*):

```powershell
wsl --install -d Ubuntu-24.04
```

This enables the WSL and Virtual Machine Platform components, installs the Linux kernel, sets WSL 2 as the
default, and installs Ubuntu 24.04. **Restart Windows** if it asks you to.

Useful while choosing:

```powershell
wsl --list --online     # every distribution available for download
wsl --list --verbose    # what you already have installed, and its WSL version
```

If the install stalls at 0.0%, repeat it with `--web-download`:

```powershell
wsl --install --web-download -d Ubuntu-24.04
```

## 2. Create your Linux user

Launch the distribution — from the Start menu ("Ubuntu 24.04"), from Windows Terminal, or:

```powershell
wsl -d Ubuntu-24.04
```

On first launch the console **asks you** for a UNIX username and password. Choose whatever you like; it has
nothing to do with your Windows account. While typing the password nothing appears on screen — that is
normal. This user becomes the default one and can use `sudo`.

Forgot it later? From PowerShell:

```powershell
wsl -d Ubuntu-24.04 -u root    # then, inside: passwd <your-user>
```

## 3. Check the machine is sane

Inside Ubuntu:

```bash
lsb_release -a        # expect: Ubuntu 24.04 LTS (noble)
python3 --version     # expect: Python 3.12.x — the tool needs 3.12 or newer (see docs/support-matrix.md)
systemctl status      # expect: "State: running" — systemd manages PostgreSQL later
```

`systemd` is the default on current Ubuntu images. If `systemctl` complains that it is not running, enable
it once and restart WSL:

```bash
printf '[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf
exit
```

```powershell
wsl --shutdown          # in PowerShell; the next launch starts with systemd
```

## 4. (Optional) Give the instance your own name

`Ubuntu-24.04` is the image name. If you want a dedicated instance with a name of your choice — one per
client, per project, or a disposable one — export it and import it back under that name. PowerShell asks
for the values, so nothing is hardcoded:

```powershell
# Suggestions: name -> OdooDev, folder -> C:\WSL\OdooDev (any name and path work)
$Name     = Read-Host "Name for the new WSL instance"
$Folder   = Read-Host "Folder where its virtual disk will live"
$Snapshot = "$env:USERPROFILE\Downloads\$Name.tar"

wsl --export Ubuntu-24.04 $Snapshot
New-Item -ItemType Directory -Force -Path $Folder | Out-Null
wsl --import $Name $Folder $Snapshot --version 2
```

An imported instance logs in as `root` and ignores the launcher's default-user setting, so declare your
user inside it:

```powershell
wsl -d $Name
```

```bash
# Inside the new instance, as root — it asks which existing user should log in by default:
read -rp "Default user for this instance: " wsluser
printf '[user]\ndefault=%s\n' "$wsluser" | tee -a /etc/wsl.conf
exit
```

```powershell
wsl --terminate $Name        # restart it so the setting applies
wsl --set-default $Name      # optional: plain `wsl` now opens this instance
wsl --list --verbose         # confirm it is there, version 2
```

Housekeeping, whenever you need it:

```powershell
wsl --terminate <name>      # stop one instance
wsl --shutdown              # stop everything
wsl --export <name> <file>  # back it up to a .tar
wsl --unregister <name>     # DELETE it permanently, data included
```

## 5. Get the tool

**Store the code in the Linux file system (`~`), never under `/mnt/c`** — Windows paths are much slower
from Linux and mangle permissions and line endings.

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git curl ca-certificates

# Git identity — the console asks, nothing is assumed:
read -rp "Your name for Git commits: " gitname && git config --global user.name "$gitname"
read -rp "Your e-mail for Git commits: " gitmail && git config --global user.email "$gitmail"

cd ~
git clone https://github.com/grojof/odoo_dev_workspace_generator.git
cd odoo_dev_workspace_generator
python3 -m odoo_dwg --help          # smoke test: the CLI answers
```

The tool has **zero runtime dependencies** — the standard library is enough, no virtual environment needed
to run it.

## 6. Prepare the host with `provision`

The tool checks and prepares the host itself. Start read-only:

```bash
python3 -m odoo_dwg provision       # menu → "Check host readiness"
```

The table shows what is missing: build dependencies, PostgreSQL and its development role, wkhtmltopdf,
and optionally Node and `uv`. Then run **Apply** from the same menu: it asks for `sudo`, shows the
full plan, and only runs it after you confirm.

```
+-------+-------------------------+------------------------------------------+
| State | Capability              | Detail                                   |
+-------+-------------------------+------------------------------------------+
| OK    | Host release            | Ubuntu 24.04 LTS (noble)                 |
| MISS  | PostgreSQL              | not installed                            |
+-------+-------------------------+------------------------------------------+
```

Details and the full capability list: [`provisioning.md`](provisioning.md).

## 7. (Optional) `uv` for other Python versions

Needed for migrations with OpenUpgrade, and for workspaces on an Odoo version whose supported Python range
excludes this host's 3.12 (see [`support-matrix.md`](support-matrix.md)):

- **`uv`** provides the per-version Python interpreters. `provision check` reports it but does not install
  it — follow the official instructions: <https://docs.astral.sh/uv/getting-started/installation/>. Reopen
  the shell afterwards and confirm with `uv --version`.

See [`migration.md`](migration.md).

## 8. (Optional) Editor and terminal

- **VS Code**: install the [WSL extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl)
  in Windows, then from inside Ubuntu run `code .` in the project folder.
- **Windows Terminal** gives every distribution its own tab: <https://learn.microsoft.com/en-us/windows/terminal/install>.
- To browse the Linux files from Explorer: `explorer.exe .` (the dot matters), or `\\wsl$\<instance>\home\<user>`.

## 9. (Optional) Working on the tool itself

Only if you are going to change `odoo_dwg`'s code:

```bash
cd ~/odoo_dev_workspace_generator
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # pytest + ruff; the tool itself still has no dependencies

python -m pytest -q
python -m ruff check .
```

Conventions, checks, and the spec-first flow: [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

## What this guide deliberately leaves out

- **No firewall or `fail2ban`.** A WSL instance is not exposed to the network the way a server is; Windows
  owns the perimeter. Hardening belongs to a production host guide, not to a development one.
- **No SSH server.** WSL is reached with `wsl -d <name>`. Install `openssh-server` only if you really need
  to reach it from another machine.
- **No `.tar` rootfs download or manual import.** `wsl --install -d Ubuntu-24.04` is the supported path and
  keeps the image updatable; step 4 covers custom names on top of it.

## Sources

- [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install) — Microsoft Learn.
- [Basic commands for WSL](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) — Microsoft Learn.
- [Set up a WSL development environment](https://learn.microsoft.com/en-us/windows/wsl/setup/environment) —
  Microsoft Learn (user creation, file-storage performance, VS Code).
- [Use systemd to manage Linux services with WSL](https://learn.microsoft.com/en-us/windows/wsl/systemd) —
  Microsoft Learn.
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/) — Astral.
