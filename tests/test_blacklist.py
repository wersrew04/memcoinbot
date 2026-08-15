"""Unit tests for BlacklistManager."""
from blacklist.manager import BlacklistManager


def test_add_and_check(tmp_path, monkeypatch):
    import blacklist.manager as mod
    monkeypatch.setattr(mod, "DB_PATH", tmp_path / "bl.json")
    bl = BlacklistManager()
    assert not bl.is_blacklisted("Tok123")
    bl.add("Tok123", "honeypot", "test")
    assert bl.is_blacklisted("Tok123")
    assert bl.remove("Tok123")
    assert not bl.is_blacklisted("Tok123")
