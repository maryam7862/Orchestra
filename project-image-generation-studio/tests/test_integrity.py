import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile

from PIL import Image

from services import integrity


def test_valid_image_passes_integrity_check():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "valid.png"
        Image.new("RGB", (64, 64), color=(10, 20, 30)).save(path)

        result = integrity.verify_and_fingerprint(path, "req-1")

        assert result.passed is True
        assert result.width == 64
        assert result.height == 64
        assert result.checksum is not None
        assert len(result.checksum) == 64  # sha256 hex digest length


def test_truncated_file_fails_integrity_check():
    with tempfile.TemporaryDirectory() as tmp:
        good_path = Path(tmp) / "good.png"
        Image.new("RGB", (128, 128)).save(good_path)

        truncated_path = Path(tmp) / "truncated.png"
        full_bytes = good_path.read_bytes()
        # Keep the header (so Image.open() succeeds) but chop off most of
        # the pixel data, so Image.load() should fail.
        truncated_path.write_bytes(full_bytes[: len(full_bytes) // 4])

        result = integrity.verify_and_fingerprint(truncated_path, "req-2")

        assert result.passed is False
        assert not truncated_path.exists()  # corrupted file must be deleted


def test_missing_file_fails_integrity_check():
    result = integrity.verify_and_fingerprint(Path("/tmp/does_not_exist_12345.png"), "req-3")
    assert result.passed is False


def test_empty_file_fails_integrity_check():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "empty.png"
        path.write_bytes(b"")
        result = integrity.verify_and_fingerprint(path, "req-4")
        assert result.passed is False
