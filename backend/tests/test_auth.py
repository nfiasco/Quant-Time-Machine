"""Authentication boundaries with locally signed tokens and a synthetic JWKS server."""

import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from uuid import UUID

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth import AUTH_TIMEOUT_SECONDS, InvalidAccessToken, TokenVerifier
from app.config import Settings
from app.main import create_app

PROJECT = "https://fixture.supabase.co"
USER_ID = "5ae11ec7-df18-4e7d-bdeb-45ba0eb0029a"
OTHER_USER_ID = "5ae11ec7-df18-4e7d-bdeb-45ba0eb0029b"
LEGACY_TEST_SECRET = "synthetic-test-signing-secret-at-least-32-bytes"


@dataclass
class SigningKey:
    private: Any
    jwk: dict[str, Any]
    algorithm: str
    kid: str


def signing_key(algorithm: str, kid: str) -> SigningKey:
    private = (
        ec.generate_private_key(ec.SECP256R1())
        if algorithm == "ES256"
        else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    jwk = jwt.algorithms.get_default_algorithms()[algorithm].to_jwk(
        private.public_key(), as_dict=True
    )
    jwk.update(kid=kid, alg=algorithm, use="sig")
    return SigningKey(private, jwk, algorithm, kid)


@pytest.fixture(scope="module")
def keys() -> list[SigningKey]:
    return [
        signing_key("ES256", "first"),
        signing_key("ES256", "rotated"),
        signing_key("RS256", "rsa"),
    ]


def claims(**changes: Any) -> dict[str, Any]:
    now = int(time.time())
    return {
        "sub": USER_ID,
        "iss": f"{PROJECT}/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "exp": now + 300,
        "iat": now - 5,
        **changes,
    }


def token(
    key: SigningKey, payload: dict[str, Any] | None = None, **headers: Any
) -> str:
    # Sign raw JSON so malformed claim types reach the verifier, even when the
    # higher-level encoder would refuse to create such a token.
    return jwt.api_jws.encode(
        json.dumps(claims() if payload is None else payload).encode(),
        key.private,
        algorithm=key.algorithm,
        headers={"kid": key.kid, **headers},
    )


class JwksServer:
    def __init__(self, keys: list[SigningKey]) -> None:
        self.payload: Any = {"keys": [key.jwk for key in keys]}
        self.calls: list[str] = []
        self.unavailable = False

    def open(self, request: Any, *, timeout: float) -> io.BytesIO:
        assert timeout == AUTH_TIMEOUT_SECONDS
        self.calls.append(request.full_url)
        if self.unavailable:
            raise URLError("synthetic provider detail must not appear in responses")
        return io.BytesIO(json.dumps(self.payload).encode())


@pytest.fixture
def jwks(monkeypatch: pytest.MonkeyPatch, keys: list[SigningKey]) -> JwksServer:
    server = JwksServer([keys[0], keys[2]])
    monkeypatch.setattr(
        "jwt.jwks_client.urllib.request.build_opener", lambda *args: server
    )
    return server


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, supabase_url=PROJECT, data_dir=tmp_path)


@pytest.fixture
def client(settings: Settings, jwks: JwksServer) -> TestClient:
    with TestClient(create_app(settings)) as client:
        yield client


def authenticated(
    client: TestClient, encoded: str, path: str = "/v1/me"
) -> httpx2.Response:
    return client.get(path, headers={"Authorization": f"Bearer {encoded}"})


def assert_unauthorized(response: httpx2.Response) -> None:
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "unauthorized",
            "message": "Sign in with a valid access token.",
            "details": [],
        }
    }
    assert response.headers["www-authenticate"] == "Bearer"
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.parametrize("index", [0, 2], ids=["ES256", "RS256"])
def test_verified_subject_is_available_to_private_handlers(
    client: TestClient,
    keys: list[SigningKey],
    jwks: JwksServer,
    index: int,
) -> None:
    response = authenticated(client, token(keys[index]))
    assert response.status_code == 200
    assert response.json() == {"user_id": USER_ID}
    assert response.headers["cache-control"] == "private, no-store"
    assert "Authorization" in response.headers["vary"].split(", ")
    assert jwks.calls == [f"{PROJECT}/auth/v1/.well-known/jwks.json"]


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Basic abc",
        "Bearer",
        "Bearer malformed",
        "Bearer a.b.c",
        "Bearer " + "x" * 16_385,
    ],
)
def test_missing_or_malformed_credentials_are_401(
    client: TestClient,
    jwks: JwksServer,
    authorization: str | None,
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}
    assert_unauthorized(client.get("/v1/me", headers=headers))
    assert jwks.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": int(time.time()) - 60},
        {"iss": "https://other.supabase.co/auth/v1"},
        {"aud": "anon"},
        {"sub": "not-a-uuid"},
        {"role": "service_role"},
        {"role": "anon"},
        {"is_anonymous": True},
        {"exp": "4102444800"},
        {"nbf": int(time.time()) + 3600},
        {"iat": int(time.time()) + 3600},
        {"sub": 123},
        {"aud": ["unrelated"]},
        {"iss": [f"{PROJECT}/auth/v1"]},
    ],
)
def test_invalid_expired_or_wrong_project_claims_are_401(
    client: TestClient,
    keys: list[SigningKey],
    changes: dict[str, Any],
) -> None:
    encoded = token(keys[0], claims(**changes))
    response = authenticated(client, encoded)
    assert_unauthorized(response)
    assert encoded not in response.text


