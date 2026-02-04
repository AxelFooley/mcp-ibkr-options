"""Tests for session manager."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from mcp_ibkr_options.session_manager import Session, SessionManager


@pytest.fixture
def session_manager():
    """Create a fresh session manager for each test."""
    manager = SessionManager()
    yield manager
    # Cleanup
    for session in list(manager.sessions.values()):
        session.cleanup()
    manager.sessions.clear()


def test_session_creation():
    """Test session creation and initialization."""
    session = Session("test-123")

    assert session.session_id == "test-123"
    assert session.client is None
    assert isinstance(session.created_at, datetime)
    assert isinstance(session.last_accessed, datetime)


def test_session_touch():
    """Test session touch updates last_accessed."""
    session = Session("test-123")
    original_time = session.last_accessed

    # Wait a bit
    import time

    time.sleep(0.1)

    session.touch()
    assert session.last_accessed > original_time


def test_session_expiration():
    """Test session expiration detection."""
    session = Session("test-123")

    # Not expired with normal timeout
    assert not session.is_expired(5)

    # Make it expired by backdating last_accessed
    session.last_accessed = datetime.now() - timedelta(minutes=10)
    assert session.is_expired(5)


def test_create_session(session_manager):
    """Test creating a new session."""
    session_id = session_manager.create_session()

    assert session_id is not None
    assert session_id in session_manager.sessions
    assert isinstance(session_manager.sessions[session_id], Session)


def test_get_session(session_manager):
    """Test getting an existing session."""
    session_id = session_manager.create_session()

    session = session_manager.get_session(session_id)
    assert session is not None
    assert session.session_id == session_id


def test_get_nonexistent_session(session_manager):
    """Test getting a non-existent session returns None."""
    session = session_manager.get_session("nonexistent")
    assert session is None


def test_get_expired_session(session_manager):
    """Test getting an expired session returns None and removes it."""
    session_id = session_manager.create_session()

    # Expire the session
    session_manager.sessions[session_id].last_accessed = datetime.now() - timedelta(minutes=10)

    # Getting it should return None and remove it
    result = session_manager.get_session(session_id)
    assert result is None
    assert session_id not in session_manager.sessions


def test_delete_session(session_manager):
    """Test deleting a session."""
    session_id = session_manager.create_session()

    assert session_manager.delete_session(session_id)
    assert session_id not in session_manager.sessions


def test_delete_nonexistent_session(session_manager):
    """Test deleting a non-existent session returns False."""
    assert not session_manager.delete_session("nonexistent")


@pytest.mark.asyncio
async def test_session_manager_start_stop(session_manager):
    """Test session manager lifecycle."""
    await session_manager.start()
    assert session_manager._running
    assert session_manager._cleanup_task is not None

    await session_manager.stop()
    assert not session_manager._running


@pytest.mark.asyncio
async def test_cleanup_loop_removes_expired_sessions(session_manager):
    """Test that cleanup loop removes expired sessions."""
    # Create a session and immediately expire it
    session_id = session_manager.create_session()
    session_manager.sessions[session_id].last_accessed = datetime.now() - timedelta(minutes=10)

    # Mock the cleanup interval to be very short
    with patch("mcp_ibkr_options.session_manager.settings") as mock_settings:
        mock_settings.session_cleanup_interval_seconds = 0.1
        mock_settings.session_timeout_minutes = 5

        await session_manager.start()

        # Wait for cleanup to run
        await asyncio.sleep(0.3)

        # Session should be gone
        assert session_id not in session_manager.sessions

        await session_manager.stop()


def test_get_stats(session_manager):
    """Test getting session statistics."""
    # Create a few sessions
    session_manager.create_session()
    session_manager.create_session()

    stats = session_manager.get_stats()

    assert stats["total_sessions"] == 2
    assert len(stats["sessions"]) == 2
    assert all("session_id" in s for s in stats["sessions"])
    assert all("created_at" in s for s in stats["sessions"])
    assert all("last_accessed" in s for s in stats["sessions"])


@pytest.mark.asyncio
async def test_session_manager_stops_cleanly_with_active_sessions(session_manager):
    """Test that stopping cleans up all active sessions."""
    # Create multiple sessions
    session_manager.create_session()
    session_manager.create_session()

    await session_manager.start()
    await session_manager.stop()

    # All sessions should be cleaned up
    assert len(session_manager.sessions) == 0
