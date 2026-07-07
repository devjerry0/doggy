import base64
import ssl

from fastapi.testclient import TestClient

from doggy.core.config import Settings
from doggy.web.door import create_door_app


def _ca_pem() -> bytes:
    # Stand-in for a real CA cert: any base64 body works for the DER round-trip
    # the mobileconfig payload does (ssl.PEM_cert_to_DER_cert just base64-decodes).
    der = bytes(range(4, 84))
    body = base64.b64encode(der).decode()
    return ("-----BEGIN CERTIFICATE-----\n" + body
            + "\n-----END CERTIFICATE-----\n").encode()


def _door(tmp_path, with_ca=True):
    kwargs: dict = {}
    if with_ca:
        ca = tmp_path / "ca.pem"
        ca.write_bytes(_ca_pem())
        kwargs["ca_cert"] = ca
    s = Settings(event_log_dir=tmp_path, ssl_port=8443, **kwargs)
    return TestClient(create_door_app(s))


def test_door_page_served(tmp_path):
    r = _door(tmp_path).get("/")
    assert r.status_code == 200
    assert "Secure this device" in r.text
    assert "/ca.pem" in r.text
    assert "8443" in r.text


def test_ping_is_204_with_cors(tmp_path):
    r = _door(tmp_path).get("/ping")
    assert r.status_code == 204
    assert r.headers["access-control-allow-origin"] == "*"


def test_ca_pem_served(tmp_path):
    r = _door(tmp_path).get("/ca.pem")
    assert r.status_code == 200
    assert r.content == _ca_pem()


def test_mobileconfig_is_apple_profile(tmp_path):
    r = _door(tmp_path).get("/ca.mobileconfig")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-apple-aspen-config")
    assert "watchdoggy-ca.mobileconfig" in r.headers["content-disposition"]
    body = r.text
    assert "com.apple.security.root" in body
    der = ssl.PEM_cert_to_DER_cert(_ca_pem().decode())
    assert base64.b64encode(der).decode()[:24] in body


def test_mobileconfig_is_stable_across_downloads(tmp_path):
    c = _door(tmp_path)
    assert c.get("/ca.mobileconfig").text == c.get("/ca.mobileconfig").text


def test_setup_routes_404_without_ca_but_ping_ok(tmp_path):
    c = _door(tmp_path, with_ca=False)
    assert c.get("/").status_code == 404
    assert c.get("/ca.pem").status_code == 404
    assert c.get("/ca.mobileconfig").status_code == 404
    # Probes must work regardless: the door has to answer /ping even before setup.
    assert c.get("/ping").status_code == 204