@pytest.mark.parametrize("missing", ["exp", "iss", "aud", "sub", "role"])
def test_required_claims_cannot_be_omitted(
    client: TestClient,
    keys: list[SigningKey],
    missing: str,
) -> None:
    payload = claims()
    payload.pop(missing)
    assert_unauthorized(authenticated(client, token(keys[0], payload)))


def test_a_signature_from_another_project_is_rejected(
    client: TestClient, keys: list[SigningKey]
) -> None:
    assert_unauthorized(authenticated(client, token(keys[1], kid=keys[0].kid)))


@pytest.mark.parametrize("algorithm", ["none", "HS256"])
def test_symmetric_and_unsigned_tokens_cannot_use_the_public_key_path(
    client: TestClient,
    jwks: JwksServer,
    algorithm: str,
) -> None:
    encoded = jwt.encode(
        claims(),
        None if algorithm == "none" else LEGACY_TEST_SECRET,
        algorithm=algorithm,
        headers={"kid": "first"},
    )
    assert_unauthorized(authenticated(client, encoded))
    assert jwks.calls == []


@pytest.mark.parametrize(
    "headers",
    [{"kid": ""}, {"kid": 123}, {"kid": "x" * 257}, {"crit": ["unsupported"]}],
)
def test_malformed_key_identifiers_and_critical_extensions_are_rejected(
    client: TestClient,
    keys: list[SigningKey],
    headers: dict[str, Any],
) -> None:
    # Build the JWT manually when an invalid kid would be rejected by jwt.encode itself.
    valid = token(keys[0])
    parts = valid.split(".")
    new_header = {"alg": "ES256", "typ": "JWT", "kid": keys[0].kid, **headers}
    parts[0] = jwt.utils.base64url_encode(json.dumps(new_header).encode()).decode()
    assert_unauthorized(authenticated(client, ".".join(parts)))


def test_token_urls_cannot_choose_a_jwks_source(
    client: TestClient,
    keys: list[SigningKey],
    jwks: JwksServer,
) -> None:
    response = authenticated(
        client,
        token(keys[0], jku="https://attacker.invalid/keys", x5u="file:///tmp/secret"),
    )
    assert response.status_code == 200
    assert jwks.calls == [f"{PROJECT}/auth/v1/.well-known/jwks.json"]


def test_private_identity_is_never_in_the_shared_as_of_cache(
    client: TestClient,
    keys: list[SigningKey],
) -> None:
    for ident in [USER_ID, OTHER_USER_ID, USER_ID]:
        response = authenticated(
            client, token(keys[0], claims(sub=ident)), "/v1/me?as_of=2020-06-05"
        )
        assert response.json() == {"user_id": ident}
        assert "etag" not in response.headers
        assert "cache-status" not in response.headers
    assert_unauthorized(client.get("/v1/me?as_of=2020-06-05"))


def test_jwks_are_cached_but_each_request_checks_its_token(
    client: TestClient,
    keys: list[SigningKey],
    jwks: JwksServer,
) -> None:
    assert authenticated(client, token(keys[0])).status_code == 200
    assert (
        authenticated(client, token(keys[0], claims(sub=OTHER_USER_ID))).status_code
        == 200
    )
    assert_unauthorized(authenticated(client, token(keys[0], claims(exp=1))))
    assert len(jwks.calls) == 1


def test_unknown_keys_are_rate_limited_then_refreshed_for_rotation(
    client: TestClient,
    keys: list[SigningKey],
    jwks: JwksServer,
) -> None:
    assert authenticated(client, token(keys[0])).status_code == 200
    for kid in ["unknown-1", "unknown-2"]:
        assert_unauthorized(authenticated(client, token(keys[0], kid=kid)))
    assert len(jwks.calls) == 1
    # Advance only this client's cooldown, without sleeping or changing JWT time.
    client.app.state.token_verifier.jwks._last_successful_fetch -= 31
    jwks.payload = {"keys": [keys[0].jwk, keys[1].jwk]}
    assert authenticated(client, token(keys[1])).status_code == 200
    assert len(jwks.calls) == 2


