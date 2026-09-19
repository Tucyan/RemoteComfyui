import pytest
from pydantic import ValidationError

from app.settings import Settings


def test_settings_use_local_development_defaults():
    settings = Settings(_env_file=None)

    assert settings.comfyui_url == "http://127.0.0.1:8188"
    assert settings.public_host == "0.0.0.0"
    assert settings.public_port == 3000
    assert settings.admin_host == "127.0.0.1"
    assert settings.admin_port == 3001
    assert settings.data_dir == "./data"
    assert settings.max_upload_size_bytes == 100 * 1024 * 1024
    assert settings.libraries == []


@pytest.mark.parametrize(
    "comfyui_url",
    ["http://192.168.1.12:8188", "http://example.com:8188", "http://[::2]:8188"],
)
def test_settings_reject_comfyui_urls_that_are_not_loopback(comfyui_url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, comfyui_url=comfyui_url)


@pytest.mark.parametrize("admin_host", ["0.0.0.0", "192.168.1.4", "example.com"])
def test_settings_reject_non_loopback_admin_hosts(admin_host):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, admin_host=admin_host)

