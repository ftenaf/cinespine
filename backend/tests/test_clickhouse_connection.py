"""
Reaching a ClickHouse that is not on this machine.

The connector assumed a local container: plain HTTP on 8123 and nothing else.
A managed instance answers only on TLS, and a secure connection aimed at the
plain port does not fail with "wrong protocol" -- it fails as unreachable,
which reads like the server being down and sends people to look at the wrong
end. So the port follows the protocol, and the failure says which it tried.
"""
import os

import pytest

from backend.app.spine import clickhouse as ch


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("CLICKHOUSE_HOST", "CLICKHOUSE_PORT", "CLICKHOUSE_SECURE",
                 "CLICKHOUSE_VERIFY", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    yield


# --------------------------------------------------------------------------- #
# The port follows the protocol
# --------------------------------------------------------------------------- #

def test_plain_http_keeps_the_port_it_always_had():
    assert ch.use_tls() is False
    assert ch.port() == 8123


def test_asking_for_tls_moves_the_port_with_it(monkeypatch):
    """
    CLICKHOUSE_SECURE=1 on its own has to be a complete answer. Leaving the
    port at 8123 would make the one-line change silently wrong.
    """
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")
    assert ch.use_tls() is True
    assert ch.port() == 8443


@pytest.mark.parametrize("secure", ["0", "1"])
def test_an_explicit_port_always_wins(monkeypatch, secure):
    monkeypatch.setenv("CLICKHOUSE_SECURE", secure)
    monkeypatch.setenv("CLICKHOUSE_PORT", "9440")
    assert ch.port() == 9440


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " on "])
def test_the_flag_accepts_what_people_actually_write(monkeypatch, raw):
    monkeypatch.setenv("CLICKHOUSE_SECURE", raw)
    assert ch.use_tls() is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "   ", "banana"])
def test_anything_else_leaves_it_off(monkeypatch, raw):
    """
    Unrecognised is the default, not an error. A connection setting is not
    worth refusing to start over, and the connection is already optional.
    """
    monkeypatch.setenv("CLICKHOUSE_SECURE", raw)
    assert ch.use_tls() is False


def test_the_protocol_is_never_guessed_from_the_hostname(monkeypatch):
    """
    A managed hostname does not switch TLS on by itself. Inferring it means
    keeping a list of what managed endpoints look like, and that list is wrong
    the day a provider adds a domain -- the keyed list that rots.
    """
    monkeypatch.setenv("CLICKHOUSE_HOST", "abc123.europe-west4.gcp.clickhouse.cloud")
    assert ch.use_tls() is False
    assert ch.port() == 8123


# --------------------------------------------------------------------------- #
# What the driver is actually handed
# --------------------------------------------------------------------------- #

class FakeClient:
    def __init__(self):
        self.commands = []

    def command(self, sql):
        self.commands.append(sql)


@pytest.fixture
def captured(monkeypatch):
    """Records the keyword arguments the driver was constructed with."""
    import sys

    seen = {}

    class FakeModule:
        @staticmethod
        def get_client(**kwargs):
            seen.update(kwargs)
            return FakeClient()

    monkeypatch.setitem(sys.modules, "clickhouse_connect", FakeModule)
    return seen


def test_a_secure_connection_asks_the_driver_for_tls(monkeypatch, captured):
    monkeypatch.setenv("CLICKHOUSE_HOST", "abc.clickhouse.cloud")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "hunter2")

    assert ch.connect() is not None
    assert captured["secure"] is True
    assert captured["port"] == 8443
    assert captured["verify"] is True


def test_a_local_connection_is_unchanged(monkeypatch, captured):
    """
    The default has to stay exactly what it was, or every existing deployment
    moves port when it upgrades.
    """
    monkeypatch.setenv("CLICKHOUSE_HOST", "localhost")

    assert ch.connect() is not None
    assert captured["secure"] is False
    assert captured["port"] == 8123


