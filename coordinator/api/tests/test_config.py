from app.config import Settings


def test_defaults():
    s = Settings()
    assert s.session_ttl_hours == 24
    assert s.session_cookie_secure is False
    assert s.session_cookie_name == "lg_session"
    assert s.oidc_issuer_url is None
    assert s.oidc_client_id is None
    assert s.oidc_client_secret is None
    assert s.oidc_auto_provision is False


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LG_SESSION_TTL_HOURS", "12")
    monkeypatch.setenv("LG_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("LG_OIDC_ISSUER_URL", "https://idp.example/")
    monkeypatch.setenv("LG_OIDC_CLIENT_ID", "abc")
    monkeypatch.setenv("LG_OIDC_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("LG_OIDC_AUTO_PROVISION", "true")
    s = Settings()
    assert s.session_ttl_hours == 12
    assert s.session_cookie_secure is True
    assert s.oidc_issuer_url == "https://idp.example/"
    assert s.oidc_client_id == "abc"
    assert s.oidc_client_secret == "xyz"
    assert s.oidc_auto_provision is True


def test_recording_defaults():
    s = Settings()
    assert s.recordings_dir == "/data/recordings"
    assert s.recording_retention_days == 30
    assert s.recording_max_bytes_per_place == 1024 * 1024 * 1024
