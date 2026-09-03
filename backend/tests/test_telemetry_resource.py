"""
The resource that tells one deployment's telemetry from another's.

Evidence:
- references/log.md (2026-09-03, 'A laptop container pushed into the production stack')
"""
from backend.app import __version__
from backend.app.core.telemetry import (
    deployment_environment,
    remote_export_allowed,
    resource_attributes,
)

GRAFANA = "https://otlp-gateway-prod-eu-west-2.grafana.net/otlp"
CLOUD_RUN = {"K_SERVICE": "cinespine", "K_REVISION": "cinespine-00042-abc"}


def test_cloud_run_is_recognised_by_the_variables_it_sets():
    attrs = resource_attributes("cinespine-backend", CLOUD_RUN, hostname="ignored")
    assert attrs["deployment.environment"] == "cloudrun"
    assert attrs["service.instance.id"] == "cinespine-00042-abc"


def test_cloud_run_wins_over_a_cinespine_env_that_says_otherwise():
    assert deployment_environment({**CLOUD_RUN, "CINESPINE_ENV": "local"}) == "cloudrun"


def test_anything_else_is_local_and_named_after_the_host():
    attrs = resource_attributes("cinespine-backend", {}, hostname="paco-laptop")
    assert attrs["deployment.environment"] == "local"
    assert attrs["service.instance.id"] == "paco-laptop"


def test_cinespine_env_names_a_deployment_that_is_not_cloud_run():
    assert deployment_environment({"CINESPINE_ENV": "staging"}) == "staging"
    assert deployment_environment({"CINESPINE_ENV": "  "}) == "local"


def test_the_version_is_the_package_version_not_a_literal():
    assert resource_attributes("cinespine-backend", {}, hostname="h")["service.version"] == __version__


def test_a_local_process_may_export_to_a_local_collector():
    for endpoint in (
        "http://localhost:9090/api/v1/otlp",
        "http://127.0.0.1:4318",
        "http://host.docker.internal:9090/api/v1/otlp",
        "http://prometheus:9090/api/v1/otlp",
    ):
        assert remote_export_allowed("local", endpoint, {}), endpoint


def test_a_local_process_does_not_export_to_a_remote_stack_by_accident():
    assert not remote_export_allowed("local", GRAFANA, {})


def test_a_local_process_exports_remotely_when_told_to():
    assert remote_export_allowed("local", GRAFANA, {"CINESPINE_TELEMETRY_REMOTE_OK": "1"})
    assert not remote_export_allowed("local", GRAFANA, {"CINESPINE_TELEMETRY_REMOTE_OK": "0"})


def test_a_deployment_exports_wherever_it_is_pointed():
    assert remote_export_allowed("cloudrun", GRAFANA, {})
    assert remote_export_allowed("staging", GRAFANA, {})
