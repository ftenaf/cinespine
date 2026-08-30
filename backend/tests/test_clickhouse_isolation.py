"""
The test suite must not write into the database a demo reads from.

It did. With CLICKHOUSE_HOST set, running the suite put 5355 rows of fixtures
-- CHTEST, HEAVY, BATCH1, INTENT_DISAGREE, RESOLVE_TEST -- into the same tables
as the production's 475. The analytics panel was 92% test data, and nothing
about it looked wrong: the rows have the same shape as real ones, so the only
clue was reading the production ids.

The same shape of problem as the compose files sharing a project name, one
layer down: two things that should have been separate were separated by nothing
but the fact that nobody had run them together yet.
"""
import pytest

from backend.app.spine import clickhouse as ch
from backend.app.spine.schema import CLICKHOUSE_SCHEMA_DDL, schema_ddl


# --------------------------------------------------------------------------- #
# Which database is chosen
# --------------------------------------------------------------------------- #

def test_the_suite_runs_against_its_own_database():
    """
    The autouse fixture in conftest.py sets this for every test, including
    this one. If it stops working the rest of this file is decoration.
    """
    assert ch.database() == "cinespine_test"


def test_the_default_is_unchanged(monkeypatch):
    """
    A deployment that sets nothing must keep the database it already has, or
    upgrading silently moves the mirror somewhere empty -- which looks exactly
    like a mirror that was never written to.
    """
    monkeypatch.delenv("CLICKHOUSE_DATABASE", raising=False)
    assert ch.database() == "cinespine"
    assert ch.DEFAULT_DATABASE == "cinespine"


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_setting_falls_back_rather_than_breaking(monkeypatch, raw):
    monkeypatch.setenv("CLICKHOUSE_DATABASE", raw)
    assert ch.database() == "cinespine"


@pytest.mark.parametrize("bad", [
    "cinespine; DROP TABLE production_events",
    "cinespine.production_events",
    "cine spine",
    "1cinespine",
    "cinespine-test",
])
def test_a_name_that_cannot_be_a_name_is_refused(monkeypatch, bad):
    """
    This value is interpolated into SQL rather than passed as a parameter,
    because a table name cannot be a query parameter. It comes from the
    environment and not from a request, but it is checked rather than trusted.
    """
    monkeypatch.setenv("CLICKHOUSE_DATABASE", bad)
    with pytest.raises(ValueError):
        ch.database()


# --------------------------------------------------------------------------- #
# It reaches the SQL
# --------------------------------------------------------------------------- #

def test_the_schema_is_built_for_the_chosen_database():
    ddl = schema_ddl("cinespine_test")
    assert "CREATE DATABASE IF NOT EXISTS cinespine_test" in ddl
    assert "cinespine_test.production_events" in ddl
    # No table left pointing at the default.
    assert "cinespine.production_events" not in ddl


def test_the_default_schema_still_names_the_real_database():
    assert "cinespine.production_events" in CLICKHOUSE_SCHEMA_DDL


def test_every_table_moves_together():
    """
    A schema half in one database and half in another would be worse than
    either: the writes would land in two places and no query would see both.
    """
    ddl = schema_ddl("cinespine_test")
    for table in ("production_events", "takes_meta", "editorial_tag_events",
                  "requirement_events", "audit_discrepancies"):
        assert f"cinespine_test.{table}" in ddl, table


def test_the_analytics_queries_carry_the_placeholder():
    """
    They are templates, substituted at query time. A query that hardcoded the
    database would read the demo's rows from inside the test suite.
    """
    import inspect

    from backend.app.spine import analytics

    source = inspect.getsource(analytics)
    assert "FROM {db}." in source
    assert "FROM cinespine." not in source


def test_the_writer_names_no_database_directly():
    import inspect

    from backend.app.spine import writer

    source = inspect.getsource(writer)
    assert "cinespine." not in source, "a table name is still hardcoded in the writer"


# --------------------------------------------------------------------------- #
# What the mirror is handed
# --------------------------------------------------------------------------- #

class RecordingClient:
    def __init__(self):
        self.inserts = []
        self.commands = []

    def insert(self, table, rows, column_names):
        self.inserts.append(table)

    def command(self, sql, parameters=None):
        self.commands.append(sql)


def test_a_mirrored_event_goes_to_the_test_database():
    """
    End to end, and the point of all of the above: an event written during a
    test must not land in the table a demo reads.
    """
    from backend.app.spine.writer import SpineWriter

    client = RecordingClient()
    writer = SpineWriter(clickhouse_client=client)
    writer.append_event({
        "event_id": "e1", "production_id": "ISOLATION", "shoot_day": "31",
        "axis": "belief", "department": "camera", "doc_type": "camera_csv",
        "entity_type": "take", "payload": {"slate": "27/7"}, "metadata": {},
    })
    writer.flush_events()

    assert client.inserts, "nothing was mirrored"
    for table in client.inserts:
        assert table.startswith("cinespine_test."), table
