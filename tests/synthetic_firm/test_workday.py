from datetime import datetime
from zoneinfo import ZoneInfo

from synthetic_firm.workday import evaluate_workday, load_workday_config


def test_workday_inside_europe_paris_hours():
    config = load_workday_config("agents/workday.yaml")
    now = datetime(2026, 6, 1, 10, 30, tzinfo=ZoneInfo("Europe/Paris"))

    status = evaluate_workday(config, now)

    assert status.inside_work_hours is True
    assert status.timezone == "Europe/Paris"
    assert config.start.hour == 9
    assert config.end.hour == 16


def test_workday_outside_weekend():
    config = load_workday_config("agents/workday.yaml")
    now = datetime(2026, 6, 6, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))

    status = evaluate_workday(config, now)

    assert status.inside_work_hours is False
    assert "not a workday" in status.reason
