import asyncio
import base64
import json
import time
import logging

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:3000"


class TokenManager:
    """
    Manages JWT access/refresh tokens for the EcoMarket HTTP client.

    Design decisions:
    - decode_payload() decodes JWT payload WITHOUT verifying signature
      (client-side validation only; server verifies signature).
    - is_expiring_soon() uses a configurable margin (default 60 s) to
      proactively refresh tokens before they expire.
    - refresh_access_token() uses an asyncio.Lock + shared Task pattern
      to guarantee INV-B3: only one concurrent HTTP request is sent to
      /auth/token even when multiple coroutines request a refresh.
    - All methods avoid logging token values (INV-B2).
    - No circuit-breaker attributes are stored (INV-B1).
    """

    def __init__(self, base_url: str = BASE_URL):
        self._base_url = base_url.rstrip("/")
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._session: aiohttp.ClientSession | None = None
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._margen_expiracion = 60  # seconds before expiry to consider "expiring soon"

    def decode_payload(self, token: str) -> dict:
        """
        Decode JWT payload without verifying signature (INV-A1: no token in logs).

        Splits the token, restores Base64URL padding, decodes the payload,
        and validates the presence of ``sub``, ``exp``, and ``rol`` claims.
        """
        try:
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("Invalid JWT format: expected 3 parts")

            payload_part = parts[1]
            padding = 4 - len(payload_part) % 4
            if padding != 4:
                payload_part += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_part)
            payload = json.loads(payload_bytes)

            for claim in ("sub", "exp", "rol"):
                if claim not in payload:
                    raise ValueError(f"JWT payload missing required claim: {claim}")

            return payload
        except Exception as exc:
            # INV-B2: never log the raw token value
            logger.error("Failed to decode JWT payload: %s", exc)
            raise

    def is_expiring_soon(self, margen_segundos: int = None) -> bool:
        """
        Check if the current access token will expire within *margen_segundos*.

        Defaults to ``self._margen_expiracion`` (60 seconds).
        Returns ``True`` when no token is available so that callers trigger
        a refresh proactively.
        """
        if self._access_token is None:
            return True

        margen = (
            margen_segundos
            if margen_segundos is not None
            else self._margen_expiracion
        )

        try:
            payload = self.decode_payload(self._access_token)
            exp = payload.get("exp", 0)
            return time.time() + margen >= exp
        except Exception:
            # If decoding fails, treat the token as expiring
            return True

    def get_auth_header(self) -> dict:
        """
        Return Authorization Bearer header.

        Raises:
            ValueError: If no access token is currently stored.
        """
        if not self._access_token:
            raise ValueError("No access token available")
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _do_refresh(self) -> str:
        """
        Perform the actual HTTP refresh request to ``/auth/token``.

        Sends the refresh token (or the current access token as fallback)
        in the ``Authorization`` header.  Stores new tokens on success.
        """
        session = await self._get_session()
        headers = {}

        # Prefer refresh token for the refresh endpoint; fall back to access token
        auth_token = self._refresh_token or self._access_token
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        url = f"{self._base_url}/auth/token"
        logger.info("Refreshing access token via %s", url)

        async with session.post(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token:
            raise RuntimeError("Refresh response missing access_token")

        self.store_tokens(access_token, refresh_token)
        logger.info("Access token refreshed successfully")
        return self._access_token

    async def refresh_access_token(self) -> str:
        """
        Singleton refresh: only one concurrent HTTP call to /auth/token.

        INV-B3: multiple callers await the same refresh result.  Uses an
        :class:`asyncio.Lock` together with a shared :class:`asyncio.Task`
        so that concurrent invocations deduplicate in-flight refreshes.
        """
        # Fast path: token is still valid and not near expiry
        if self._access_token and not self.is_expiring_soon():
            return self._access_token

        async with self._refresh_lock:
            # Double-check after acquiring the lock in case another caller
            # already refreshed while we were waiting.
            if self._access_token and not self.is_expiring_soon():
                return self._access_token

            # If a refresh is already in flight, reuse it
            if self._refresh_task is not None and not self._refresh_task.done():
                task = self._refresh_task
            else:
                self._refresh_task = asyncio.create_task(self._do_refresh())
                task = self._refresh_task

        # Await the shared task outside the lock so other concurrent callers
        # can enter the critical section, see the in-flight task, and await
        # the same result without spawning additional HTTP requests.
        return await task

    def store_tokens(self, access_token: str, refresh_token: str) -> None:
        """
        Persist access and refresh tokens in memory.

        Never logs token values (INV-B2).
        """
        self._access_token = access_token
        self._refresh_token = refresh_token

    async def login(
        self,
        username: str = "op1",
        password: str = "",
        rol: str = "viewer",
    ) -> dict:
        """
        POST /auth/login with credentials and store returned tokens.

        The mock server defaults ``exp_seconds`` to 900 when omitted.
        """
        session = await self._get_session()
        payload = {
            "username": username,
            "password": password,
            "rol": rol,
        }
        url = f"{self._base_url}/auth/login"
        logger.info("Logging in user '%s' to %s", username, url)

        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            data = await response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token:
            raise RuntimeError("Login response missing access_token")

        self.store_tokens(access_token, refresh_token)
        logger.info("Login successful for user '%s'", username)
        return data

    @property
    def access_token(self) -> str | None:
        return self._access_token

    def logout(self) -> None:
        """Clear stored tokens."""
        self._access_token = None
        self._refresh_token = None
        logger.info("User logged out, tokens cleared")

    # Helper
    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
