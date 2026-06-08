import base64
from datetime import datetime, timedelta, timezone

import pytest
from aioresponses import aioresponses
from yarl import URL

from database.repository import Repository
from services.autoscaler import (
    AutoscalerError,
    ProvisionNodeRequest,
    StaticNodeRegistration,
    VultrClient,
    VultrError,
    VultrInstance,
    assign_subscription_to_node,
    autoscale_premium_pool,
    build_remnawave_node_cloud_init,
    decommission_vultr_node,
    ensure_capacity_node,
    provision_vultr_node,
    register_static_node,
    release_subscription_nodes,
)
from services.panel_client import PanelHost, PanelNode


def _vultr_instance_payload(**overrides):
    payload = {
        "id": "vultr-instance-1",
        "label": "premium-ams-1",
        "region": "ams",
        "plan": "vc2-1c-1gb",
        "status": "active",
        "main_ip": "203.0.113.10",
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
async def test_vultr_create_instance_sends_encoded_user_data():
    client = VultrClient(base_url="https://api.vultr.test/v2", api_token="vultr-token")

    with aioresponses() as mocked:
        mocked.post(
            "https://api.vultr.test/v2/instances",
            status=202,
            payload={"instance": _vultr_instance_payload()},
        )

        instance = await client.create_instance(
            region="ams",
            plan="vc2-1c-1gb",
            os_id=1743,
            label="premium-ams-1",
            user_data="#cloud-config\n",
            ssh_key_ids=["ssh-key-1"],
            tags=["PREMIUM"],
            enable_ipv6=True,
        )

    request = mocked.requests[("POST", URL("https://api.vultr.test/v2/instances"))][0]
    payload = request.kwargs["json"]
    assert request.kwargs["headers"]["Authorization"] == "Bearer vultr-token"
    assert payload["region"] == "ams"
    assert payload["plan"] == "vc2-1c-1gb"
    assert payload["os_id"] == 1743
    assert payload["sshkey_id"] == ["ssh-key-1"]
    assert base64.b64decode(payload["user_data"]).decode("utf-8") == "#cloud-config\n"
    assert instance.id == "vultr-instance-1"
    assert instance.main_ip == "203.0.113.10"


@pytest.mark.unit
async def test_vultr_delete_instance_calls_endpoint():
    client = VultrClient(base_url="https://api.vultr.test/v2", api_token="vultr-token")

    with aioresponses() as mocked:
        mocked.delete("https://api.vultr.test/v2/instances/vultr-instance-1", status=204)

        assert await client.delete_instance("vultr-instance-1") is True


@pytest.mark.unit
async def test_vultr_request_requires_token():
    client = VultrClient(base_url="https://api.vultr.test/v2", api_token="")

    with pytest.raises(VultrError):
        await client.get_instance("vultr-instance-1")


@pytest.mark.unit
def test_build_remnawave_node_cloud_init_contains_compose():
    cloud_init = build_remnawave_node_cloud_init("secret-value", node_port=2222)

    assert cloud_init.startswith("#cloud-config")
    assert "image: remnawave/node:latest" in cloud_init
    assert "NODE_PORT: 2222" in cloud_init
    assert 'SECRET_KEY: "secret-value"' in cloud_init
    assert "docker compose up -d" in cloud_init


class FakeVultrClient:
    def __init__(self, instance: VultrInstance | None = None):
        self.instance = instance or VultrInstance(
            id="vultr-instance-1",
            label="premium-ams-1",
            region="ams",
            plan="vc2-1c-1gb",
            status="active",
            main_ip="203.0.113.10",
        )
        self.created_payload = None
        self.deleted_instance_ids = []
        self.waited_instance_ids = []

    async def create_instance(self, **kwargs):
        self.created_payload = kwargs
        return self.instance

    async def wait_for_main_ip(self, instance_id: str, **kwargs):
        self.waited_instance_ids.append(instance_id)
        return VultrInstance(
            id=instance_id,
            label=self.instance.label,
            region=self.instance.region,
            plan=self.instance.plan,
            status="active",
            main_ip="203.0.113.10",
        )

    async def delete_instance(self, instance_id: str):
        self.deleted_instance_ids.append(instance_id)
        return True


class FakePanelClient:
    def __init__(self, create_error: Exception | None = None):
        self.create_error = create_error
        self.create_payload = None
        self.create_host_payloads = []
        self.deleted_node_uuids = []
        self.deleted_host_uuids = []
        self.hosts = []

    async def generate_node_secret(self):
        return "node-secret"

    async def create_node(self, **kwargs):
        self.create_payload = kwargs
        if self.create_error is not None:
            raise self.create_error
        return PanelNode(
            uuid="panel-node-1",
            name=kwargs["name"],
            address=kwargs["address"],
            port=kwargs["port"],
            is_connected=False,
            is_disabled=False,
            is_connecting=True,
            country_code=kwargs["country_code"],
            traffic_used_bytes=0,
            users_online=0,
        )

    async def delete_node(self, uuid: str):
        self.deleted_node_uuids.append(uuid)
        return True

    async def create_host(self, **kwargs):
        self.create_host_payloads.append(kwargs)
        host = PanelHost(
            uuid=f"panel-host-{len(self.create_host_payloads)}",
            remark=kwargs["remark"],
            address=kwargs["address"],
            port=kwargs["port"],
            config_profile_uuid=kwargs["config_profile_uuid"],
            inbound_uuid=kwargs["inbound_uuid"],
            node_uuids=kwargs["node_uuids"],
            tag=kwargs.get("tag"),
            is_disabled=False,
        )
        self.hosts.append(host)
        return host

    async def list_hosts(self):
        return list(self.hosts)

    async def delete_host(self, uuid: str):
        self.deleted_host_uuids.append(uuid)
        self.hosts = [host for host in self.hosts if host.uuid != uuid]
        return True


def _provision_request() -> ProvisionNodeRequest:
    return ProvisionNodeRequest(
        tier="premium",
        region="ams",
        capacity=25,
        plan="vc2-1c-1gb",
        os_id=1743,
        name="premium-ams-1",
        country_code="NL",
        config_profile_uuid="profile-uuid",
        active_inbound_uuids=["inbound-uuid"],
        node_port=2222,
        host_port=1234,
        ssh_key_ids=["ssh-key-1"],
    )


@pytest.mark.integration
async def test_provision_vultr_node_creates_instance_panel_node_and_db_record(db_session):
    vultr = FakeVultrClient(
        VultrInstance(
            id="vultr-instance-1",
            label="premium-ams-1",
            region="ams",
            plan="vc2-1c-1gb",
            status="pending",
            main_ip="",
        )
    )
    panel = FakePanelClient()

    node = await provision_vultr_node(
        db_session,
        _provision_request(),
        vultr_client=vultr,
        panel_client=panel,
    )

    assert vultr.waited_instance_ids == ["vultr-instance-1"]
    assert "SECRET_KEY" in vultr.created_payload["user_data"]
    assert vultr.created_payload["ssh_key_ids"] == ["ssh-key-1"]
    assert panel.create_payload["address"] == "203.0.113.10"
    assert panel.create_payload["config_profile_uuid"] == "profile-uuid"
    assert panel.create_payload["active_inbound_uuids"] == ["inbound-uuid"]
    assert panel.create_host_payloads == [
        {
            "remark": "premium-ams-1",
            "address": "203.0.113.10",
            "port": 1234,
            "config_profile_uuid": "profile-uuid",
            "inbound_uuid": "inbound-uuid",
            "node_uuids": ["panel-node-1"],
            "tag": "AUTO",
        }
    ]
    assert node.name == "premium-ams-1"
    assert node.tier == "premium"
    assert node.capacity == 25
    assert node.provider == "vultr"
    assert node.provider_instance_id == "vultr-instance-1"
    assert node.panel_node_id == "panel-node-1"
    assert node.ip_address == "203.0.113.10"


@pytest.mark.integration
async def test_provision_vultr_node_deletes_instance_when_panel_registration_fails(db_session):
    vultr = FakeVultrClient()
    panel = FakePanelClient(create_error=RuntimeError("panel down"))

    with pytest.raises(RuntimeError):
        await provision_vultr_node(
            db_session,
            _provision_request(),
            vultr_client=vultr,
            panel_client=panel,
        )

    assert vultr.deleted_instance_ids == ["vultr-instance-1"]
    assert await Repository(db_session).list_nodes() == []


@pytest.mark.integration
async def test_decommission_vultr_node_deletes_panel_node_instance_and_db_record(db_session):
    repo = Repository(db_session)
    node = await repo.create_node(
        tier="premium",
        capacity=25,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-instance-1",
        ip_address="203.0.113.10",
        panel_node_id="panel-node-1",
        name="premium-ams-1",
    )
    vultr = FakeVultrClient()
    panel = FakePanelClient()
    panel.hosts = [
        PanelHost(
            uuid="panel-host-1",
            remark="premium-ams-1",
            address="203.0.113.10",
            port=1234,
            config_profile_uuid="profile-uuid",
            inbound_uuid="inbound-uuid",
            node_uuids=["panel-node-1"],
            tag="AUTO",
        )
    ]

    deleted = await decommission_vultr_node(
        db_session,
        node.id,
        vultr_client=vultr,
        panel_client=panel,
    )

    assert deleted is True
    assert panel.deleted_host_uuids == ["panel-host-1"]
    assert panel.deleted_node_uuids == ["panel-node-1"]
    assert vultr.deleted_instance_ids == ["vultr-instance-1"]
    assert await repo.get_node(node.id) is None


@pytest.mark.integration
async def test_register_static_node_upserts_manual_single_server_node(db_session):
    node = await register_static_node(
        db_session,
        StaticNodeRegistration(
            name="phase0-node-1",
            ip_address="62.60.156.158",
            panel_node_id="af74d563-a107-4cf0-b4f0-08cad62761d1",
            region="ams",
            capacity=25,
        ),
    )

    updated = await register_static_node(
        db_session,
        StaticNodeRegistration(
            name="phase0-node-1",
            ip_address="62.60.156.158",
            panel_node_id="af74d563-a107-4cf0-b4f0-08cad62761d1",
            region="ams",
            capacity=50,
        ),
    )

    nodes = await Repository(db_session).list_nodes()
    assert len(nodes) == 1
    assert updated.id == node.id
    assert updated.provider == "manual"
    assert updated.ip_address == "62.60.156.158"
    assert updated.panel_node_id == "af74d563-a107-4cf0-b4f0-08cad62761d1"
    assert updated.capacity == 50


@pytest.mark.integration
async def test_ensure_capacity_node_returns_available_existing_node(db_session):
    repo = Repository(db_session)
    available = await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-instance-1",
        ip_address="203.0.113.10",
        panel_node_id="panel-node-1",
        current_users=1,
    )
    await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-instance-2",
        ip_address="203.0.113.11",
        panel_node_id="panel-node-2",
        current_users=2,
    )

    node = await ensure_capacity_node(db_session, tier="premium", region="ams")

    assert node == available


