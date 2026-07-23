from pathlib import Path

from app.rec import service


def test_invalid_or_incompatible_artifact_falls_back_to_deterministic(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "benchmark.json"
    artifact.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(service, "ARTIFACT_PATH", artifact)
    service.load_artifact.cache_clear()
    assert service.load_artifact() == {"selected": "deterministic"}

    artifact.write_text('{"feature_version": 999}', encoding="utf-8")
    service.load_artifact.cache_clear()
    assert service.load_artifact() == {"selected": "deterministic"}
    service.load_artifact.cache_clear()
