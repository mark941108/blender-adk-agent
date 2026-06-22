"""
Unit tests for security module.

Verifies Zero Ambient Authority enforcement:
- Paths inside allowlist should pass validation
- Paths outside allowlist should be rejected
- Edge cases (empty paths, partial matches) should be handled correctly
"""

import pytest
from agents.security import validate_path, require_valid_path, ALLOWED_MODEL_PATHS


class TestValidatePath:
    """Tests for the file-tree allowlist enforcement."""

    def test_allowed_model_path_passes(self):
        """Valid model path within allowlist should return True."""
        path = r"D:\blender\model\Hiyuki model\绯雪\绯雪_edit.glb"
        assert validate_path(path) is True

    def test_allowed_vmd_path_passes(self):
        """Valid path within allowlist with allowed extension should return True."""
        path = r"D:\blender\vmd\[A]ddiction\dance.gltf"
        assert validate_path(path) is True

    def test_ssh_key_rejected(self):
        """SSH private key access must be rejected (sensitive file)."""
        path = r"C:\Users\USER\.ssh\id_rsa"
        assert validate_path(path) is False

    def test_system_path_rejected(self):
        """Windows system directory access must be rejected."""
        path = r"C:\Windows\System32\cmd.exe"
        assert validate_path(path) is False

    def test_user_profile_rejected(self):
        """User profile directory access must be rejected."""
        path = r"C:\Users\USER\Documents\secret.docx"
        assert validate_path(path) is False

    def test_partial_match_rejected(self):
        """Path that merely CONTAINS an allowed prefix but isn't inside it."""
        path = r"D:\blender\model_backup\evil.py"
        result = validate_path(path)
        assert result is False

    def test_empty_path_rejected(self):
        """Empty path should not match any allowlist entry."""
        assert validate_path("") is False

    def test_require_valid_path_raises_on_invalid(self):
        """require_valid_path() should raise ValueError for disallowed paths."""
        with pytest.raises(ValueError, match="Security"):
            require_valid_path(r"C:\Users\USER\Desktop\evil.exe")

    def test_require_valid_path_passes_silently(self):
        """require_valid_path() should not raise for allowed paths."""
        # Should not raise
        require_valid_path(r"D:\blender\model\test.glb")

    def test_allowlist_contents(self):
        """Sanity check: ALLOWED_MODEL_PATHS contains expected directories."""
        assert any(r"D:\blender\model" in p for p in ALLOWED_MODEL_PATHS)
        assert len(ALLOWED_MODEL_PATHS) >= 2
