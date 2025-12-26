#!/usr/bin/env python3
"""
WhisperX Daemon State Management

Manages state files and Unix socket communication for the WhisperBar SwiftUI app.
"""

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class TranscriptionProgress:
    filename: str
    started_at: str
    duration_seconds: float
    progress_percent: float = 0.0
    stage: str = "loading"  # loading | detecting | transcribing | aligning | diarization | saving


@dataclass
class CompletedTranscript:
    id: str
    original_filename: str
    transcript_path: str
    completed_at: str
    duration_seconds: float
    language: str
    speaker_count: int
    success: bool
    error: Optional[str] = None


@dataclass
class DaemonState:
    status: str = "idle"  # idle | transcribing | error
    current: Optional[TranscriptionProgress] = None
    queue: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    error_message: Optional[str] = None


class StateManager:
    """Manages daemon state files and socket connections for SwiftUI app communication."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".whisperx"
        self.socket_path = self.state_dir / "whisperxd.sock"
        self.state_file = self.state_dir / "state.json"
        self.history_file = self.state_dir / "history.json"
        self.pid_file = self.state_dir / "daemon.pid"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state = DaemonState()
        self._history: list[CompletedTranscript] = []
        self._clients: list[asyncio.StreamWriter] = []
        self._server: Optional[asyncio.Server] = None

        self._load_history()
        self.set_idle()  # Write initial state file

    def _load_history(self):
        """Load transcript history from disk."""
        if self.history_file.exists():
            try:
                data = json.loads(self.history_file.read_text())
                self._history = [
                    CompletedTranscript(**t) for t in data.get("transcripts", [])
                ]
            except (json.JSONDecodeError, TypeError):
                self._history = []
        else:
            self._history = []

    def _save_history(self):
        """Save transcript history to disk."""
        data = {"transcripts": [asdict(t) for t in self._history[:50]]}
        self.history_file.write_text(json.dumps(data, indent=2, default=str))

    def _save_state(self):
        """Save current daemon state to disk."""
        state_dict = {
            "status": self._state.status,
            "current": asdict(self._state.current) if self._state.current else None,
            "queue": self._state.queue,
            "last_updated": datetime.now().isoformat(),
            "error_message": self._state.error_message,
        }
        self.state_file.write_text(json.dumps(state_dict, indent=2, default=str))

    async def broadcast(self, event: dict):
        """Send event to all connected SwiftUI clients."""
        if not self._clients:
            return

        msg = json.dumps(event, default=str) + "\n"
        msg_bytes = msg.encode()

        disconnected = []
        for client in self._clients:
            try:
                client.write(msg_bytes)
                await client.drain()
            except (ConnectionResetError, BrokenPipeError, OSError):
                disconnected.append(client)

        for client in disconnected:
            self._clients.remove(client)

    def write_pid(self):
        """Write daemon PID file."""
        self.pid_file.write_text(str(os.getpid()))

    def cleanup_pid(self):
        """Remove PID file on shutdown."""
        if self.pid_file.exists():
            self.pid_file.unlink()

    async def on_transcription_start(
        self, filename: str, duration_seconds: float
    ) -> None:
        """Called when a transcription begins."""
        self._state.status = "transcribing"
        self._state.current = TranscriptionProgress(
            filename=filename,
            started_at=datetime.now().isoformat(),
            duration_seconds=duration_seconds,
            progress_percent=0.0,
            stage="loading",
        )
        self._state.error_message = None
        self._save_state()

        await self.broadcast(
            {
                "event": "started",
                "filename": filename,
                "duration_seconds": duration_seconds,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def on_progress(self, percent: float, stage: str) -> None:
        """Called when transcription progress updates."""
        if self._state.current:
            self._state.current.progress_percent = percent
            self._state.current.stage = stage
            self._save_state()

        await self.broadcast(
            {
                "event": "progress",
                "percent": percent,
                "stage": stage,
            }
        )

    async def on_transcription_complete(
        self,
        filename: str,
        transcript_path: str,
        duration_seconds: float,
        language: str,
        speaker_count: int,
    ) -> None:
        """Called when a transcription completes successfully."""
        import uuid

        transcript = CompletedTranscript(
            id=str(uuid.uuid4())[:8],
            original_filename=filename,
            transcript_path=transcript_path,
            completed_at=datetime.now().isoformat(),
            duration_seconds=duration_seconds,
            language=language,
            speaker_count=speaker_count,
            success=True,
        )

        self._history.insert(0, transcript)
        self._history = self._history[:50]  # Keep last 50
        self._save_history()

        self._state.status = "idle"
        self._state.current = None
        self._save_state()

        await self.broadcast(
            {
                "event": "completed",
                "id": transcript.id,
                "filename": filename,
                "transcript_path": transcript_path,
                "duration_seconds": duration_seconds,
                "language": language,
                "speaker_count": speaker_count,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def on_transcription_failed(self, filename: str, error: str) -> None:
        """Called when a transcription fails."""
        import uuid

        transcript = CompletedTranscript(
            id=str(uuid.uuid4())[:8],
            original_filename=filename,
            transcript_path="",
            completed_at=datetime.now().isoformat(),
            duration_seconds=0,
            language="",
            speaker_count=0,
            success=False,
            error=error,
        )

        self._history.insert(0, transcript)
        self._history = self._history[:50]
        self._save_history()

        self._state.status = "error"
        self._state.current = None
        self._state.error_message = error
        self._save_state()

        await self.broadcast(
            {
                "event": "failed",
                "filename": filename,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def update_queue(self, queue: list[str]) -> None:
        """Update the pending file queue."""
        self._state.queue = queue
        self._save_state()

    def set_idle(self) -> None:
        """Set daemon to idle state."""
        self._state.status = "idle"
        self._state.current = None
        self._state.error_message = None
        self._save_state()

    def set_transcribing_sync(self, filename: str, duration_seconds: float) -> None:
        """Synchronously set transcription state (for use outside async context)."""
        self._state.status = "transcribing"
        self._state.current = TranscriptionProgress(
            filename=filename,
            started_at=datetime.now().isoformat(),
            duration_seconds=duration_seconds,
            progress_percent=0.0,
            stage="loading",
        )
        self._state.error_message = None
        self._save_state()

    def set_completed_sync(
        self,
        filename: str,
        transcript_path: str,
        duration_seconds: float,
        language: str,
        speaker_count: int,
    ) -> None:
        """Synchronously record completion (for use outside async context)."""
        import uuid

        transcript = CompletedTranscript(
            id=str(uuid.uuid4())[:8],
            original_filename=filename,
            transcript_path=transcript_path,
            completed_at=datetime.now().isoformat(),
            duration_seconds=duration_seconds,
            language=language,
            speaker_count=speaker_count,
            success=True,
        )

        self._history.insert(0, transcript)
        self._history = self._history[:50]
        self._save_history()
        self.set_idle()

    def set_failed_sync(self, filename: str, error: str) -> None:
        """Synchronously record failure (for use outside async context)."""
        import uuid

        transcript = CompletedTranscript(
            id=str(uuid.uuid4())[:8],
            original_filename=filename,
            transcript_path="",
            completed_at=datetime.now().isoformat(),
            duration_seconds=0,
            language="",
            speaker_count=0,
            success=False,
            error=error,
        )

        self._history.insert(0, transcript)
        self._history = self._history[:50]
        self._save_history()

        self._state.status = "error"
        self._state.current = None
        self._state.error_message = error
        self._save_state()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle a connected SwiftUI client."""
        self._clients.append(writer)

        # Send current state on connect
        state_dict = {
            "event": "state",
            "status": self._state.status,
            "current": asdict(self._state.current) if self._state.current else None,
            "queue": self._state.queue,
            "history": [asdict(t) for t in self._history[:10]],
        }
        writer.write((json.dumps(state_dict, default=str) + "\n").encode())
        await writer.drain()

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break

                try:
                    cmd = json.loads(data.decode())
                    if cmd.get("command") == "status":
                        state_dict = {
                            "event": "state",
                            "status": self._state.status,
                            "current": (
                                asdict(self._state.current)
                                if self._state.current
                                else None
                            ),
                            "queue": self._state.queue,
                        }
                        writer.write(
                            (json.dumps(state_dict, default=str) + "\n").encode()
                        )
                        await writer.drain()
                    elif cmd.get("command") == "history":
                        history_dict = {
                            "event": "history",
                            "transcripts": [asdict(t) for t in self._history[:20]],
                        }
                        writer.write(
                            (json.dumps(history_dict, default=str) + "\n").encode()
                        )
                        await writer.drain()
                except json.JSONDecodeError:
                    pass
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass

    async def start_server(self):
        """Start the Unix socket server for SwiftUI app connections."""
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.socket_path)
        )
        # Make socket readable by all users
        os.chmod(self.socket_path, 0o666)

    async def stop_server(self):
        """Stop the Unix socket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Close all client connections
        for client in self._clients:
            client.close()
            try:
                await client.wait_closed()
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass

        self._clients.clear()

        if self.socket_path.exists():
            self.socket_path.unlink()


# Global state manager instance (created in watcher.py)
state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get or create the global state manager."""
    global state_manager
    if state_manager is None:
        state_manager = StateManager()
    return state_manager
