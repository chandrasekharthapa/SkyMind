import time
import pytest
from backend.services.memory_manager import (
    MemoryManager,
    SessionHistory,
    SessionState,
    UserTravelProfile
)


def test_session_history_save_and_retrieve():
    """Verify session history saving, retrieval, and message management."""
    mem = MemoryManager()
    msgs = [{"role": "user", "content": "Flight to BOM"}]
    
    saved_hist = mem.save_session_history("sess_mem_1", msgs)
    assert len(saved_hist.messages) == 1
    assert saved_hist.messages[0]["content"] == "Flight to BOM"

    retrieved_hist = mem.get_session_history("sess_mem_1")
    assert len(retrieved_hist.messages) == 1
    assert retrieved_hist.session_id == "sess_mem_1"


def test_session_history_ttl_expiration():
    """Verify short-term session history expires according to TTL policy."""
    mem = MemoryManager()
    hist = SessionHistory(session_id="sess_exp", ttl_seconds=1, last_updated=time.time() - 10)
    mem._ram_histories["sess_exp"] = hist

    retrieved = mem.get_session_history("sess_exp")
    assert len(retrieved.messages) == 0  # Expired and cleared


def test_session_state_optimistic_concurrency():
    """Verify state updates and version-based optimistic concurrency locking."""
    mem = MemoryManager()
    state = mem.get_session_state("sess_state_1")
    assert state.version == 1

    updated_1 = mem.update_session_state("sess_state_1", {"origin": "DEL", "destination": "BOM"})
    assert updated_1.origin == "DEL"
    assert updated_1.destination == "BOM"
    assert updated_1.version == 2

    # Lock violation test
    with pytest.raises(ValueError, match="Optimistic lock violation"):
        mem.update_session_state("sess_state_1", {"origin": "BLR"}, expected_version=1)


def test_user_travel_profile_persistence():
    """Verify user travel profiles are stored persistently without expiration."""
    mem = MemoryManager()
    profile = UserTravelProfile(user_id="usr_101", preferred_airline="6E", home_airport="DEL")
    mem.save_user_profile(profile)

    fetched = mem.get_user_profile("usr_101")
    assert fetched.preferred_airline == "6E"
    assert fetched.home_airport == "DEL"


def test_ram_fallback_resilience():
    """Verify memory operations fall back to RAM seamlessly if remote backends fail."""
    mem = MemoryManager(redis_client="invalid_redis_mock")
    state = mem.update_session_state("sess_fallback", {"origin": "DEL"})
    
    assert state.origin == "DEL"
    assert mem.get_session_state("sess_fallback").origin == "DEL"
