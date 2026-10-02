"""Small HTTP client wrapper for the WSBF server API."""
import threading
import requests

DEFAULT_TIMEOUT = 5.0


class ApiError(Exception):
    """Raised when the server API cannot return a usable response."""


class ApiClient(object):
    """HTTP client with per-thread sessions and request timeouts.

    The client is called from the Tk thread and from background workers,
    and requests sessions are not guaranteed to be thread-safe, so each
    thread gets its own session.
    """

    def __init__(self, timeout=DEFAULT_TIMEOUT, session=None, session_factory=None):
        """Construct an API client.

        :param timeout: request timeout in seconds
        :param session: optional requests-compatible session shared by all threads
        :param session_factory: optional function that creates a session per thread
        """
        self._timeout = timeout
        self._shared_session = session
        self._session_factory = session_factory or requests.Session
        self._local = threading.local()

    def _session(self):
        """Get the session for the current thread."""
        if self._shared_session is not None:
            return self._shared_session

        session = getattr(self._local, "session", None)
        if session is None:
            session = self._session_factory()
            self._local.session = session

        return session

    def get_json(self, url, params=None):
        """GET a JSON response from the server API."""
        try:
            res = self._session().get(url, params=params, timeout=self._timeout)
            res.raise_for_status()
            return res.json()
        except (requests.exceptions.RequestException, ValueError), exc:
            raise ApiError(str(exc))

    def post_text(self, url, params=None):
        """POST to the server API and return text."""
        try:
            res = self._session().post(url, params=params, timeout=self._timeout)
            res.raise_for_status()
            return res.text
        except requests.exceptions.RequestException, exc:
            raise ApiError(str(exc))