def test_certificate_checking_can_be_turned_off_for_a_private_ca(monkeypatch, captured):
    monkeypatch.setenv("CLICKHOUSE_HOST", "clickhouse.internal")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")
    monkeypatch.setenv("CLICKHOUSE_VERIFY", "0")

    assert ch.connect() is not None
    assert captured["verify"] is False


def test_certificates_are_checked_unless_asked_otherwise(monkeypatch, captured):
    """
    Off by request only. Defaulting to unverified would make a TLS setting that
    proves nothing about who answered.
    """
    monkeypatch.setenv("CLICKHOUSE_HOST", "abc.clickhouse.cloud")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")

    ch.connect()
    assert captured["verify"] is True


def test_the_schema_is_applied_over_a_secure_connection(monkeypatch):
    """
    Connecting is not the point; the tables are. A managed instance starts
    empty and there is no migration step.
    """
    import sys

    made = {}

    class FakeModule:
        @staticmethod
        def get_client(**kwargs):
            client = FakeClient()
            made["client"] = client
            return client

    monkeypatch.setitem(sys.modules, "clickhouse_connect", FakeModule)
    monkeypatch.setenv("CLICKHOUSE_HOST", "abc.clickhouse.cloud")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")

    ch.connect()
    ddl = " ".join(made["client"].commands)
    assert "cinespine.production_events" in ddl
    assert "cinespine.editorial_tag_events" in ddl


# --------------------------------------------------------------------------- #
# Failing legibly
# --------------------------------------------------------------------------- #

def test_an_unreachable_host_is_still_not_fatal(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_HOST", "nowhere.invalid")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")
    monkeypatch.setenv("CLICKHOUSE_CONNECT_TIMEOUT", "1")

    assert ch.connect() is None


def test_the_failure_names_the_protocol_it_tried(monkeypatch, caplog):
    """
    The diagnostic this exists for. Pointing plain HTTP at a TLS port fails as
    "unreachable", and without the protocol in the message the obvious next
    step is to check whether the server is running -- when the answer is here.
    """
    import sys

    class Broken:
        @staticmethod
        def get_client(**kwargs):
            raise ConnectionError("Remote end closed connection without response")

    monkeypatch.setitem(sys.modules, "clickhouse_connect", Broken)
    monkeypatch.setenv("CLICKHOUSE_HOST", "abc.clickhouse.cloud")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "0")

    with caplog.at_level("WARNING"):
        assert ch.connect() is None

    assert "plain HTTP" in caplog.text
    assert "8123" in caplog.text


# --------------------------------------------------------------------------- #
# Against a real TLS server, when there is one
# --------------------------------------------------------------------------- #

TLS_HOST = os.environ.get("CINESPINE_TLS_CLICKHOUSE", "").strip()


@pytest.mark.skipif(not TLS_HOST, reason="No CINESPINE_TLS_CLICKHOUSE; the handshake is not exercised")
def test_it_really_connects_over_tls(monkeypatch):
    """
    Set CINESPINE_TLS_CLICKHOUSE to host:port of a TLS ClickHouse to run this.
    Verified on 2026-08-30 against a local instance with a self-signed
    certificate: the handshake succeeded and all five tables were created.
    """
    host, _, tls_port = TLS_HOST.partition(":")
    monkeypatch.setenv("CLICKHOUSE_HOST", host)
    monkeypatch.setenv("CLICKHOUSE_PORT", tls_port or "8443")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "1")
    monkeypatch.setenv("CLICKHOUSE_VERIFY", os.environ.get("CINESPINE_TLS_VERIFY", "0"))
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", os.environ.get("CINESPINE_TLS_PASSWORD", ""))

    client = ch.connect()
    assert client is not None, "the TLS connection failed"
    tables = {r[0] for r in client.query(
        "SELECT name FROM system.tables WHERE database='cinespine'").result_rows}
    assert "production_events" in tables