def test_expired_jwks_cannot_keep_a_revoked_key_forever(
    client: TestClient,
    keys: list[SigningKey],
    jwks: JwksServer,
) -> None:
    assert authenticated(client, token(keys[0])).status_code == 200
    cache = client.app.state.token_verifier.jwks.jwk_set_cache
    cache.jwk_set_with_timestamp.timestamp -= 601
    jwks.payload = {"keys": [keys[1].jwk]}
    assert_unauthorized(authenticated(client, token(keys[0])))
    assert authenticated(client, token(keys[1])).status_code == 200
    assert len(jwks.calls) == 2


def test_unavailable_jwks_fails_closed_without_provider_details(
    client: TestClient,
    keys: list[SigningKey],
    jwks: JwksServer,
) -> None:
    jwks.unavailable = True
    response = authenticated(client, token(keys[0]))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"
    assert "synthetic provider" not in response.text
    assert "no-store" in response.headers["cache-control"]


def test_missing_configuration_keeps_public_routes_usable(
    tmp_path: Path, keys: list[SigningKey]
) -> None:
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path))) as client:
        assert authenticated(client, token(keys[0])).status_code == 503
        assert_unauthorized(client.get("/v1/me"))
        assert client.get("/health").status_code == 200
        assert client.get("/v1/catalog/signals").status_code == 200
        assert client.get("/v1/knowledge-time?as_of=2020-06-05").status_code == 200


def test_public_market_reads_ignore_an_invalid_optional_token(
    client: TestClient,
) -> None:
    assert (
        client.get(
            "/v1/catalog/signals", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 200
    )


def test_openapi_marks_only_account_routes_as_protected(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v1/me"]["get"]["security"] == [{"SupabaseAccessToken": []}]
    for path, operations in schema["paths"].items():
        if path == "/v1/me":
            continue
        for operation in operations.values():
            assert not operation.get("security"), path


def test_cors_errors_can_be_read_by_the_allowed_frontend(client: TestClient) -> None:
    response = client.get("/v1/me", headers={"Origin": "http://localhost:3000"})
    assert_unauthorized(response)
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_legacy_verification_requires_explicit_opt_in(settings: Settings) -> None:
    encoded = jwt.encode(claims(), LEGACY_TEST_SECRET, algorithm="HS256")
    with pytest.raises(InvalidAccessToken):
        TokenVerifier(settings).verify(encoded)


def test_legacy_tokens_are_verified_by_auth_and_match_the_returned_user(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = TokenVerifier(
        settings.model_copy(
            update={
                "supabase_allow_legacy_hs256": True,
                "supabase_publishable_key": SecretStr("sb_publishable_fixture"),
            }
        )
    )
    seen = []

    def provider(
        url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool
    ) -> httpx2.Response:
        assert url == f"{PROJECT}/auth/v1/user"
        assert headers["apikey"] == "sb_publishable_fixture"
        assert timeout == AUTH_TIMEOUT_SECONDS
        assert follow_redirects is False
        seen.append(headers["Authorization"])
        encoded = headers["Authorization"].removeprefix("Bearer ")
        try:
            decoded = jwt.decode(
                encoded,
                LEGACY_TEST_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.InvalidTokenError:
            return httpx2.Response(401)
        return httpx2.Response(200, json={"id": decoded["sub"]})

    monkeypatch.setattr("app.auth.httpx2.get", provider)
    good = jwt.encode(claims(), LEGACY_TEST_SECRET, algorithm="HS256")
    assert verifier.verify(good).user_id == UUID(USER_ID)
    wrong = jwt.encode(
        claims(), "different-synthetic-signing-secret-32-bytes", algorithm="HS256"
    )
    with pytest.raises(InvalidAccessToken):
        verifier.verify(wrong)
    assert len(seen) == 2


def test_legacy_response_cannot_substitute_another_user(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = TokenVerifier(
        settings.model_copy(
            update={
                "supabase_allow_legacy_hs256": True,
                "supabase_publishable_key": SecretStr("sb_publishable_fixture"),
            }
        )
    )
    monkeypatch.setattr(
        "app.auth.httpx2.get",
        lambda *args, **kwargs: httpx2.Response(200, json={"id": OTHER_USER_ID}),
    )
    with pytest.raises(InvalidAccessToken):
        verifier.verify(jwt.encode(claims(), LEGACY_TEST_SECRET, algorithm="HS256"))
