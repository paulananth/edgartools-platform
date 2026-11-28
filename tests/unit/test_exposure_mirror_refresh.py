"""After a load the mirror applies its pending changes now, and the refresh waits until its last apply time moves."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mirror_refresh", ROOT / "skills/data-platform/scripts/exposure/mirror_refresh.py")
mirror_refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror_refresh)

LIST = "CALL SNOWFLAKE.POSTGRES.LIST_MIRRORS();\n"
REFRESH = "CALL SNOWFLAKE.POSTGRES.REFRESH_MIRROR('m1');\n"


class Mirror:
    """A mirror whose last apply time moves after the refresh call once `applies_after` listings have gone by."""

    def __init__(self, applies_after):
        self.applies_after, self.calls, self.refreshed, self.listings = applies_after, [], False, 0

    def run(self, sql):
        self.calls.append(sql)
        if sql == REFRESH:
            self.refreshed = True
            return [{"REFRESH_MIRROR": "Refresh dispatched via EXECUTE TASK"}]
        if self.refreshed:
            self.listings += 1
        moved = self.refreshed and self.applies_after is not None and self.listings > self.applies_after
        return [{"MIRROR_NAME": "other", "LAST_APPLY_TIME": "t9"},
                {"MIRROR_NAME": "m1", "LAST_APPLY_TIME": "t2" if moved else "t1"}]


def test_the_refresh_returns_the_new_apply_time_once_the_recorded_mirror_has_applied():
    mirror, waits = Mirror(applies_after=2), []
    assert mirror_refresh.refresh("m1", mirror.run, waits.append, minutes=15, every=15) == "t2"
    assert mirror.calls[:2] == [LIST, REFRESH] and mirror.calls.count(REFRESH) == 1
    assert waits == [15, 15, 15]


def test_a_refresh_not_applied_within_its_minutes_returns_nothing_and_stops_listing():
    mirror, waits = Mirror(applies_after=None), []
    assert mirror_refresh.refresh("m1", mirror.run, waits.append, minutes=1, every=15) is None
    assert sum(waits) <= 60 and mirror.calls.count(REFRESH) == 1


def test_a_refused_statement_ends_the_refresh_with_its_error_number_and_no_login(monkeypatch, capsys):
    def refused(sql):
        raise mirror_refresh.readiness.SnowflakeRefused("002003")
    monkeypatch.setattr(mirror_refresh.readiness, "run_as_mirror_operator", refused)
    assert mirror_refresh.main([]) == 1
    assert capsys.readouterr().err.strip() == "mirror: not refreshed: Snowflake error 002003"
