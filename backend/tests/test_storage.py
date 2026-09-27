import unittest
from pathlib import Path

from app.core.config import BASE_DIR
from app.core.storage import to_storage_ref, resolve_storage_ref
# These unit tests check that MediExplain+ stores file references relative to the
# project storage area and resolves them back to the correct local path. They also
# verify the storage helpers reject directory traversal attempts and absolute paths
# outside the managed project storage, helping prevent unsafe or non-portable file
# references from being accepted.

class StorageTests(unittest.TestCase):
    def test_roundtrip(self):
        original = BASE_DIR / "audio_cache" / "example.wav"
        ref = to_storage_ref(original)
        self.assertEqual(ref, "audio_cache/example.wav")
        self.assertEqual(resolve_storage_ref(ref), original.resolve())

    def test_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_storage_ref("../../outside.txt")

    def test_outside_absolute_path_is_rejected_for_new_storage(self):
        with self.assertRaises(ValueError):
            to_storage_ref(Path("/tmp/outside-mediexplain.txt"))


if __name__ == "__main__":
    unittest.main()
