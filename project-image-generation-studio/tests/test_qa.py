import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile

from PIL import Image

from services import aesthetic_qa, semantic_qa, qa


def test_aesthetic_score_is_deterministic_not_random():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "img.png"
        Image.new("RGB", (256, 256), color=(120, 80, 200)).save(path)

        score_1 = aesthetic_qa.evaluate(path, "req-1")
        score_2 = aesthetic_qa.evaluate(path, "req-1")

        # Same image, same method -> identical score. A random scorer
        # would fail this test.
        assert score_1.score == score_2.score


def test_aesthetic_score_in_valid_range():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "img.png"
        Image.new("RGB", (256, 256), color=(50, 200, 150)).save(path)
        result = aesthetic_qa.evaluate(path, "req-2")
        assert 0.0 <= result.score <= 10.0


def test_semantic_qa_defaults_to_not_evaluated_without_clip():
    import config
    if config.ENABLE_CLIP_QA:
        return  # skip; this test targets the default heuristic-only mode
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "img.png"
        Image.new("RGB", (64, 64)).save(path)
        result = semantic_qa.evaluate(path, "a test prompt", "req-3")
        assert result.evaluated is False
        assert result.passed is True  # pass-through, never a fabricated rejection


def test_qa_orchestrator_rejects_on_low_aesthetic(monkeypatch):
    from services import aesthetic_qa as aq_module

    class FakeAesthetic:
        score = 2.0
        threshold = 7.0
        passed = False
        method = "test"

    monkeypatch.setattr(aq_module, "evaluate", lambda path, rid: FakeAesthetic())

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "img.png"
        Image.new("RGB", (64, 64)).save(path)
        result = qa.run_qa(path, "a prompt", "req-4")
        assert result.passed is False
        assert "Aesthetic" in result.reason
