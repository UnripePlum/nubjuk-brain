from __future__ import annotations

from pathlib import Path


def test_qwen_install_script_pins_expected_gguf() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "install_qwen35_0_8b.sh"
    content = script.read_text(encoding="utf-8")

    assert "lmstudio-community/Qwen3.5-0.8B-GGUF" in content
    assert "Qwen3.5-0.8B-Q4_K_M.gguf" in content
    assert "527502816" in content
    assert "f5b14da98939b60bbe1019a964eba656407e1e0b64f1fe3003ff6d650e93bfec" in content
