import pytest

from homework_helper import names, plan_settings, study_sessions


class MemorySettings:
    def __init__(self):
        self.data = {}

    def load(self):
        return dict(self.data)

    def save(self, data):
        self.data = data


@pytest.fixture(autouse=True)
def saved_settings(monkeypatch):
    """Plan changes are kept in memory, never in a real file or table."""
    kept = MemorySettings()
    monkeypatch.setattr(plan_settings, "default_store", lambda: kept)
    return kept


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
