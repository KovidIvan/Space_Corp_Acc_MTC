"""HTTP client helpers restricted to the runtime host allowlist."""

import ipaddress
from urllib.parse import urlsplit

import httpx


def is_allowed_url(url: str) -> bool:
    """Return whether a URL targets loopback or the Telegram Bot API."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "api.telegram.org":
            return parsed.scheme == "https"
        if hostname == "localhost":
            return True
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False
    except (TypeError, ValueError):
        return False


def validate_outbound_url(url: str) -> str:
    """Return an allowed URL or raise ValueError before any request is sent."""
    if not is_allowed_url(url):
        raise ValueError(f"Outbound URL is not allowlisted: {url!r}")
    return url


class SafeHttpClient:
    """Async HTTP client that validates each target before sending a request."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient()

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        """Send an HTTP request only to an allowlisted URL."""
        validate_outbound_url(url)
        return await self._client.request(method, url, **kwargs)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
