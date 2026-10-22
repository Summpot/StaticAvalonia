import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts


class ComponentTests(unittest.TestCase):
    def test_recipe_changes_only_invalidate_the_affected_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "native/static/args.win.gn"
            path.parent.mkdir(parents=True)
            path.write_text("before", encoding="utf-8")
            skia = artifacts.identity("skiasharp", "a" * 40, "3.119.4", root)
            angle = artifacts.identity("angle", "b" * 40, "chromium-7151", root)
            (root / "README.md").write_text("documentation", encoding="utf-8")
            self.assertEqual(skia, artifacts.identity("skiasharp", "a" * 40, "3.119.4", root))
            path.write_text("after", encoding="utf-8")
            self.assertNotEqual(skia["tag"], artifacts.identity("skiasharp", "a" * 40, "3.119.4", root)["tag"])
            self.assertEqual(angle, artifacts.identity("angle", "b" * 40, "chromium-7151", root))

    def fixture(self, directory, component="angle"):
        incoming = directory / "incoming"
        manifest = artifacts.identity(component, "a" * 40, "3.119.4" if component == "skiasharp" else "chromium-7151")
        for name in artifacts.required(component):
            rid, file = name.split("/")
            base = incoming / f"native-{component}-{rid}"
            if rid.startswith("osx-"):
                base = incoming / "native-skiasharp-osx" / rid
            base.mkdir(parents=True, exist_ok=True)
            (base / file).write_bytes(name.encode())
        output = directory / "bundle"
        result = artifacts.bundle(manifest, incoming, output)
        return result, output / result["archive"]

    def test_all_component_bundles_roundtrip_with_checksums(self):
        for component in ("skiasharp", "angle"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest, archive = self.fixture(root, component)
                artifacts.extract_component(manifest, archive, root / "native")
                self.assertEqual(manifest["files"], artifacts.inventory(root / "native"))

    def test_damaged_archive_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, archive = self.fixture(root)
            archive.write_bytes(archive.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "checksum"):
                artifacts.extract_component(manifest, archive, root / "native")
            self.assertFalse((root / "native").exists())

    def test_component_identity_and_missing_platform_are_rejected(self):
        manifest = artifacts.identity("angle", "a" * 40, "chromium-7151")
        tampered = dict(manifest, commit="b" * 40)
        with self.assertRaisesRegex(ValueError, "identity"):
            artifacts.check_component(tampered)
        with self.assertRaisesRegex(ValueError, "required"):
            artifacts.check_component(dict(manifest, files={}))

    def test_zip_paths_cannot_escape_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, archive = self.fixture(root)
            with zipfile.ZipFile(archive, "a") as stream:
                stream.writestr("../outside", b"tamper")
            manifest["files"]["../outside"] = artifacts.digest(b"tamper")
            manifest["sha256"] = artifacts.digest(archive.read_bytes())
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                artifacts.extract_component(manifest, archive, root / "native")
            self.assertFalse((root / "outside").exists())

    def test_api_failure_is_not_a_cache_miss(self):
        result = type("Result", (), {"returncode": 1, "stderr": "gh: server error (HTTP 500)"})()
        with patch.object(artifacts, "gh", return_value=result):
            with self.assertRaises(RuntimeError):
                artifacts.release("native-angle-test")

    def test_release_assets_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote = root / "local.zip", root / "remote.zip"
            local.write_bytes(b"new")
            remote.write_bytes(b"old")
            with patch.object(artifacts, "release", return_value={}), patch.object(artifacts, "download", return_value=remote):
                with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                    artifacts.store("tag", [local], "title", "notes")


class CandidateTests(unittest.TestCase):
    def manifest(self):
        skia = dict(artifacts.identity("skiasharp", "a" * 40, "3.119.4"), sha256="c" * 64)
        angle = dict(artifacts.identity("angle", "b" * 40, "chromium-7151"), sha256="d" * 64)
        return artifacts.package_plan(skia, angle, "12.1.4", "8.3.1.3", "r1")

    def test_package_assembly_changes_do_not_invalidate_native_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skia = artifacts.identity("skiasharp", "a" * 40, "3.119.4", root)
            angle = artifacts.identity("angle", "b" * 40, "chromium-7151", root)
            path = root / "nuget/StaticAvalonia/README.md"
            path.parent.mkdir(parents=True)
            path.write_text("new package docs", encoding="utf-8")
            self.assertEqual(skia, artifacts.identity("skiasharp", "a" * 40, "3.119.4", root))
            self.assertEqual(angle, artifacts.identity("angle", "b" * 40, "chromium-7151", root))

    def test_package_tag_binds_exact_component_hashes(self):
        first = self.manifest()
        skia = dict(artifacts.identity("skiasharp", "a" * 40, "3.119.4"), sha256="e" * 64)
        angle = dict(artifacts.identity("angle", "b" * 40, "chromium-7151"), sha256="d" * 64)
        second = artifacts.package_plan(skia, angle, "12.1.4", "8.3.1.3", "r1")
        self.assertNotEqual(first["tag"], second["tag"])
        self.assertEqual(first["version"], second["version"])

    def test_repository_signature_does_not_change_payload_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in ("unsigned.nupkg", "signed.nupkg"):
                with zipfile.ZipFile(root / file, "w") as stream:
                    stream.writestr("package.nuspec", b"metadata")
                    if file.startswith("signed"):
                        stream.writestr(".signature.p7s", b"repository signature")
            self.assertEqual(artifacts.payload_hash(root / "unsigned.nupkg"), artifacts.payload_hash(root / "signed.nupkg"))

    def test_nuget_version_conflict_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote = root / "local.nupkg", io.BytesIO()
            for target, contents in ((local, "original"), (remote, "different")):
                with zipfile.ZipFile(target, "w") as stream:
                    stream.writestr("test.txt", contents)
            remote.seek(0)
            with patch.object(artifacts, "check_package", return_value=local), patch.object(artifacts.urllib.request, "urlopen", return_value=remote):
                with self.assertRaisesRegex(ValueError, "different package contents"):
                    artifacts.nuget_exists(self.manifest(), root)


if __name__ == "__main__":
    unittest.main()
