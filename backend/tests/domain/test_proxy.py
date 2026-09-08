from hypothesis import given
from hypothesis import strategies as st

from app.domain.proxy import line_to_url, mask_proxy_url, proxy_settings, session_id_from_line

secrets = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126, blacklist_characters=":@/?#[]%"),
    min_size=4,
    max_size=20,
)
hosts = st.sampled_from(["proxy.example.com", "10.0.0.1", "mobile.provider.ru"])
ports = st.integers(min_value=1, max_value=65535)
schemes = st.sampled_from(["http", "https", "socks5"])


def test_mask_hides_credentials_but_keeps_endpoint() -> None:
    masked = mask_proxy_url("http://user:s3cret@proxy.example.com:8000")

    assert masked == "http://***@proxy.example.com:8000"


def test_mask_leaves_anonymous_proxy_readable() -> None:
    assert mask_proxy_url("socks5://10.0.0.1:1080") == "socks5://10.0.0.1:1080"


def test_mask_handles_empty_and_garbage() -> None:
    assert mask_proxy_url(None) is None
    assert mask_proxy_url("") is None
    assert mask_proxy_url("not a url") == "***"


def test_proxy_settings_split_credentials_for_playwright() -> None:
    assert proxy_settings("http://user:s3cret@proxy.example.com:8000") == {
        "server": "http://proxy.example.com:8000",
        "username": "user",
        "password": "s3cret",
    }


def test_proxy_settings_without_credentials() -> None:
    assert proxy_settings("socks5://10.0.0.1:1080") == {"server": "socks5://10.0.0.1:1080"}
    assert proxy_settings(None) is None
    assert proxy_settings("nonsense") is None


@given(scheme=schemes, user=secrets, password=secrets, host=hosts, port=ports)
def test_masked_url_never_leaks_the_password(
    scheme: str, user: str, password: str, host: str, port: int
) -> None:
    url = f"{scheme}://{user}:{password}@{host}:{port}"

    masked = mask_proxy_url(url)

    assert masked is not None
    assert password not in masked
    assert user not in masked
    assert host in masked
    assert str(port) in masked


@given(scheme=schemes, user=secrets, password=secrets, host=hosts, port=ports)
def test_proxy_settings_keep_credentials_out_of_the_server_field(
    scheme: str, user: str, password: str, host: str, port: int
) -> None:
    settings = proxy_settings(f"{scheme}://{user}:{password}@{host}:{port}")

    assert settings is not None
    assert settings["server"] == f"{scheme}://{host}:{port}"
    assert settings.get("username") == user
    assert settings.get("password") == password


LINE = (
    "res.lteboost.com:1000:user_e0121bae:pw_country-RU_city-Moscow_lifetime-10080_session-lf33lu8z"
)


def test_line_to_url_builds_a_usable_proxy_url() -> None:
    url = line_to_url(LINE)

    assert url == (
        "http://user_e0121bae:pw_country-RU_city-Moscow_lifetime-10080_session-lf33lu8z"
        "@res.lteboost.com:1000"
    )
    assert proxy_settings(url) == {
        "server": "http://res.lteboost.com:1000",
        "username": "user_e0121bae",
        "password": "pw_country-RU_city-Moscow_lifetime-10080_session-lf33lu8z",
    }


def test_line_to_url_honours_the_protocol() -> None:
    url = line_to_url("res.lteboost.com:1002:login:pass", "socks5")

    assert url is not None
    assert url.startswith("socks5://")


def test_line_to_url_quotes_a_password_with_url_characters() -> None:
    url = line_to_url("host:1000:login:p@ss/word?x")

    assert url is not None
    assert "p%40ss%2Fword%3Fx" in url
    assert proxy_settings(url) == {
        "server": "http://host:1000",
        "username": "login",
        "password": "p@ss/word?x",
    }


def test_line_to_url_rejects_malformed_lines() -> None:
    assert line_to_url("") is None
    assert line_to_url("host:1000:login") is None
    assert line_to_url("host:notaport:login:pass") is None
    assert line_to_url(":1000:login:pass") is None


def test_session_id_is_read_from_the_line() -> None:
    assert session_id_from_line(LINE) == "lf33lu8z"
    assert session_id_from_line("host:1000:login:plainpass") is None
