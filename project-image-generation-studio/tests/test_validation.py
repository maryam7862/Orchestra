import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile

import pytest

import config
from services.huggingface_provider import HuggingFaceProvider
from services.retry import NonRetryableError
from utils.file_utils import sanitize_filename, resolve_within, unique_filename


def test_load_env_files_supports_dotenv_and_dotenv_local(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("HF_TOKEN=from_dotenv\nHF_MODEL=model-from-dotenv\n", encoding="utf-8")
    env_local_file = tmp_path / ".env.local"
    env_local_file.write_text("HF_TOKEN=from_dotenv_local\nHF_MODEL=model-from-dotenv-local\n", encoding="utf-8")

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_MODEL", raising=False)

    config.load_env_files(tmp_path)

    assert os.environ["HF_TOKEN"] == "from_dotenv_local"
    assert os.environ["HF_MODEL"] == "model-from-dotenv-local"


def test_default_hf_model_uses_working_free_tier_flux_route(monkeypatch):
    monkeypatch.delenv("HF_MODEL", raising=False)
    monkeypatch.setenv("HF_TOKEN", "fake-token")

    import importlib
    importlib.reload(config)

    assert config.HF_MODEL == "black-forest-labs/FLUX.1-schnell"


def test_hf_402_maps_to_credit_exhausted_error():
    class Response:
        status_code = 402

    class FakeHFError(Exception):
        response = Response()

    with pytest.raises(NonRetryableError, match="free-tier inference credits are exhausted"):
        HuggingFaceProvider._classify_hf_exception(FakeHFError("depleted your monthly included credits"), "req-42")


def test_sanitize_filename_strips_path_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_sanitize_filename_strips_unsafe_chars():
    assert sanitize_filename("my file!@#.png") == "my_file___.png"


def test_resolve_within_blocks_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        with pytest.raises(ValueError):
            # even though sanitize_filename would neuter this, we verify
            # resolve_within itself is defense-in-depth
            resolve_within(base, "../../../etc/passwd")


def test_resolve_within_allows_normal_filename():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        result = resolve_within(base, "image123.png")
        assert result.parent == base.resolve()


def test_unique_filename_has_extension():
    name = unique_filename("GEN-20260815-AB12CD", "png")
    assert name.endswith(".png")
    assert "GEN-20260815-AB12CD" in name
