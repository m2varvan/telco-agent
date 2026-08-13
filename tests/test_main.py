"""
Unit tests for main.py env validation.
Requirements: 11.3, 11.6
"""
import pytest
import os
from main import _validate_env, _REQUIRED_NIM as _REQUIRED_VARS


class TestValidateEnv:
    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("ACTIVE_LLM", "nemotron_nim")

    def test_all_vars_set_passes(self, monkeypatch):
        """When all required vars are set, _validate_env should not raise."""
        for var in _REQUIRED_VARS:
            monkeypatch.setenv(var, "test_value")
        # Should not raise
        _validate_env()

    def test_missing_llm_model_name_raises(self, monkeypatch):
        """Missing LLM_MODEL_NAME raises EnvironmentError naming the variable."""
        # Set the other two
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.setenv("LLM_BASE_URL", "http://test")
        monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
        with pytest.raises(EnvironmentError) as exc_info:
            _validate_env()
        assert "LLM_MODEL_NAME" in str(exc_info.value)

    def test_missing_llm_api_key_raises(self, monkeypatch):
        """Missing LLM_API_KEY raises EnvironmentError naming the variable."""
        monkeypatch.setenv("LLM_MODEL_NAME", "test_model")
        monkeypatch.setenv("LLM_BASE_URL", "http://test")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(EnvironmentError) as exc_info:
            _validate_env()
        assert "LLM_API_KEY" in str(exc_info.value)

    def test_missing_llm_base_url_raises(self, monkeypatch):
        """Missing LLM_BASE_URL raises EnvironmentError naming the variable."""
        monkeypatch.setenv("LLM_MODEL_NAME", "test_model")
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        with pytest.raises(EnvironmentError) as exc_info:
            _validate_env()
        assert "LLM_BASE_URL" in str(exc_info.value)

    def test_empty_string_treated_as_missing(self, monkeypatch):
        """Empty string value for a required var also raises EnvironmentError."""
        monkeypatch.setenv("LLM_MODEL_NAME", "")
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.setenv("LLM_BASE_URL", "http://test")
        with pytest.raises(EnvironmentError) as exc_info:
            _validate_env()
        assert "LLM_MODEL_NAME" in str(exc_info.value)

    def test_error_message_contains_variable_name(self, monkeypatch):
        """Error message specifically names the missing variable."""
        for var in _REQUIRED_VARS:
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(EnvironmentError) as exc_info:
            _validate_env()
        # At least one of the required var names should appear in the message
        error_msg = str(exc_info.value)
        assert any(var in error_msg for var in _REQUIRED_VARS)

    def test_required_vars_list(self):
        """Verify the required variables list contains the expected three vars."""
        assert "LLM_MODEL_NAME" in _REQUIRED_VARS
        assert "LLM_API_KEY" in _REQUIRED_VARS
        assert "LLM_BASE_URL" in _REQUIRED_VARS
        assert len(_REQUIRED_VARS) == 3
