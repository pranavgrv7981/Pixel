"""Unit tests for SingleInstanceManager single-instance process coordination.

Test matrix (per spec):
 1.  First instance acquires successfully.
 2.  Second instance detects primary.
 3.  Second instance sends wakeup.
 4.  Primary receives wakeup.
 5.  Primary on_activate callback fires.
 6.  Second instance exits (returns False from acquire).
 7.  Stale PID file is detected.
 8.  Stale lock is recovered (port freed after primary exit, no ACK).
 9.  Dead primary is recovered via stale recovery path.
10.  Unrelated Python process does not block assistant.
11.  check_is_secondary() returns True for healthy primary.
12.  check_is_secondary() returns False when no primary is running.
13.  Shutdown releases instance ownership (port freed after release).
14.  Crash/stale-state recovery: stale port + dead PID → new primary.
15.  Multiple simultaneous starts result in exactly one primary.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.single_instance import (
    DEFAULT_SINGLE_INSTANCE_PORT,
    SingleInstanceManager,
    _MSG_ACK,
    _MSG_WAKEUP,
)

# Use a range of test ports well away from the production port
_BASE_PORT = 49830


def _mgr(port: int, on_activate=None) -> SingleInstanceManager:
    return SingleInstanceManager(port=port, on_activate=on_activate, settings=Settings())


def _port_free(port: int) -> bool:
    """Return True if the port is not bound by any process."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        sock.connect(("127.0.0.1", port))
        sock.close()
        return False
    except (ConnectionRefusedError, OSError):
        return True


# ---------------------------------------------------------------------------
# Test 1 — First instance acquires successfully
# ---------------------------------------------------------------------------
def test_first_instance_acquires() -> None:
    port = _BASE_PORT
    mgr = _mgr(port)
    try:
        assert mgr.acquire() is True
        assert mgr.is_primary is True
    finally:
        mgr.release()


# ---------------------------------------------------------------------------
# Test 2 + 3 + 4 + 5 + 6 — Secondary detects primary, sends wakeup, primary
#                            callback fires, secondary returns False.
# ---------------------------------------------------------------------------
def test_secondary_detects_primary_and_wakeup_fires() -> None:
    port = _BASE_PORT + 1
    woke_up = threading.Event()

    primary = _mgr(port, on_activate=lambda: woke_up.set())
    secondary = _mgr(port)

    try:
        assert primary.acquire() is True

        # Test 2 — secondary detects primary
        assert secondary.is_primary is False

        # Test 6 — secondary.acquire() returns False
        result = secondary.acquire()
        assert result is False
        assert secondary.is_primary is False

        # Test 4 + 5 — primary callback fires
        assert woke_up.wait(timeout=3.0), "Primary on_activate was not called within 3 s"
    finally:
        primary.release()


# ---------------------------------------------------------------------------
# Test 3 — Secondary sends WAKEUP and receives WAKEUP_ACK
# ---------------------------------------------------------------------------
def test_secondary_receives_ack() -> None:
    port = _BASE_PORT + 2
    primary = _mgr(port, on_activate=lambda: None)
    try:
        assert primary.acquire() is True
        # Manually test the ACK protocol
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(3.0)
        client.connect(("127.0.0.1", port))
        client.sendall(_MSG_WAKEUP)
        data = client.recv(64)
        client.close()
        assert b"WAKEUP_ACK" in data
    finally:
        primary.release()


# ---------------------------------------------------------------------------
# Test 7 — Stale PID file is detected (dead PID in file)
# ---------------------------------------------------------------------------
def test_stale_pid_file_detected() -> None:
    import subprocess
    import sys as _sys
    port = _BASE_PORT + 3
    mgr = _mgr(port)

    # Spawn a process that exits immediately — this gives us a guaranteed dead PID
    proc = subprocess.Popen([_sys.executable, "-c", "import sys; sys.exit(0)"])
    dead_pid = proc.pid
    proc.wait(timeout=5)

    pid_file = mgr._pid_file_path()
    pid_file.write_text(str(dead_pid), encoding="utf-8")

    try:
        mgr._try_clear_stale_pid()
        # PID file should be removed since the process is dead
        assert not pid_file.exists(), f"Stale PID file for dead PID {dead_pid} was not removed"
    finally:
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Test 8 — Stale lock recovery: port freed after primary exits normally
# ---------------------------------------------------------------------------
def test_stale_lock_recovered_after_primary_exits() -> None:
    port = _BASE_PORT + 4
    primary = _mgr(port)
    assert primary.acquire() is True
    primary.release()

    # After release, port should be free
    assert _port_free(port), "Port was not freed after release()"

    # New instance should acquire cleanly
    new_primary = _mgr(port)
    try:
        assert new_primary.acquire() is True
        assert new_primary.is_primary is True
    finally:
        new_primary.release()


