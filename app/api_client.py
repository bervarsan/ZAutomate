"""Small HTTP client wrapper for the WSBF server API."""
import requests

DEFAULT_TIMEOUT = 5.0


class ApiError(Exception):
    """Raised when the server API cannot return a usable response."""


class ApiClient(object):
    """HTTP client with shared session and request timeouts."""

    def __init__(self, timeout=DEFAULT_TIMEOUT, session=None):
        """Construct an API client.

        :param timeout: request timeout in seconds
        :param session: optional requests-compatible session
        """
        self._timeout = timeout
        self._session = session or requests.Session()

    def get_json(self, url, params=None):
        """GET a JSON response from the server API."""
        try:
            res = self._session.get(url, params=params, timeout=self._timeout)
            res.raise_for_status()
            return res.json()
        except (requests.exceptions.RequestException, ValueError), exc:
            raise ApiError(str(exc))

    def post_text(self, url, params=None):
        """POST to the server API and return text."""
        try:
            res = self._session.post(url, params=params, timeout=self._timeout)
            res.raise_for_status()
            return res.text
        except requests.exceptions.RequestException, exc:
            raise ApiError(str(exc))
