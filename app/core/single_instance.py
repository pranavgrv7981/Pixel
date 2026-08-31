"""Single-instance process lock and inter-process activation coordinator.

Architecture
============
A TCP server on a loopback port (default 49811) serves as the instance lock:
  * Primary   — binds the port, writes a PID file, listens for WAKEUP.
  * Secondary — cannot bind; sends WAKEUP, waits for WAKEUP_ACK, exits.

Stale-instance recovery
-----------------------
If the port is already bound but the owning process is dead or unresponsive
(no ACK within the timeout), the secondary treats the lock as stale, reclaims
ownership and becomes the new primary.

Startup ordering
----------------
``check_is_secondary()`` performs only the port-probe and optional liveness
check WITHOUT starting a listener thread.  It is designed to be called before
expensive backend initialisation so secondary instances exit immediately.

``acquire()`` is called later by the primary to start the listener thread.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("core.single_instance")

DEFAULT_SINGLE_INSTANCE_PORT: int = 49811
_PID_FILE_NAME: str = "assistant_instance.pid"

# Protocol tokens
_MSG_WAKEUP = b"WAKEUP\n"
_MSG_ACK = b"WAKEUP_ACK\n"

# Timeouts
_WAKEUP_CONNECT_TIMEOUT = 2.0   # seconds to connect to primary
_WAKEUP_ACK_TIMEOUT = 3.0       # seconds to wait for ACK from primary
_STALE_PROBE_TIMEOUT = 1.0      # quick connect to decide if primary is alive


class SingleInstanceManager:
    """Ensures only a single assistant process runs at once.

    Typical GUI startup usage
    -------------------------
    Before any heavy initialisation::

        mgr = SingleInstanceManager(settings=cfg)
        if not mgr.check_is_secondary():
            # We are (or can become) primary — proceed with full startup
            ...
            mgr.acquire()   # starts listener, writes PID
        else:
            sys.exit(0)

    Or simply call ``acquire()`` directly (it handles liveness internally)::

        mgr = SingleInstanceManager(settings=cfg)
        if not mgr.acquire():
            sys.exit(0)   # secondary; primary already woken
    """

    def __init__(
        self,
        port: int = DEFAULT_SINGLE_INSTANCE_PORT,
        on_activate: Optional[Callable[[], None]] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.port = port
        self.on_activate = on_activate
        self._settings = settings or get_settings()
        self._server_sock: Optional[socket.socket] = None
        self._is_primary: bool = False
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_primary(self) -> bool:
        """True if this process holds the single-instance lock."""
        return self._is_primary

    # Legacy alias for old code still using self.settings
    @property
    def settings(self) -> Settings:
        return self._settings

    def check_is_secondary(self) -> bool:
        """Lightweight early check: returns True if another *healthy* primary is running.

        Sends WAKEUP and waits for WAKEUP_ACK.  If no ACK is received the
        existing lock is considered stale and False is returned so the caller
        can proceed to ``acquire()``.

        Does NOT start a listener thread.  Safe to call before Qt is
        initialised and before any backend subsystems are running.
        """
        if not self._settings.single_instance_enabled:
            return False

        if not self._port_is_bound():
            return False

        # Port is bound — check if the holder is actually alive and responsive
        logger.info(
            "Port %d is already bound. Probing primary instance liveness...",
            self.port,
        )
        alive = self._send_wakeup_with_ack()
        if alive:
            logger.info(
                "Primary instance is alive and acknowledged wakeup. "
                "This process will exit."
            )
            return True

        # Stale lock — try to remove PID file so acquire() can bind cleanly
        logger.warning(
            "Port %d was bound but primary did not respond (stale lock). "
            "Attempting stale-state recovery.",
            self.port,
        )
        self._try_clear_stale_pid()
        return False  # caller should proceed to acquire()

    def acquire(self) -> bool:
        """Attempt to acquire the single-instance lock and start the listener.

        Returns True  — this process is now primary.
        Returns False — a healthy primary exists; wakeup was sent; caller should exit.
        """
        if not self._settings.single_instance_enabled:
            self._is_primary = True
            return True

        # --- Try to bind the server socket ---
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind(("127.0.0.1", self.port))
            sock.listen(5)
        except (OSError, socket.error):
            sock.close()
            # Port already held — is the holder alive?
            logger.info(
                "Port %d already in use. Probing primary liveness...", self.port
            )
            alive = self._send_wakeup_with_ack()
            if alive:
                logger.info(
                    "Another assistant instance is already active. Forwarding wakeup signal..."
                )
                logger.info("Sent WAKEUP signal to primary instance.")
                self._is_primary = False
                return False

            # Stale — attempt to clear and re-bind
            logger.warning("Primary did not respond. Attempting stale recovery...")
            self._try_clear_stale_pid()
            time.sleep(0.5)  # brief wait for OS to release the port
            sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            try:
                sock2.bind(("127.0.0.1", self.port))
                sock2.listen(5)
                sock = sock2
                logger.info(
                    "Stale instance recovered. This process is now primary on port %d.",
                    self.port,
                )
            except (OSError, socket.error) as err:
                sock2.close()
                logger.error(
                    "Cannot reclaim port %d after stale recovery: %s.",
                    self.port,
                    err,
                )
                self._is_primary = False
                return False

        # We own the socket — become primary
        self._server_sock = sock
        self._is_primary = True
        self._running = True
        self._write_pid_file()

        self._thread = threading.Thread(
            target=self._listen_loop,
            name="SingleInstanceListener",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Acquired single-instance lock on 127.0.0.1:%d (PID %d).",
            self.port,
            os.getpid(),
        )
        return True

    def release(self) -> None:
        """Release the single-instance lock and close the listening socket."""
        self._running = False
        if self._server_sock:
            try:
                # Unblock accept() with a dummy connection
                dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                dummy.settimeout(0.5)
                dummy.connect(("127.0.0.1", self.port))
                dummy.close()
            except Exception:
                pass
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        self._is_primary = False
        self._remove_pid_file()
        logger.debug("Released single-instance lock.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _port_is_bound(self) -> bool:
        """Return True if the loopback port is currently bound by any process."""
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(_STALE_PROBE_TIMEOUT)
        try:
            probe.connect(("127.0.0.1", self.port))
            probe.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False
        finally:
            try:
                probe.close()
            except Exception:
                pass

    def _send_wakeup_with_ack(self) -> bool:
        """Send WAKEUP to primary and wait for WAKEUP_ACK.

        Returns True if primary acknowledged (healthy); False otherwise.
        """
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(_WAKEUP_CONNECT_TIMEOUT)
            client.connect(("127.0.0.1", self.port))
            client.settimeout(_WAKEUP_ACK_TIMEOUT)
            client.sendall(_MSG_WAKEUP)
            data = client.recv(64)
            client.close()
            if _MSG_ACK.strip() in data:
                logger.info("Received WAKEUP_ACK from primary instance.")
                return True
            logger.warning(
                "Unexpected response from primary: %r (expected ACK).", data
            )
            return False
        except socket.timeout:
            logger.warning(
                "Timed out waiting for WAKEUP_ACK — primary may be unresponsive."
            )
            return False
        except Exception as err:
            logger.warning("Could not reach primary instance: %s", err)
            return False

    def _listen_loop(self) -> None:
        """Background listener accepting activation requests from secondary instances."""
        while self._running and self._server_sock:
            try:
                conn, addr = self._server_sock.accept()
                conn.settimeout(2.0)
                try:
                    data = conn.recv(1024)
                    if b"WAKEUP" in data:
                        logger.info(
                            "Received wakeup notification from secondary instance at %s.",
                            addr,
                        )
                        # Send ACK before invoking callback so secondary exits cleanly
                        try:
                            conn.sendall(_MSG_ACK)
                        except Exception:
                            pass
                        conn.close()
                        if callable(self.on_activate):
                            try:
                                self.on_activate()
                            except Exception as err:
                                logger.warning(
                                    "Error in on_activate callback: %s", err
                                )
                    else:
                        conn.close()
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                if not self._running:
                    break

    # ------------------------------------------------------------------
    # PID file helpers
    # ------------------------------------------------------------------

    def _pid_file_path(self) -> Path:
        try:
            data_dir = self._settings.get_resolved_data_dir()
        except Exception:
            data_dir = Path.home() / ".local_assistant"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / _PID_FILE_NAME

    def _write_pid_file(self) -> None:
        try:
            self._pid_file_path().write_text(str(os.getpid()), encoding="utf-8")
        except Exception as err:
            logger.debug("Could not write PID file: %s", err)

    def _remove_pid_file(self) -> None:
        try:
            pid_path = self._pid_file_path()
            if pid_path.exists():
                pid_path.unlink()
        except Exception as err:
            logger.debug("Could not remove PID file: %s", err)

    def _try_clear_stale_pid(self) -> None:
        """Remove the PID file if it refers to a dead process."""
        try:
            pid_path = self._pid_file_path()
            if not pid_path.exists():
                return
            pid_text = pid_path.read_text(encoding="utf-8").strip()
            pid = int(pid_text)
            if pid == os.getpid():
                return  # own PID — don't remove

            # Check if process is alive.
            # On Windows os.kill(pid, 0) raises PermissionError for terminated-but-
            # not-yet-reaped processes, giving a false "alive" result.  Use psutil
            # when available for an accurate check; fall back to os.kill otherwise.
            is_alive = self._pid_is_alive(pid)
            if is_alive:
                logger.debug("PID %d from PID file is still alive.", pid)
            else:
                logger.info(
                    "PID %d from PID file is dead. Removing stale PID file.", pid
                )
                pid_path.unlink(missing_ok=True)
        except Exception as err:
            logger.debug("PID file check failed: %s", err)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        """Return True if the process with the given PID is alive.

        Uses psutil.pid_exists() when available (accurate on Windows).
        Falls back to os.kill(pid, 0) on POSIX.
        """
        try:
            import psutil
            if not psutil.pid_exists(pid):
                return False
            # psutil.pid_exists() can return True for zombie processes on some
            # platforms — additionally check the process status when possible.
            try:
                proc = psutil.Process(pid)
                status = proc.status()
                return status not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        except ImportError:
            pass

        # POSIX fallback
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # On POSIX PermissionError means the process exists (we lack signal perms)
            # On Windows it means the process is gone — can't distinguish without psutil
            import sys
            if sys.platform == "win32":
                return False  # Windows: terminated process
            return True  # POSIX: process exists but we lack permissions
