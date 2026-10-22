import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RIDS = ("win-x64", "win-arm64", "linux-x64", "linux-arm64", "osx-x64", "osx-arm64")


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="staticavalonia-package-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.native = cls.directory / "native"
        cls.environment = dict(os.environ, DOTNET_NOLOGO="true", DOTNET_CLI_TELEMETRY_OPTOUT="1")
        for rid in RIDS:
            names = ("skia.lib", "SkiaSharp.lib", "libHarfBuzzSharp.lib", "libANGLE_static.lib", "libGLESv2_static.lib") if rid.startswith("win-") else ("libskia.a", "libSkiaSharp.a", "libHarfBuzzSharp.a")
            for name in names:
                path = cls.native / rid / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"package content fixture\n")
        license = cls.native / "win-x64/licenses/angle/third_party/example/LICENSE"
        license.parent.mkdir(parents=True)
        license.write_text("dependency license", encoding="utf-8")
        (cls.native / "win-x64/ANGLE-source.json").write_text(
            (ROOT / "native/angle/source.json").read_text(encoding="utf-8"), encoding="utf-8")
        cls.pack = ["dotnet", "pack", str(ROOT / "nuget/StaticAvalonia/StaticAvalonia.csproj"),
                    "-c", "Release", "-p:Version=3.119.4-avalonia.12.1.4-r1",
                    f"-p:NativeOutputDir={cls.native}",
                    f"-p:BaseIntermediateOutputPath={cls.directory / 'obj'}/",
                    f"-p:OutputPath={cls.directory / 'bin'}/", "-o", str(cls.directory / "packages")]
        cls.command(cls.pack)
        cls.package, = (cls.directory / "packages").glob("*.nupkg")
        cls.extracted = cls.directory / "extracted"
        with zipfile.ZipFile(cls.package) as archive:
            archive.extractall(cls.extracted)
            cls.entries = archive.namelist()
        cls.consumer = cls.directory / "consumer.proj"
        targets = cls.extracted / "buildTransitive/Summpot.StaticAvalonia.targets"
        cls.consumer.write_text(f'<Project><Import Project="{targets}" /></Project>', encoding="utf-8")

    @classmethod
    def command(cls, command):
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=cls.environment)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout

    def test_package_identity_and_complete_native_payload(self):
        self.assertTrue(self.package.name.startswith("Summpot.StaticAvalonia."))
        self.assertEqual(22, len([entry for entry in self.entries if entry.startswith("runtimes/")]))
        for directory in ("build", "buildTransitive"):
            self.assertIn(f"{directory}/Summpot.StaticAvalonia.targets", self.entries)
        self.assertFalse(any("SkiaSharp.Static.targets" in entry for entry in self.entries))
        self.assertIn("licenses/ANGLE.txt", self.entries)
        self.assertIn("licenses/angle/third_party/example/LICENSE", self.entries)
        self.assertIn("build/ANGLE-source.json", self.entries)

    def test_nativeaot_routes_archives_and_angle_import_by_runtime(self):
        for rid in RIDS:
            with self.subTest(rid=rid):
                result = json.loads(self.command(["dotnet", "msbuild", str(self.consumer), "-nologo",
                    "-getItem:NativeLibrary,DirectPInvoke,LinkerArg", f"-p:RuntimeIdentifier={rid}", "-p:PublishAot=true"]))["Items"]
                libraries = [item["Identity"].replace("\\", "/") for item in result["NativeLibrary"]]
                self.assertEqual(5 if rid.startswith("win-") else 3, len(libraries))
                self.assertTrue(all(f"runtimes/{rid}/native/" in name for name in libraries))
                imports = [item["Identity"] for item in result["DirectPInvoke"]]
                self.assertEqual(rid.startswith("win-"), "av_libGLESv2.dll" in imports)

    def test_non_aot_build_does_not_add_native_libraries(self):
        items = json.loads(self.command(["dotnet", "msbuild", str(self.consumer), "-nologo",
            "-getItem:NativeLibrary,DirectPInvoke", "-p:RuntimeIdentifier=win-x64", "-p:PublishAot=false"]))["Items"]
        self.assertEqual([], items["NativeLibrary"])
        self.assertEqual([], items["DirectPInvoke"])

    def test_incomplete_angle_payload_cannot_be_packed(self):
        path = self.native / "win-arm64/libGLESv2_static.lib"
        contents = path.read_bytes()
        try:
            path.unlink()
            result = subprocess.run([*self.pack, "--no-build", "--no-restore"], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", env=self.environment)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Required native library is missing", result.stdout + result.stderr)
        finally:
            path.write_bytes(contents)


if __name__ == "__main__":
    unittest.main()
