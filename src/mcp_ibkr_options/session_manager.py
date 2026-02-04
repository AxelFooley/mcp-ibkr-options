"""Session manager for handling IBKR connections with automatic cleanup."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict

from .config import settings
from .ibkr_client import IBKRClient

logger = logging.getLogger(__name__)


class Session:
    """Represents a user session with IBKR connection."""

    def __init__(self, session_id: str):
        """Initialize a session."""
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.client: IBKRClient | None = None

    def touch(self) -> None:
        """Update the last accessed timestamp."""
        self.last_accessed = datetime.now()

    def is_expired(self, timeout_minutes: int) -> bool:
        """Check if the session has expired."""
        timeout_delta = timedelta(minutes=timeout_minutes)
        return datetime.now() - self.last_accessed > timeout_delta

    def get_or_create_client(self) -> IBKRClient:
        """Get existing client or create a new one."""
        if self.client is None:
            logger.info(f"Creating new IBKR client for session {self.session_id}")
            self.client = IBKRClient()
            self.client.connect()
        elif not self.client.is_connected:
            logger.warning(f"Client disconnected for session {self.session_id}, reconnecting")
            try:
                self.client.connect()
            except Exception as e:
                logger.error(f"Failed to reconnect: {e}")
                # Create new client if reconnection fails
                self.client = IBKRClient()
                self.client.connect()

        self.touch()
        return self.client

    def cleanup(self) -> None:
        """Clean up session resources."""
        if self.client:
            logger.info(f"Cleaning up session {self.session_id}")
            try:
                self.client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")
            self.client = None


class SessionManager:
    """Manages multiple user sessions with automatic cleanup."""

    def __init__(self) -> None:
        """Initialize the session manager."""
        self.sessions: Dict[str, Session] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the session manager and cleanup task."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager and cleanup all sessions."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Clean up all sessions
        for session in list(self.sessions.values()):
            session.cleanup()

        self.sessions.clear()
        logger.info("Session manager stopped")

    def create_session(self) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = Session(session_id)
        logger.info(f"Created new session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        session = self.sessions.get(session_id)
        if session:
            # Check if expired
            if session.is_expired(settings.session_timeout_minutes):
                logger.info(f"Session {session_id} has expired")
                self._remove_session(session_id)
                return None
            session.touch()
        return session

    def _remove_session(self, session_id: str) -> None:
        """Remove and cleanup a session."""
        session = self.sessions.pop(session_id, None)
        if session:
            session.cleanup()
            logger.info(f"Removed session: {session_id}")

    def delete_session(self, session_id: str) -> bool:
        """Explicitly delete a session."""
        if session_id in self.sessions:
            self._remove_session(session_id)
            return True
        return False

    async def _cleanup_loop(self) -> None:
        """Periodically check for and remove expired sessions."""
        logger.info(
            f"Starting session cleanup loop "
            f"(interval: {settings.session_cleanup_interval_seconds}s, "
            f"timeout: {settings.session_timeout_minutes}m)"
        )

        while self._running:
            try:
                await asyncio.sleep(settings.session_cleanup_interval_seconds)

                expired_sessions = [
                    session_id
                    for session_id, session in self.sessions.items()
                    if session.is_expired(settings.session_timeout_minutes)
                ]

                if expired_sessions:
                    logger.info(f"Cleaning up {len(expired_sessions)} expired sessions")
                    for session_id in expired_sessions:
                        self._remove_session(session_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def get_stats(self) -> dict:
        """Get session statistics."""
        return {
            "total_sessions": len(self.sessions),
            "sessions": [
                {
                    "session_id": session.session_id,
                    "created_at": session.created_at.isoformat(),
                    "last_accessed": session.last_accessed.isoformat(),
                    "has_client": session.client is not None,
                    "is_connected": (
                        session.client.is_connected if session.client else False
                    ),
                }
                for session in self.sessions.values()
            ],
        }


# Global session manager instance
session_manager = SessionManager()
