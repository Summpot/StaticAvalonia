import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location("upstream", Path(__file__).parents[1] / "scripts/upstream.py")
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)


class ResolveTests(unittest.TestCase):
    def test_annotated_tag_uses_peeled_commit(self):
        with patch.object(upstream.subprocess, "check_output", return_value=(
            "a" * 40 + "\trefs/tags/v1.2.3\n" + "b" * 40 + "\trefs/tags/v1.2.3^{}\n"
        )):
            self.assertEqual("b" * 40, upstream.resolve_ref("v1.2.3"))

    def test_full_commit_needs_no_ref_listing(self):
        with patch.object(upstream.subprocess, "check_output") as remote:
            self.assertEqual("a" * 40, upstream.resolve_ref("A" * 40))
            remote.assert_not_called()

    def test_missing_ref_fails_without_main_fallback(self):
        with patch.object(upstream.subprocess, "check_output", return_value=""):
            with self.assertRaises(ValueError):
                upstream.resolve_ref("v9.9.9")

    def test_xml_property_version(self):
        self.assertEqual({"SkiaSharp": "3.119.4"}, upstream.package_versions('''
            <Project><PropertyGroup><SkiaVersion>3.119.4</SkiaVersion></PropertyGroup>
            <ItemGroup><PackageVersion Include="SkiaSharp" Version="$(SkiaVersion)" /></ItemGroup></Project>
        '''))

    def test_detects_legacy_props(self):
        missing = urllib.error.HTTPError("url", 404, "Not found", {}, None)
        self.addCleanup(missing.close)
        with patch.object(upstream, "read_url", side_effect=[missing,
            '<Project><PackageReference Include="SkiaSharp" Version="3.119.4" /></Project>',
            '<Project><PackageReference Include="HarfBuzzSharp" Version="8.3.1.3" /></Project>'
        ]), patch.object(upstream, "resolve_ref", return_value="a" * 40):
            result = upstream.detect_avalonia("11.0.0")
            self.assertEqual("8.3.1.3", result["harfbuzz_version"])
            self.assertEqual("a" * 40, result["skiasharp_ref"])

    def test_missing_package_version_fails(self):
        with patch.object(upstream, "read_url", return_value="<Project />"):
            with self.assertRaises(ValueError):
                upstream.detect_avalonia("12.0.0")

    def test_network_failure_is_not_treated_as_missing_props(self):
        error = urllib.error.HTTPError("url", 503, "Unavailable", {}, None)
        self.addCleanup(error.close)
        with patch.object(upstream, "read_url", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                upstream.detect_avalonia("12.0.0")


class PatchTests(unittest.TestCase):
    def test_empty_patch_set_leaves_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test.txt").write_text("unchanged", encoding="utf-8")
            upstream.apply_patches(root, root / "patches")
            self.assertEqual("unchanged", (root / "test.txt").read_text())

    def test_patch_applies_to_parent_and_nested_skia(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, patches = root / "source", root / "patches"
            for name, target in (("skiasharp", source), ("skia", source / "externals/skia")):
                target.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "init", "-q", str(target)], check=True)
                (target / "test.txt").write_text("old\n", encoding="utf-8")
                (patches / name).mkdir(parents=True)
                (patches / name / "0001-test.patch").write_text(
                    "diff --git a/test.txt b/test.txt\n--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-old\n+new\n",
                    encoding="utf-8")
            upstream.apply_patches(source, patches)
            self.assertEqual("new\n", (source / "test.txt").read_text())
            self.assertEqual("new\n", (source / "externals/skia/test.txt").read_text())

    def test_invalid_patch_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root / "source")], check=True)
            patches = root / "patches/skiasharp"
            patches.mkdir(parents=True)
            (patches / "0001-broken.patch").write_text("invalid", encoding="utf-8")
            with self.assertRaises(subprocess.CalledProcessError):
                upstream.apply_patches(root / "source", root / "patches")


if __name__ == "__main__":
    unittest.main()
