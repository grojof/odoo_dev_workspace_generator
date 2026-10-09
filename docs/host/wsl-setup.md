---
type: how-to
title: "Setting up a WSL Ubuntu 24.04 host"
description: "Step by step, from a Windows PC to an Odoo workspace running in its own WSL machine."
tags: [host, wsl, setup]
audience: [developer]
updated: 2026-10-09
---

# Setting up a WSL Ubuntu 24.04 host

From a Windows PC to Odoo running in a workspace made by `odoo_dwg`. Each step is done once, in order. Copy
each block as it is; where a value is yours to choose, the step says so.

The examples call the machine **OdooDevServer** and keep it in **`C:\WSL\OdooDevServer`**. Any name and
folder work; use the same ones in every step.

**You need:** Windows 11, or Windows 10 version 2004 or later, and an internet connection.

## 1. Install WSL

Open **PowerShell as Administrator** (right-click → *Run as administrator*):

```powershell
wsl --install --no-distribution
wsl --update
```

If Windows asks you to restart, restart, and open PowerShell as Administrator again.

## 2. Create the machine

```powershell
wsl --install Ubuntu-24.04 --name OdooDevServer --location C:\WSL\OdooDevServer
```

It downloads Ubuntu 24.04 and opens it. The first time, it asks for a **user name and a password** for the
machine. They are yours to choose and have nothing to do with your Windows account.

- The user-name prompt may already show your Windows name: delete it if you want another one.
- Nothing appears on screen while you type the password. That is normal.

When it shows a prompt such as `adminit@PC:~$`, you are inside the machine. Every next step runs there.

To come back to it later, from PowerShell or the Start menu:

```powershell
wsl -d OdooDevServer
```

## 3. Update Ubuntu

```bash
sudo apt update && sudo apt -y upgrade
```

`sudo` asks for the password you chose in step 2.

## 4. Get odoo_dwg

Use **one** of the two.

**A. From GitHub:**

```bash
git clone https://github.com/grojof/odoo_dev_workspace_generator.git ~/odoo_dev_workspace_generator
```

**B. From a copy you already have on Windows** — for example in `C:\WSL\odoo_dev_workspace_generator`
(`C:\` is `/mnt/c` inside the machine):

```bash
cp -r /mnt/c/WSL/odoo_dev_workspace_generator ~/
```

Either way, the tool now lives in the machine's own disk, which is much faster than working from `/mnt/c`.

## 5. Prepare the machine

```bash
cd ~/odoo_dev_workspace_generator
sudo python3 -m odoo_dwg provision
```

1. Choose **2) Apply (install what's missing)**.
2. *Development PostgreSQL role*: press **Enter** (it keeps `odoo`).
3. Answer **n** to the optional questions (rtlcss, outbound firewall, mail capture).
4. It shows the plan. Answer **y** to apply it. It installs the build dependencies, PostgreSQL and the
   patched wkhtmltopdf, and takes a few minutes.
5. Choose **1) Check host readiness**: every required row must say **OK**. The *PostgreSQL* row shows its
   port, usually `5432` (see the note in step 8). Then **0** to leave.

## 6. Only for Odoo 12, 13 or 14: install uv

Ubuntu 24.04 comes with Python 3.12, which Odoo 15 and later accept. Odoo 12, 13 and 14 need an older Python,
which `uv` provides ([support matrix](../reference/support-matrix.md)). Skip this step otherwise.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
exit
```

Open the machine again (`wsl -d OdooDevServer`); `uv --version` must answer.

## 7. Create a workspace

```bash
cd ~/odoo_dev_workspace_generator
python3 -m odoo_dwg workspace
```

1. Choose **1) Create a workspace**, then **1) New (quick)**.
2. *Workspace name*: a short name, for example `demo`.
3. *Odoo versions*: press **Enter** for `18.0`, or type the ones you want, separated by commas.
4. *OCA repositories*: press **Enter**.
5. It shows the plan. Answer **y**. It downloads Odoo and builds its Python environment, which takes a while
   the first time. Then **0** to leave.

## 8. Start Odoo

For a workspace called `demo` with Odoo 18.0. Its own `README.md` has the same commands with its names and
ports.

```bash
cd ~/odoo-workspaces/demo
createdb -h 127.0.0.1 -p 5432 -U odoo demo
bash scripts/run-odoo18.sh -d demo -i base
```

- `createdb` makes the database; use the port step 5 showed. Only once.
- `-i base` installs Odoo in it. Only the first time; afterwards start it with
  `bash scripts/run-odoo18.sh -d demo`.

Open <http://localhost:8069/web/login> in Windows and log in as **admin** / **admin**. To stop Odoo, press
**Ctrl+C** in the machine's window.

> **Other WSL machines share these ports.** All WSL machines share one network. If another one already uses
> PostgreSQL's port 5432, this machine's PostgreSQL gets the next one (5433); `provision` and the workspace use
> it, and its README shows it. If another machine is already running Odoo on port 8069, stop that machine
> (`wsl --terminate <name>` in PowerShell) before starting this one.

## Next

- What a workspace contains and how to use it: [workspace layout](../workspace/layout.md).
- Every menu action: [commands](../reference/commands.md).
- What `provision` installs and why: [provisioning](provisioning.md).

## Sources

- [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install) — Microsoft Learn.
- [Basic commands for WSL](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) — Microsoft Learn.
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/) — Astral.
