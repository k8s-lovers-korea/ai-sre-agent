"""
Configuration management using Pydantic Settings with dotenv support.

This module provides centralized configuration for the SRE Agent,
loading settings from environment variables and .env files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    # Azure OpenAI settings
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-02-15-preview"

    # OpenAI settings (alternative)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4"

    # General settings
    temperature: float = 0.3
    max_tokens: int = 1000
    timeout_seconds: int = 60

    @field_validator("azure_openai_endpoint")
    @classmethod
    def validate_azure_endpoint(cls, v):
        if v and not v.startswith("https://"):
            raise ValueError("Azure OpenAI endpoint must start with https://")
        return v


class KubernetesSettings(BaseSettings):
    """Kubernetes configuration."""

    kubeconfig: str | None = None
    namespace: str = "default"
    in_cluster: bool = False
    timeout_seconds: int = 30

    class Config:
        env_prefix = "K8S_"

class APISettings(BaseSettings):
    """API server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    log_level: str = "INFO"

    class Config:
        env_prefix = "API_"


class SafetySettings(BaseSettings):
    """Safety and security configuration."""

    enable_dry_run: bool = True
    require_human_approval: bool = True
    max_concurrent_actions: int = 3
    action_timeout_seconds: int = 300

    # Rate limiting
    rate_limit_window_minutes: int = 5
    rate_limit_max_actions: int = 10

    # Allow-list file path
    allowlist_file: str = "configs/allowlist.yaml"


class MonitoringSettings(BaseSettings):
    """Monitoring integration settings."""

    prometheus_url: str = "http://prometheus:9090"
    prometheus_timeout: int = 30

    grafana_url: str | None = None
    grafana_api_key: str | None = None


class AzureSettings(BaseSettings):
    """Azure integration settings."""

    key_vault_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    tenant_id: str | None = None

    class Config:
        env_prefix = "AZURE_"


class DevelopmentSettings(BaseSettings):
    """Development and debugging settings."""

    debug: bool = False
    enable_debug_logs: bool = False
    test_mode: bool = False
    mock_k8s_api: bool = False


class Settings(BaseSettings):
    """Main application settings."""

    # Sub-configurations
    llm: LLMSettings = Field(default_factory=LLMSettings)
    kubernetes: KubernetesSettings = Field(default_factory=KubernetesSettings)
    api: APISettings = Field(default_factory=APISettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    development: DevelopmentSettings = Field(default_factory=DevelopmentSettings)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings (useful for testing)."""
    global _settings
    _settings = Settings()
    return _settings
