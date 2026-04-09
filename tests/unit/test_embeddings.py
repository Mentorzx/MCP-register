from __future__ import annotations

import os
import tempfile

from mcp_crm.slices.users.infrastructure import embeddings as embeddings_module


def test_prepare_sentence_transformers_runtime_sets_safe_defaults(
    tmp_path,
    monkeypatch,
):
    cache_dir = tmp_path / "torchinductor-cache"
    huggingface_home = tmp_path / "huggingface-home"

    monkeypatch.delenv("TORCHINDUCTOR_CACHE_DIR", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_CACHE", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.delenv("LOGNAME", raising=False)
    monkeypatch.setattr(
        embeddings_module,
        "_default_torchinductor_cache_dir",
        lambda: cache_dir,
    )
    monkeypatch.setattr(
        embeddings_module,
        "_default_huggingface_cache_dir",
        lambda: huggingface_home,
    )
    monkeypatch.setattr(
        embeddings_module,
        "_current_uid_has_passwd_entry",
        lambda: False,
    )

    embeddings_module._prepare_sentence_transformers_runtime()

    assert os.environ["TORCHINDUCTOR_CACHE_DIR"] == str(cache_dir)
    assert os.environ["HF_HOME"] == str(huggingface_home)
    assert os.environ["HF_HUB_CACHE"] == str(huggingface_home / "hub")
    assert os.environ["TRANSFORMERS_CACHE"] == str(huggingface_home / "hub")
    assert os.environ["HOME"] == tempfile.gettempdir()
    assert os.environ["USER"] == f"uid-{os.getuid()}"
    assert os.environ["LOGNAME"] == f"uid-{os.getuid()}"
    assert cache_dir.is_dir()
    assert huggingface_home.is_dir()


def test_prepare_sentence_transformers_runtime_preserves_existing_env(monkeypatch):
    monkeypatch.setenv("TORCHINDUCTOR_CACHE_DIR", "/tmp/custom-torchinductor")
    monkeypatch.setenv("HF_HOME", "/tmp/custom-hf-home")
    monkeypatch.setenv("HF_HUB_CACHE", "/tmp/custom-hf-home/custom-hub")
    monkeypatch.setenv("TRANSFORMERS_CACHE", "/tmp/custom-hf-home/custom-transformers")
    monkeypatch.setenv("HOME", "/tmp/custom-home")
    monkeypatch.setenv("USER", "existing-user")
    monkeypatch.setenv("LOGNAME", "existing-logname")
    monkeypatch.setattr(
        embeddings_module,
        "_current_uid_has_passwd_entry",
        lambda: False,
    )

    embeddings_module._prepare_sentence_transformers_runtime()

    assert os.environ["TORCHINDUCTOR_CACHE_DIR"] == "/tmp/custom-torchinductor"
    assert os.environ["HF_HOME"] == "/tmp/custom-hf-home"
    assert os.environ["HF_HUB_CACHE"] == "/tmp/custom-hf-home/custom-hub"
    assert os.environ["TRANSFORMERS_CACHE"] == "/tmp/custom-hf-home/custom-transformers"
    assert os.environ["HOME"] == "/tmp/custom-home"
    assert os.environ["USER"] == "existing-user"
    assert os.environ["LOGNAME"] == "existing-logname"
