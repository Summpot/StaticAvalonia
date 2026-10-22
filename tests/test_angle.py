import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("angle", Path(__file__).parents[1] / "scripts/angle.py")
angle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(angle)


def archive(*members):
    result = bytearray(b"!<arch>\n")
    for index, member in enumerate(members):
        name = f"test{index}.obj/".ljust(16)
        header = f"{name}{'0':<12}{'0':<6}{'0':<6}{'0':<8}{len(member):<10}`\n".encode("ascii")
        result.extend(header + member + (b"\n" if len(member) % 2 else b""))
    return result


class ArchiveTests(unittest.TestCase):
    def test_standard_and_bigobj_architectures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.lib"
            for machine in (0x8664, 0xAA64):
                for member in (machine.to_bytes(2, "little") + b"\0" * 18,
                               b"\0\0\xff\xff\x02\0" + machine.to_bytes(2, "little") + b"\0" * 48):
                    path.write_bytes(archive(member))
                    self.assertEqual(machine, angle.coff_machine(path))

    def test_mixed_architecture_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.lib"
            path.write_bytes(archive(b"\x64\x86" + b"\0" * 18, b"\x64\xaa" + b"\0" * 18))
            with self.assertRaises(ValueError):
                angle.coff_machine(path)

    def test_non_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.lib"
            path.write_bytes(b"not an archive")
            with self.assertRaises(ValueError):
                angle.coff_machine(path)


if __name__ == "__main__":
    unittest.main()
