from __future__ import annotations

from pathlib import Path


def test_llama_cli_install_script_pins_macos_arm64_asset() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "install_llama_cli.sh"
    content = script.read_text(encoding="utf-8")

    assert "b8994" in content
    assert "llama-$TAG-bin-macos-arm64.tar.gz" in content
    assert "ggml-org/llama.cpp" in content


def test_qwen_smoke_test_defaults_to_local_llama_cli() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "qwen35_smoke_test.sh"
    content = script.read_text(encoding="utf-8")

    assert ".tools/llama.cpp/bin/llama-cli" in content
    assert "scripts/install_llama_cli.sh" in content
