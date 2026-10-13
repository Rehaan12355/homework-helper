import pytest

from homework_helper import names, study_sessions


@pytest.fixture(autouse=True)
def no_google_calendar(monkeypatch):
    """Planning never reads the real calendar in tests."""
    monkeypatch.setattr(study_sessions, "saved_calendar", lambda: None)


@pytest.fixture(autouse=True)
def no_bedrock(monkeypatch):
    """Tests never call Amazon Bedrock; titles keep their rule-based names
    unless a test supplies its own namer."""
    def offline(titles):
        raise RuntimeError("Bedrock is off in tests")
    monkeypatch.setattr(names, "ask_bedrock", offline)
