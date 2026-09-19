import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("自动化测试禁止真实网络和模型付费调用")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def pytest_collection_modifyitems(items):
    for item in items:
        name = item.path.name
        item.add_marker(pytest.mark.unit if name == "test_rules.py" else pytest.mark.integration)
        if name == "test_workflows.py":
            item.add_marker(pytest.mark.fixture_workflow)
