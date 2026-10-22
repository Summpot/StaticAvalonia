"""Resolve upstream inputs and apply optional source patches."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SKIASHARP_REPO = "https://github.com/mono/SkiaSharp.git"


def read_url(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8-sig")


def resolve_ref(ref):
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        return ref.lower()
    if not ref or ref.startswith("-") or any(c.isspace() for c in ref):
        raise ValueError("Invalid upstream ref")
    candidates = [ref] if ref.startswith("refs/") else [f"refs/tags/{ref}", f"refs/heads/{ref}"]
    refs = subprocess.check_output(
        ["git", "ls-remote", "--exit-code", SKIASHARP_REPO,
         *candidates, *(f"{name}^{{}}" for name in candidates)], text=True
    )
    found = dict((name, sha) for sha, name in (line.split() for line in refs.splitlines()))
    for name in candidates:
        if name in found:
            return found.get(f"{name}^{{}}", found[name])
    raise ValueError(f"Upstream ref does not exist: {ref}")


def package_versions(xml):
    root = ET.fromstring(xml)
    properties = {element.tag.rsplit("}", 1)[-1]: element.text.strip()
                  for group in root.iter() if group.tag.rsplit("}", 1)[-1] == "PropertyGroup"
                  for element in group if element.text}
    versions = {}
    for element in root.iter():
        package = element.get("Include") or element.get("Update")
        version = element.get("Version") or element.findtext("Version")
        if package in ("SkiaSharp", "HarfBuzzSharp") and version:
            for _ in range(10):
                expanded = re.sub(r"\$\(([^)]+)\)", lambda m: properties.get(m[1], m[0]), version)
                if expanded == version:
                    break
                version = expanded
            if "$" not in version:
                versions[package] = version
    return versions


def detect_avalonia(tag):
    versions = {}
    for path in ("Directory.Packages.props", "build/SkiaSharp.props", "build/HarfBuzzSharp.props"):
        url = f"https://raw.githubusercontent.com/AvaloniaUI/Avalonia/{urllib.parse.quote(tag, safe='')}/{path}"
        try:
            versions.update(package_versions(read_url(url)))
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        if len(versions) == 2:
            break
    if len(versions) != 2:
        raise ValueError(f"Cannot determine SkiaSharp and HarfBuzzSharp versions for Avalonia {tag}")
    for version in versions.values():
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?", version):
            raise ValueError(f"Unsupported package version: {version}")
    commit = resolve_ref(f"v{versions['SkiaSharp']}")
    return {"avalonia_version": tag, "skiasharp_version": versions["SkiaSharp"],
            "harfbuzz_version": versions["HarfBuzzSharp"], "skiasharp_ref": commit}


def apply_patches(source, patches):
    source, patches = Path(source).resolve(), Path(patches).resolve()
    for name, target in (("skiasharp", source), ("skia", source / "externals/skia")):
        for patch in sorted((patches / name).glob("*.patch")):
            subprocess.run(["git", "-C", str(target), "apply", "--check", str(patch)], check=True)
            subprocess.run(["git", "-C", str(target), "apply", str(patch)], check=True)
            print(f"Applied {name}/{patch.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("ref")
    detect = commands.add_parser("detect")
    detect.add_argument("tag")
    apply = commands.add_parser("apply")
    apply.add_argument("--source", default="src_skiasharp")
    apply.add_argument("--patches", default="patches")
    args = parser.parse_args()
    if args.command == "apply":
        apply_patches(args.source, args.patches)
        return
    result = {"commit": resolve_ref(args.ref)} if args.command == "resolve" else detect_avalonia(args.tag)
    print(json.dumps(result, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8", newline="\n") as stream:
            for key, value in result.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("Workflow output cannot contain newlines")
                stream.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