@pytest.mark.integration
async def test_assign_subscription_to_node_increments_existing_capacity_and_is_idempotent(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=900)
    now = datetime.now(timezone.utc)
    subscription = await repo.create_subscription(
        user_id=user.id,
        plan="premium_1m",
        tier="premium",
        started_at=now,
        expires_at=now + timedelta(days=30),
        is_active=True,
    )
    node = await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-instance-1",
        ip_address="203.0.113.10",
        panel_node_id="panel-node-1",
        current_users=1,
    )

    assigned = await assign_subscription_to_node(db_session, subscription.id, tier="premium", region="ams")
    assigned_again = await assign_subscription_to_node(db_session, subscription.id, tier="premium", region="ams")

    refreshed_node = await repo.get_node(node.id)
    refreshed_subscription = await repo.get_subscription(subscription.id)
    assert assigned.id == node.id
    assert assigned_again.id == node.id
    assert refreshed_node.current_users == 2
    assert refreshed_subscription.node_ids == ["panel-node-1"]


@pytest.mark.integration
async def test_assign_subscription_to_node_provisions_when_capacity_is_missing(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=901)
    now = datetime.now(timezone.utc)
    subscription = await repo.create_subscription(
        user_id=user.id,
        plan="premium_1m",
        tier="premium",
        started_at=now,
        expires_at=now + timedelta(days=30),
        is_active=True,
    )
    vultr = FakeVultrClient()
    panel = FakePanelClient()

    assigned = await assign_subscription_to_node(
        db_session,
        subscription.id,
        tier="premium",
        region="ams",
        provision_request=_provision_request(),
        vultr_client=vultr,
        panel_client=panel,
    )

    refreshed_subscription = await repo.get_subscription(subscription.id)
    assert assigned.current_users == 1
    assert assigned.panel_node_id == "panel-node-1"
    assert refreshed_subscription.node_ids == ["panel-node-1"]
    assert vultr.created_payload["label"] == "premium-ams-1"


