from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_gmail_onboarding_keeps_credentials_in_research_worker_only():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    credentials = {"GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"}
    for name, service in compose["services"].items():
        exposed = credentials.intersection(service.get("environment", {}))
        assert exposed == (credentials if name == "job-worker" else set())


def test_mail_setup_entrypoints_share_configuration_lock():
    for script in ("gmail-oauth.ps1", "promotion.ps1"):
        source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert ". (Join-Path $PSScriptRoot 'environment-lock.ps1')" in source
        assert "Invoke-HermesEnvironmentLock -Path" in source
        assert "[IO.File]::Replace(" in source
    lock = (ROOT / "scripts/environment-lock.ps1").read_text(encoding="utf-8")
    assert "GetFullPath($Path)" in lock
    assert "SHA256" in lock
    assert "WaitOne(15000)" in lock
    assert "ReleaseMutex()" in lock


def test_gmail_helper_is_readonly_and_has_no_runtime_task_or_send_authority():
    source = (ROOT / "scripts/gmail-oauth.ps1").read_text(encoding="utf-8")
    assert "https://www.googleapis.com/auth/gmail.readonly" in source
    assert "https://mail.google.com/" not in source
    assert "gmail.send" not in source
    assert "gmail.modify" not in source
    assert "TcpListener]::new([Net.IPAddress]::Loopback, 0)" in source
    assert "code_challenge_method = 'S256'" in source
    assert "Assert-GmailExistingIdentity $baseline $Mailbox" in source
    assert "Assert-GmailReadOnlyToken $token" in source
    assert "/v1/marketing/" not in source
    assert "SMTP_PASSWORD" not in source
    assert "Start-Transcript" not in source
