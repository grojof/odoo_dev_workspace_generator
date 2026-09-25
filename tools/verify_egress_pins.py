#!/usr/bin/env python3
"""Check the pinned OpenSnitch and Mailpit releases against their upstream sources.

Developer tooling, not part of the package: ``odoo_dwg`` never imports this. Run it
before trusting or moving the pins in ``odoo_dwg/egress.py``:

    python tools/verify_egress_pins.py

What it does (see docs/host/egress-control.md, "Keeping the versions current"):

1. OpenSnitch: downloads the pinned release's ``readme.txt.asc`` — the
   maintainer-signed checksum list — and checks that each pinned SHA-512 appears
   in it for its file. When ``gpg`` is installed it also verifies the signature
   against the maintainer key published with the same release, and requires the
   signing key to be the one pinned in ``egress.py``.
2. Mailpit: reads the digest GitHub records for the pinned release asset and
   compares it with the pinned SHA-256 (Mailpit publishes no checksum file).
3. For both, reports the latest release, so a newer one is noticed.

Exits 0 when every pin matches its source, 1 otherwise. It never edits anything.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_dwg import egress  # noqa: E402

TIMEOUT = 30
API = "https://api.github.com/repos/{repo}/releases/{which}"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "odoo_dwg-verify"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def _release(repo: str, which: str) -> dict:
    return json.loads(_get(API.format(repo=repo, which=which)))


def _check_opensnitch() -> bool:
    ok = True
    tag = f"v{egress.OPENSNITCH_VERSION}"
    signed = _get(f"{egress.OPENSNITCH_BASE_URL}/readme.txt.asc").decode("utf-8", "replace")
    for name, sha512 in egress.OPENSNITCH_PACKAGES:
        found = f"{sha512}  bins/{name}" in signed
        print(f"  {'ok ' if found else 'BAD'}  {name}: SHA-512 {'listed' if found else 'NOT listed'}"
              " in the signed readme.txt.asc")
        ok &= found
    if shutil.which("gpg"):
        with tempfile.TemporaryDirectory() as home:
            key = _get(f"{egress.OPENSNITCH_BASE_URL}/gustavo_iniguez_goia.asc")
            (Path(home) / "key.asc").write_bytes(key)
            (Path(home) / "readme.txt.asc").write_text(signed)
            env = {"GNUPGHOME": home, "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
            subprocess.run(["gpg", "--batch", "-q", "--import", "key.asc"], cwd=home, env=env,
                           capture_output=True, check=False)
            result = subprocess.run(["gpg", "--batch", "--verify", "readme.txt.asc"], cwd=home,
                                    env=env, capture_output=True, text=True, check=False,
                                    encoding="utf-8", errors="replace")
            signer = next((line.split("key ")[-1].strip() for line in result.stderr.splitlines()
                           if "using" in line and "key" in line), "?")
            good = "Good signature" in result.stderr and signer == egress.OPENSNITCH_SIGNING_KEY
            print(f"  {'ok ' if good else 'BAD'}  signature: {'good' if good else 'NOT good'}"
                  f", signing key {signer} (pinned {egress.OPENSNITCH_SIGNING_KEY})")
            ok &= good
    else:
        print("  --   signature: gpg not installed, not verified")
    latest = _release("evilsocket/opensnitch", "latest")["tag_name"]
    print(f"  {'ok ' if latest == tag else 'NEW'}  latest release {latest} (pinned {tag})")
    return ok


def _check_mailpit() -> bool:
    tag = f"v{egress.MAILPIT_VERSION}"
    release = _release("axllent/mailpit", f"tags/{tag}")
    asset = next((a for a in release["assets"] if a["name"] == "mailpit-linux-amd64.tar.gz"), None)
    digest = (asset or {}).get("digest") or ""
    ok = digest == f"sha256:{egress.MAILPIT_SHA256}"
    print(f"  {'ok ' if ok else 'BAD'}  mailpit-linux-amd64.tar.gz: GitHub digest {digest or 'missing'}")
    latest = _release("axllent/mailpit", "latest")["tag_name"]
    print(f"  {'ok ' if latest == tag else 'NEW'}  latest release {latest} (pinned {tag})")
    return ok


def main() -> int:
    print(f"OpenSnitch {egress.OPENSNITCH_VERSION}")
    opensnitch = _check_opensnitch()
    print(f"Mailpit {egress.MAILPIT_VERSION}")
    mailpit = _check_mailpit()
    ok = opensnitch and mailpit
    print("\nEvery pin matches its source." if ok else "\nA pin does not match its source.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