@pytest.mark.integration
async def test_release_subscription_nodes_decrements_without_decommissioning_non_empty_node(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=902)
    now = datetime.now(timezone.utc)
    subscription = await repo.create_subscription(
        user_id=user.id,
        plan="premium_1m",
        tier="premium",
        node_ids=["panel-node-1"],
        started_at=now,
        expires_at=now + timedelta(days=30),
        is_active=True,
    )
    node = await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-instance-1",
        ip_address="203.0.113.10",
        panel_node_id="panel-node-1",
        current_users=2,
    )
    vultr = FakeVultrClient()
    panel = FakePanelClient()

    released = await release_subscription_nodes(
        db_session,
        subscription.id,
        vultr_client=vultr,
        panel_client=panel,
    )

    refreshed_node = await repo.get_node(node.id)
    refreshed_subscription = await repo.get_subscription(subscription.id)
    assert [item.id for item in released] == [node.id]
    assert refreshed_node.current_users == 1
    assert refreshed_subscription.node_ids == []
    assert panel.deleted_node_uuids == []
    assert vultr.deleted_instance_ids == []


@pytest.mark.integration
async def test_release_subscription_nodes_decommissions_empty_vultr_node(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=903)
    now = datetime.now(timezone.utc)
    subscription = await repo.create_subscription(
        user_id=user.id,
        plan="premium_1m",
        tier="premium",
        node_ids=["panel-node-1"],
        started_at=now,
        expires_at=now + timedelta(days=30),
        is_active=True,
    )
    node = await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-instance-1",
        ip_address="203.0.113.10",
        panel_node_id="panel-node-1",
        current_users=1,
    )
    vultr = FakeVultrClient()
    panel = FakePanelClient()

    released = await release_subscription_nodes(
        db_session,
        subscription.id,
        vultr_client=vultr,
        panel_client=panel,
    )

    refreshed_subscription = await repo.get_subscription(subscription.id)
    assert [item.id for item in released] == [node.id]
    assert released[0].current_users == 0
    assert await repo.get_node(node.id) is None
    assert refreshed_subscription.node_ids == []
    assert panel.deleted_node_uuids == ["panel-node-1"]
    assert vultr.deleted_instance_ids == ["vultr-instance-1"]