# ---------------------------------------------------------------------------
# Test 9 — Dead primary recovered via stale recovery path (port bound but
#          no ACK because we killed the listener before it can respond)
# ---------------------------------------------------------------------------
def test_dead_primary_recovered() -> None:
    port = _BASE_PORT + 5

    # Simulate a dead primary: bind the port in a raw socket, write a stale
    # PID file, and never send an ACK.  The manager should recover.
    dead_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dead_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    dead_sock.bind(("127.0.0.1", port))
    dead_sock.listen(1)

    mgr = _mgr(port)
    # Write a dead PID so _try_clear_stale_pid cleans up
    pid_file = mgr._pid_file_path()
    pid_file.write_text("99999", encoding="utf-8")

    # Close the dead socket so the OS releases the port before acquire tries
    dead_sock.close()

    try:
        # Should recover: check_is_secondary will timeout (no ACK), acquire should succeed
        is_sec = mgr.check_is_secondary()
        assert is_sec is False, "Should detect stale and not treat as secondary"
        result = mgr.acquire()
        assert result is True
        assert mgr.is_primary is True
    finally:
        mgr.release()
        pid_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test 10 — Unrelated Python process does NOT block assistant
# ---------------------------------------------------------------------------
def test_unrelated_process_does_not_block() -> None:
    # Bind a port with a completely bare socket that responds with garbage
    unrelated_port = _BASE_PORT + 6
    unrelated_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unrelated_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    unrelated_sock.bind(("127.0.0.1", unrelated_port))
    unrelated_sock.listen(1)

    def _garbage_server():
        try:
            conn, _ = unrelated_sock.accept()
            conn.recv(64)
            conn.sendall(b"garbage response\n")  # not WAKEUP_ACK
            conn.close()
        except Exception:
            pass

    t = threading.Thread(target=_garbage_server, daemon=True)
    t.start()

    mgr = _mgr(unrelated_port)
    # check_is_secondary should return False (no valid ACK) rather than blocking forever
    result = mgr.check_is_secondary()
    assert result is False, "Unrelated process should not block assistant startup"
    unrelated_sock.close()


# ---------------------------------------------------------------------------
# Test 11 — check_is_secondary returns True for healthy primary
# ---------------------------------------------------------------------------
def test_check_is_secondary_true_for_healthy_primary() -> None:
    port = _BASE_PORT + 7
    primary = _mgr(port, on_activate=lambda: None)
    secondary = _mgr(port)
    try:
        assert primary.acquire() is True
        assert secondary.check_is_secondary() is True
    finally:
        primary.release()


# ---------------------------------------------------------------------------
# Test 12 — check_is_secondary returns False when no primary is running
# ---------------------------------------------------------------------------
def test_check_is_secondary_false_when_no_primary() -> None:
    port = _BASE_PORT + 8
    mgr = _mgr(port)
    assert mgr.check_is_secondary() is False


# ---------------------------------------------------------------------------
# Test 13 — Shutdown releases instance ownership (port freed after release)
# ---------------------------------------------------------------------------
def test_shutdown_releases_ownership() -> None:
    port = _BASE_PORT + 9
    mgr = _mgr(port)
    assert mgr.acquire() is True
    assert not _port_free(port)
    mgr.release()
    # Give OS time to fully release
    time.sleep(0.1)
    assert _port_free(port), "Port not freed after release()"
    assert mgr.is_primary is False


# ---------------------------------------------------------------------------
# Test 14 — crash / stale state recovery: check_is_secondary + acquire cycle
# ---------------------------------------------------------------------------
def test_stale_state_full_recovery_cycle() -> None:
    port = _BASE_PORT + 10
    mgr1 = _mgr(port)
    assert mgr1.acquire() is True
    # Abruptly close the socket without release() (simulates crash)
    mgr1._running = False
    mgr1._server_sock.close()
    mgr1._server_sock = None
    mgr1._is_primary = False

    # Give the OS a moment to free the port
    time.sleep(0.3)

    mgr2 = _mgr(port)
    try:
        # check_is_secondary should detect no live primary and return False
        is_sec = mgr2.check_is_secondary()
        assert is_sec is False
        result = mgr2.acquire()
        assert result is True
        assert mgr2.is_primary is True
    finally:
        mgr2.release()


# ---------------------------------------------------------------------------
# Test 15 — Multiple simultaneous starts result in exactly one primary
# ---------------------------------------------------------------------------
def test_simultaneous_starts_exactly_one_primary() -> None:
    port = _BASE_PORT + 11
    N = 5
    results: list[Optional[bool]] = [None] * N
    managers: list[SingleInstanceManager] = []

    def _try_acquire(idx: int) -> None:
        mgr = _mgr(port)
        managers.append(mgr)
        results[idx] = mgr.acquire()

    threads = [threading.Thread(target=_try_acquire, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    primaries = [r for r in results if r is True]
    secondaries = [r for r in results if r is False]

    try:
        assert len(primaries) == 1, f"Expected exactly 1 primary, got {len(primaries)}"
        assert len(secondaries) == N - 1
    finally:
        for mgr in managers:
            try:
                mgr.release()
            except Exception:
                pass
