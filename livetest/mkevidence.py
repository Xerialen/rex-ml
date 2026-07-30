#!/usr/bin/env python3
"""Wrap a rex-drills raw result in an evidence envelope that identifies the build under test.

Not rtx-testflow/1. The lab suite is unreachable from this machine (see README.md here), so this
produces a self-describing envelope under its own schema id, `rex-drills/1`, which cannot be
confused with a suite envelope.

The point of the envelope is attribution: a tier result is worthless unless the digests say which
binaries produced it. `qwprogs.so` is the artifact the server actually dlopens, so its digest — not
the repo commit — is what proves the ML build ran.

Usage: mkevidence.py <raw.json> <out.json> [--note TEXT ...]
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
import time

RTX = "/home/benjamin-adm/rex-ml/rtx"
PLAYGROUND = f"{RTX}/playground"


def digest(path):
    """md5 + size for a file, following symlinks; None if absent."""
    try:
        real = os.path.realpath(path)
        h = hashlib.md5()
        with open(real, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return {
            "path": path,
            "realpath": real,
            "md5": h.hexdigest(),
            "bytes": os.path.getsize(real),
        }
    except OSError as e:
        return {"path": path, "error": str(e)}


def git(*args):
    try:
        return subprocess.run(
            ["git", "-C", RTX, *args], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"<error: {e}>"


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    raw_path, out_path = sys.argv[1], sys.argv[2]
    notes = []
    argv = sys.argv[3:]
    while argv:
        if argv[0] == "--note":
            notes.append(argv[1])
            argv = argv[2:]
        else:
            argv = argv[1:]

    with open(raw_path) as f:
        raw = json.load(f)

    engine = digest(f"{PLAYGROUND}/mvdsv")
    module = digest(f"{PLAYGROUND}/qw/qwprogs.so")
    built = digest(f"{RTX}/target/release/librtx.so")
    # The staged module and the build output must be the same bytes, or the digests point at
    # something other than what ran. Checked, not assumed.
    module_matches_build = (
        module.get("md5") is not None and module.get("md5") == built.get("md5")
    )

    envelope = {
        "schema": "rex-drills/1",
        "not_": "rtx-testflow/1 — the lab suite was unreachable; see livetest/README.md",
        "tier": raw.get("tier"),
        "kind": raw.get("kind"),
        "status": raw.get("result", {}).get("status", "unknown"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "machine": {
            "host": platform.node(),
            "kernel": platform.release(),
            "arch": platform.machine(),
            "cpus": os.cpu_count(),
        },
        "build": {
            "engine_binary": engine,
            "game_module": module,
            "build_output": built,
            "game_module_matches_build_output": module_matches_build,
            "map": digest(f"{PLAYGROUND}/qw/maps/dm3.bsp"),
            "repo": {
                "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "commit": git("rev-parse", "HEAD"),
                "describe": git("describe", "--always", "--dirty"),
                "dirty": bool(git("status", "--porcelain")),
            },
        },
        "notes": notes,
    }
    if "conditions" in raw:
        envelope["conditions"] = raw["conditions"]
    envelope["result"] = raw.get("result", raw)

    with open(out_path, "w") as f:
        json.dump(envelope, f, indent=1)
    print(f"{out_path}: tier={envelope['tier']} status={envelope['status']}")
    if not module_matches_build:
        print(
            "  WARNING: staged qwprogs.so does not match target/release/librtx.so — "
            "the digests may not identify what ran",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
