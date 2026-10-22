"""Build the pinned ANGLE source as Windows static libraries."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = ("libANGLE_static.lib", "libGLESv2_static.lib")


def run(*args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True, shell=os.name == "nt")


def source_config():
    return json.loads((ROOT / "native/angle/source.json").read_text(encoding="utf-8"))


def apply_patches(source, stage):
    for patch in sorted((ROOT / "patches/angle" / stage).glob("*.patch")):
        run("git", "apply", "--check", patch, cwd=source)
        run("git", "apply", patch, cwd=source)


def prepare(arch):
    source = ROOT / "src_angle"
    if source.exists():
        raise ValueError("src_angle already exists; use a clean checkout for a native build")
    config = source_config()
    source.mkdir()
    run("git", "init", source)
    run("git", "remote", "add", "origin", config["repository"], cwd=source)
    run("git", "fetch", "--depth=1", "origin", config["commit"], cwd=source)
    run("git", "checkout", "--detach", "FETCH_HEAD", cwd=source)
    apply_patches(source, "deps")
    run("python", "scripts/bootstrap.py", cwd=source)
    run("gclient", "sync", "-f", "-D", "-R", cwd=source)
    apply_patches(source, "build")
    build = ROOT / "out/angle" / f"win-{arch}"
    build.mkdir(parents=True)
    args = (ROOT / "native/angle/args.win.gn").read_text(encoding="utf-8")
    (build / "args.gn").write_text(args.replace('target_cpu = "x64"', f'target_cpu = "{arch}"'),
                                   encoding="utf-8", newline="\n")


def coff_machine(path):
    data = Path(path).read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError(f"Not a COFF archive: {path}")
    offset = 8
    machines = set()
    while offset + 60 <= len(data):
        header = data[offset:offset + 60]
        size = int(header[48:58])
        name = header[:16].decode("ascii").strip()
        member = data[offset + 60:offset + 60 + size]
        if name not in ("/", "//", "/SYM64/") and len(member) >= 8:
            machine = int.from_bytes(member[6:8] if member[:4] == b"\0\0\xff\xff" else member[:2], "little")
            if machine in (0x8664, 0xAA64, 0x14C, 0x1C0):
                machines.add(machine)
        offset += 60 + size + size % 2
    if len(machines) != 1:
        raise ValueError(f"Expected one COFF architecture in {path}, found {machines}")
    return machines.pop()


def collect(arch):
    build = ROOT / "out/angle" / f"win-{arch}"
    artifacts = ROOT / "artifacts" / f"angle-win-{arch}"
    artifacts.mkdir(parents=True, exist_ok=True)
    expected = {"x64": 0x8664, "arm64": 0xAA64}[arch]
    for name in LIBRARIES:
        library = build / "obj" / name
        if coff_machine(library) != expected:
            raise ValueError(f"Wrong architecture in {library}")
        shutil.copy2(library, artifacts / name)
    (artifacts / "ANGLE-source.json").write_text(json.dumps(source_config(), indent=2) + "\n", encoding="utf-8")
    source = ROOT / "src_angle"
    for path in source.rglob("*"):
        if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT")):
            relative = path.relative_to(source)
            if any(part in (".git", "out") for part in relative.parts):
                continue
            target = artifacts / "licenses/angle" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "collect"))
    parser.add_argument("--arch", choices=("x64", "arm64"), required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.arch)
    elif args.command == "collect":
        collect(args.arch)
    else:
        source = ROOT / "src_angle"
        build = ROOT / "out/angle" / f"win-{args.arch}"
        run("gn", "gen", build, cwd=source)
        run("autoninja", "-C", build, "libANGLE_static", "libGLESv2_static", cwd=source)


if __name__ == "__main__":
    main()
