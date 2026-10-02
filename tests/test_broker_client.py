from unittest.mock import patch

from openstack_vdi.broker_client import BrokerBackend
from openstack_vdi.models import LoginSession, UserError


def test_expired_session_can_always_log_out_locally():
    backend = BrokerBackend()
    backend.session = LoginSession("user", "VDI", "id", "scope")
    backend.http.headers["Authorization"] = "Bearer old-token"
    with patch.object(backend, "request", side_effect=UserError("expired")):
        backend.close()
    assert backend.session is None
    assert "Authorization" not in backend.http.headers
