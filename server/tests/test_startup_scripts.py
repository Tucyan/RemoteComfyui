from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_windows_scripts_resolve_project_root_from_their_own_location():
    for name in ("start-server.ps1", "start-admin.ps1", "install-autostart.ps1"):
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "$PSScriptRoot" in script
        assert "Resolve-Path" in script
        assert "Set-Location $ProjectRoot" in script or "WorkingDirectory $ProjectRoot" in script


def test_scripts_keep_comfyui_loopback_and_use_separate_admin_listener():
    server = (ROOT / "scripts" / "start-server.ps1").read_text(encoding="utf-8")
    admin = (ROOT / "scripts" / "start-admin.ps1").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8188" in server
    assert "REMOTE_COMFYUI_COMFYUI_URL" in server
    assert "create_public_app" in server
    assert "create_admin_app" in admin
    assert '"127.0.0.1"' in admin
    assert '"--port", "8188"' not in server
    assert "PublicPort 必须" in server
    assert "AdminHost 必须" in admin


def test_scripts_do_not_launch_comfyui_or_forward_the_admin_listener():
    for name in ("start-server.ps1", "start-admin.ps1", "install-autostart.ps1"):
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8").lower()
        assert "comfyui_windows_portable" not in script
        assert "--listen" not in script
        assert "3001" not in script or name == "start-admin.ps1"