@pytest.mark.integration
async def test_autoscale_premium_pool_provisions_when_region_lacks_free_slots(db_session):
    repo = Repository(db_session)
    await repo.create_node(
        tier="premium",
        capacity=1,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-full",
        ip_address="203.0.113.20",
        panel_node_id="panel-full",
        current_users=1,
    )
    vultr = FakeVultrClient()
    panel = FakePanelClient()

    result = await autoscale_premium_pool(
        db_session,
        regions=["ams"],
        min_free_slots=1,
        provision_request=_provision_request(),
        vultr_client=vultr,
        panel_client=panel,
    )

    nodes = await repo.list_nodes(tier="premium", region="ams", provider="vultr", status="active")
    assert result.checked_regions == 1
    assert result.provisioned_count == 1
    assert result.decommissioned_count == 0
    assert len(nodes) == 2
    assert vultr.created_payload["region"] == "ams"
    assert panel.create_payload["country_code"] == "NL"


@pytest.mark.integration
async def test_autoscale_premium_pool_decommissions_empty_extra_nodes(db_session):
    repo = Repository(db_session)
    kept = await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-keep",
        ip_address="203.0.113.21",
        panel_node_id="panel-keep",
        current_users=0,
    )
    deleted = await repo.create_node(
        tier="premium",
        capacity=2,
        region="ams",
        provider="vultr",
        provider_instance_id="vultr-delete",
        ip_address="203.0.113.22",
        panel_node_id="panel-delete",
        current_users=0,
    )
    vultr = FakeVultrClient()
    panel = FakePanelClient()

    result = await autoscale_premium_pool(
        db_session,
        regions=["ams"],
        min_free_slots=1,
        min_active_nodes=1,
        provision_request=_provision_request(),
        vultr_client=vultr,
        panel_client=panel,
    )

    assert result.provisioned_count == 0
    assert result.decommissioned_node_ids == [deleted.id]
    assert await repo.get_node(kept.id) is not None
    assert await repo.get_node(deleted.id) is None
    assert panel.deleted_node_uuids == ["panel-delete"]
    assert vultr.deleted_instance_ids == ["vultr-delete"]


@pytest.mark.unit
def test_provision_request_validation_requires_external_config(monkeypatch):
    monkeypatch.setattr("services.autoscaler.settings.VULTR_DEFAULT_REGION", "")

    with pytest.raises(AutoscalerError):
        from services.autoscaler import _resolve_request

        _resolve_request(ProvisionNodeRequest(plan="", os_id=0, config_profile_uuid="", active_inbound_uuids=[]))
