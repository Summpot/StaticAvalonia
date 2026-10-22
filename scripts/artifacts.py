"""Build identities, verified component bundles, and immutable package candidates."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from upstream import read_url, resolve_ref

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "Summpot.StaticAvalonia"
RIDS = ("win-x64", "win-arm64", "linux-x64", "linux-arm64", "osx-x64", "osx-arm64")
RECIPES = {
    "skiasharp": ("native/static", "patches/skiasharp", "patches/skia", "scripts/upstream.py", ".github/workflows/build-skiasharp.yml"),
    "angle": ("native/angle", "patches/angle", "scripts/angle.py", ".github/workflows/build-angle.yml"),
    "package": ("nuget/StaticAvalonia", "scripts/artifacts.py", "tests/NativeAotSmoke", ".github/workflows/package-staticavalonia.yml"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def recipe(kind, root=ROOT):
    files = {}
    for name in RECIPES[kind]:
        path = root / name
        for file in sorted(path.rglob("*") if path.is_dir() else [path]):
            if file.is_file() and not any(part in ("bin", "obj", "__pycache__") for part in file.relative_to(root).parts):
                files[file.relative_to(root).as_posix()] = digest(file.read_bytes())
    return files


def identity(component, commit, version, root=ROOT):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A component requires an exact upstream commit")
    value = {"schema": 1, "component": component, "commit": commit, "version": version,
             "recipe": recipe(component, root)}
    value["tag"] = f"native-{component}-{digest(canonical(value))[:32]}"
    return value


def required(component):
    result = set()
    for rid in RIDS if component == "skiasharp" else RIDS[:2]:
        names = ("libANGLE_static.lib", "libGLESv2_static.lib") if component == "angle" else (
            ("skia.lib", "SkiaSharp.lib", "libHarfBuzzSharp.lib") if rid.startswith("win-") else
            ("libskia.a", "libSkiaSharp.a", "libHarfBuzzSharp.a"))
        result.update(f"{rid}/{name}" for name in names)
    return result


def inventory(directory):
    directory = Path(directory)
    return {file.relative_to(directory).as_posix(): digest(file.read_bytes())
            for file in sorted(directory.rglob("*")) if file.is_file()}


def check_component(manifest):
    seed = {key: manifest[key] for key in ("schema", "component", "commit", "version", "recipe")}
    if seed["schema"] != 1 or seed["component"] not in ("skiasharp", "angle"):
        raise ValueError("Unsupported component manifest")
    tag = f"native-{seed['component']}-{digest(canonical(seed))[:32]}"
    if manifest["tag"] != tag:
        raise ValueError("Component identity does not match its manifest")
    if "files" in manifest and not required(seed["component"]).issubset(manifest["files"]):
        raise ValueError("Component does not contain all required native libraries")


def producer():
    return {key: os.environ.get(env, "local") for key, env in
            (("repository", "GITHUB_REPOSITORY"), ("commit", "GITHUB_SHA"),
             ("workflow", "GITHUB_WORKFLOW_REF"), ("run_id", "GITHUB_RUN_ID"))}


def bundle(manifest, incoming, output):
    check_component(manifest)
    incoming, output = Path(incoming), Path(output)
    with tempfile.TemporaryDirectory() as directory:
        native = Path(directory)
        for rid in RIDS if manifest["component"] == "skiasharp" else RIDS[:2]:
            source = incoming / f"native-{manifest['component']}-{rid}"
            if manifest["component"] == "skiasharp" and rid.startswith("osx-"):
                source = incoming / "native-skiasharp-osx" / rid
            shutil.copytree(source, native / rid)
        manifest = dict(manifest, files=inventory(native), producer=producer())
        check_component(manifest)
        output.mkdir(parents=True, exist_ok=True)
        archive = output / f"{manifest['component']}-native.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as stream:
            for name in manifest["files"]:
                stream.write(native / name, name)
        manifest["archive"] = archive.name
        manifest["sha256"] = digest(archive.read_bytes())
        write_json(output / "component.json", manifest)
    return manifest


def extract_component(manifest, archive, destination):
    check_component(manifest)
    if digest(Path(archive).read_bytes()) != manifest["sha256"]:
        raise ValueError("Component archive checksum mismatch")
    with zipfile.ZipFile(archive) as stream:
        if set(stream.namelist()) != set(manifest["files"]) or len(stream.namelist()) != len(manifest["files"]):
            raise ValueError("Component archive inventory mismatch")
        for name in stream.namelist():
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name or ":" in name:
                raise ValueError("Unsafe component archive path")
            data = stream.read(name)
            if digest(data) != manifest["files"][name]:
                raise ValueError(f"Component file checksum mismatch: {name}")
            target = Path(destination) / name
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f"Components contain conflicting files: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def gh(*args):
    return subprocess.run(["gh", *map(str, args)], capture_output=True, text=True, encoding="utf-8")


def repository():
    return os.environ.get("GITHUB_REPOSITORY", "Summpot/StaticAvalonia")


def release(tag):
    result = gh("api", f"repos/{repository()}/releases/tags/{urllib.parse.quote(tag, safe='')}")
    if result.returncode:
        if "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    value = json.loads(result.stdout)
    if value["draft"]:
        raise ValueError("Draft releases are not reusable build inputs")
    return value


def download(tag, name, directory):
    if Path(name).name != name or name.startswith("-"):
        raise ValueError("Invalid release asset name")
    result = gh("release", "download", tag, "--repo", repository(), "--pattern", name,
                "--dir", directory, "--clobber")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return Path(directory) / name


def cached_component(expected):
    existing = release(expected["tag"])
    if existing is None:
        return False
    names = {asset["name"] for asset in existing["assets"]}
    if not {"component.json", f"{expected['component']}-native.zip"}.issubset(names):
        raise ValueError("Existing component release is incomplete")
    with tempfile.TemporaryDirectory() as directory:
        actual = json.loads(download(expected["tag"], "component.json", directory).read_text())
    check_component(actual)
    if any(actual[key] != value for key, value in expected.items()):
        raise ValueError("Existing component release has a different identity")
    return True


def store(tag, files, title, notes, target=None):
    if release(tag) is not None:
        with tempfile.TemporaryDirectory() as directory:
            for path in files:
                if digest(download(tag, path.name, directory).read_bytes()) != digest(path.read_bytes()):
                    raise ValueError(f"Refusing to replace existing release asset: {path.name}")
        return
    commit = target or os.environ.get("GITHUB_SHA")
    if not commit:
        raise ValueError("Release persistence requires a GitHub workflow commit")
    result = gh("release", "create", tag, *files, "--repo", repository(), "--target", commit,
                "--title", title, "--notes", notes, "--prerelease", "--latest=false")
    if result.returncode:
        raise RuntimeError(result.stderr)


def fetch_component(component, tag, destination):
    if not tag.startswith(f"native-{component}-"):
        raise ValueError("Unexpected component tag")
    with tempfile.TemporaryDirectory() as directory:
        manifest = json.loads(download(tag, "component.json", directory).read_text())
        if manifest["tag"] != tag or manifest["component"] != component:
            raise ValueError("Downloaded component does not match the requested tag")
        archive = download(tag, manifest["archive"], directory)
        extract_component(manifest, archive, destination)
    write_json(Path(destination).parent / f"{component}.json", manifest)
    return manifest


def package_plan(skia, angle, avalonia, harfbuzz, revision, root=ROOT):
    for value in (avalonia, harfbuzz, skia["version"]):
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?", value):
            raise ValueError(f"Invalid package version: {value}")
    if revision and not re.fullmatch(r"[0-9A-Za-z]+", revision):
        raise ValueError("Invalid package revision")
    suffix = f"-{revision}" if revision else ""
    version = f"{skia['version']}-avalonia.{avalonia}{suffix}"
    result = {"schema": 1, "package_id": PACKAGE_ID, "version": version,
              "avalonia_version": avalonia, "skiasharp_version": skia["version"],
              "harfbuzz_version": harfbuzz, "revision": revision,
              "components": {item["component"]: {key: item[key] for key in ("tag", "commit", "sha256")}
                             for item in (skia, angle)}, "recipe": recipe("package", root)}
    result["tag"] = f"package-staticavalonia-{version}-{digest(canonical(result))[:16]}"
    result["release_tag"] = f"staticavalonia-{avalonia}-skia-{skia['version']}{suffix}"
    return result


def package_identity(path):
    with zipfile.ZipFile(path) as archive:
        nuspec, = [name for name in archive.namelist() if name.endswith(".nuspec")]
        root = ET.fromstring(archive.read(nuspec))
        metadata = {node.tag.rsplit("}", 1)[-1]: node.text for node in root.iter()}
        return metadata["id"], metadata["version"]


def check_package(manifest, directory):
    seed = {key: value for key, value in manifest.items()
            if key not in ("tag", "release_tag", "file", "sha256", "producer")}
    expected = f"package-staticavalonia-{manifest['version']}-{digest(canonical(seed))[:16]}"
    if manifest["schema"] != 1 or manifest["package_id"] != PACKAGE_ID or manifest["tag"] != expected:
        raise ValueError("Package candidate identity mismatch")
    path = Path(directory) / manifest["file"]
    if Path(manifest["file"]).name != manifest["file"] or digest(path.read_bytes()) != manifest["sha256"]:
        raise ValueError("Package checksum mismatch")
    if package_identity(path) != (PACKAGE_ID, manifest["version"]):
        raise ValueError("NuGet package identity mismatch")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if not {f"runtimes/{name.split('/')[0]}/native/{name.split('/')[1]}"
                for component in ("skiasharp", "angle") for name in required(component)}.issubset(names):
            raise ValueError("NuGet package is missing native libraries")
        if "buildTransitive/Summpot.StaticAvalonia.targets" not in names:
            raise ValueError("NuGet package is missing its build targets")
    return path


def fetch_package(tag, destination):
    if not tag.startswith("package-staticavalonia-"):
        raise ValueError("Expected an exact package candidate tag")
    Path(destination).mkdir(parents=True, exist_ok=True)
    manifest = json.loads(download(tag, "package.json", destination).read_text())
    if manifest["tag"] != tag:
        raise ValueError("Package candidate tag mismatch")
    download(tag, manifest["file"], destination)
    check_package(manifest, destination)
    return manifest


def payload_hash(path):
    with zipfile.ZipFile(path) as archive:
        return digest(canonical({name: digest(archive.read(name)) for name in sorted(archive.namelist())
                                 if name != ".signature.p7s"}))


def nuget_exists(manifest, directory):
    local = check_package(manifest, directory)
    package_id, version = PACKAGE_ID.lower(), manifest["version"].lower()
    url = f"https://api.nuget.org/v3-flatcontainer/{package_id}/{version}/{package_id}.{version}.nupkg"
    try:
        with urllib.request.urlopen(url, timeout=120) as response, tempfile.TemporaryFile() as remote:
            shutil.copyfileobj(response, remote)
            remote.seek(0)
            if payload_hash(remote) != payload_hash(local):
                raise ValueError("This NuGet version already exists with different package contents; increment revision")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise
    return True


def outputs(values):
    print(json.dumps(values, indent=2))
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8", newline="\n") as stream:
            for key, value in values.items():
                value = str(value).lower() if isinstance(value, bool) else str(value)
                if "\n" in value or "\r" in value:
                    raise ValueError("Multiline workflow output")
                stream.write(f"{key}={value}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "bundle", "store-component", "fetch-component",
                        "plan-package", "seal-package", "store-package", "fetch-package", "check-nuget", "wait-nuget", "release", "release-plan"))
    parser.add_argument("--component", choices=("skiasharp", "angle"))
    parser.add_argument("--ref", default="release/3.119.4")
    parser.add_argument("--tag")
    parser.add_argument("--input", default="out/component.json")
    parser.add_argument("--incoming", default="out/incoming")
    parser.add_argument("--output", default="out/component")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--avalonia", default="12.1.4")
    parser.add_argument("--harfbuzz", default="8.3.1.3")
    parser.add_argument("--revision", default="r1")
    args = parser.parse_args()
    if args.command == "plan":
        if args.component == "angle":
            config = json.loads((ROOT / "native/angle/source.json").read_text())
            commit, version = config["commit"], config["ref"].replace("/", "-")
        else:
            commit = resolve_ref(args.ref)
            versions = read_url(f"https://raw.githubusercontent.com/mono/SkiaSharp/{commit}/scripts/VERSIONS.txt")
            version, = re.findall(r"^SkiaSharp\s+nuget\s+(\S+)\s*$", versions, re.MULTILINE)
        manifest = identity(args.component, commit, version)
        write_json(args.output, manifest)
        outputs(dict(tag=manifest["tag"], commit=commit, version=version,
                     exists=cached_component(manifest) if args.probe else False))
    elif args.command == "bundle":
        manifest = bundle(json.loads(Path(args.input).read_text()), args.incoming, args.output)
        outputs({"tag": manifest["tag"]})
    elif args.command == "fetch-component":
        manifest = fetch_component(args.component, args.tag, args.output)
        outputs({"tag": manifest["tag"], "version": manifest["version"]})
    elif args.command == "plan-package":
        base = Path(args.input)
        manifest = package_plan(json.loads((base / "skiasharp.json").read_text()),
                                json.loads((base / "angle.json").read_text()), args.avalonia, args.harfbuzz, args.revision)
        write_json(Path(args.output) / "package.json", manifest)
        exists = args.probe and release(manifest["tag"]) is not None
        if exists:
            actual = fetch_package(manifest["tag"], args.output)
            if any(actual[key] != value for key, value in manifest.items()):
                raise ValueError("Package candidate identity mismatch")
        outputs({key: manifest[key] for key in ("tag", "version", "skiasharp_version", "harfbuzz_version")}
                | {"exists": exists})
    elif args.command == "release-plan":
        base = Path(args.input)
        components = [json.loads((base / f"{name}-plan.json").read_text()) for name in ("skiasharp", "angle")]
        proposed = package_plan(*(dict(item, sha256="") for item in components),
                                args.avalonia, args.harfbuzz, args.revision)
        existing = release(proposed["release_tag"])
        if existing is not None:
            with tempfile.TemporaryDirectory() as directory:
                actual = json.loads(download(proposed["release_tag"], "package.json", directory).read_text())
            if any(actual[key] != proposed[key] for key in ("recipe", "version", "harfbuzz_version")) or any(
                actual["components"][item["component"]]["tag"] != item["tag"] for item in components
            ):
                raise ValueError("The published version uses different inputs; increment the package revision")
        outputs({"needed": existing is None})
    else:
        directory = Path(args.output)
        path = directory / ("component.json" if args.command == "store-component" else "package.json")
        if args.command == "fetch-package":
            manifest = fetch_package(args.tag, directory)
        else:
            manifest = json.loads(path.read_text())
        if args.command == "seal-package":
            package, = directory.glob("*.nupkg")
            manifest.update(file=package.name, sha256=digest(package.read_bytes()), producer=producer())
            check_package(manifest, directory)
            write_json(path, manifest)
        elif args.command == "store-component":
            check_component(manifest)
            store(manifest["tag"], [path, directory / manifest["archive"]], manifest["tag"],
                  f"Verified {manifest['component']} native libraries. Source: {manifest['commit']}.")
        elif args.command == "store-package":
            package = check_package(manifest, directory)
            store(manifest["tag"], [path, package], manifest["tag"], "Validated StaticAvalonia package candidate.")
        elif args.command == "check-nuget":
            outputs({"exists": nuget_exists(manifest, directory)})
            return
        elif args.command == "wait-nuget":
            for attempt in range(40):
                if nuget_exists(manifest, directory):
                    break
                if attempt == 39:
                    raise RuntimeError("NuGet has not made this package public; retry publication with the same candidate tag")
                time.sleep(15)
        elif args.command == "release":
            package = check_package(manifest, directory)
            notes = f"NuGet: {PACKAGE_ID} {manifest['version']}\n\n" + "\n".join(
                f"- {name}: [{item['tag']}](https://github.com/{repository()}/releases/tag/{item['tag']})"
                for name, item in manifest["components"].items())
            store(manifest["release_tag"], [path, package], f"StaticAvalonia {manifest['version']}", notes,
                  target=manifest["producer"]["commit"])
            result = gh("release", "edit", manifest["release_tag"], "--repo", repository(), "--prerelease=false", "--latest")
            if result.returncode:
                raise RuntimeError(result.stderr)
        outputs({"tag": manifest["tag"], "version": manifest.get("version", ""), "file": manifest.get("file", "")})


if __name__ == "__main__":
    main()
