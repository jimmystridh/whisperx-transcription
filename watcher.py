#!/usr/bin/env python3
"""
WhisperX File Watcher Daemon

Monitors the incoming folder for new audio files and automatically processes them.
Provides state management and Unix socket IPC for the WhisperBar SwiftUI menu bar app.
"""

import asyncio
import os
import signal
import sys
import time
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, Set
import argparse

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich import print as rprint
from datetime import datetime
import threading

from daemon_state import StateManager, get_state_manager

# Load environment variables
load_dotenv()

# Initialize rich console
console = Console()

# Configure logging to ~/.whisperx/daemon.log
LOG_DIR = Path.home() / ".whisperx"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "daemon.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)


def log_info(message: str):
    """Log info message and optionally print to console."""
    logger.info(message)


def log_error(message: str):
    """Log error message."""
    logger.error(message)

# Supported audio formats
SUPPORTED_FORMATS = {'.m4a', '.mp4', '.mov', '.wav', '.mp3', '.flac', '.ogg'}

# File processing cooldown (seconds)
PROCESSING_COOLDOWN = 2


class TranscriptionHandler(FileSystemEventHandler):
    """Handles file system events for automatic transcription."""

    def __init__(
        self,
        incoming_dir: str,
        transcripts_dir: str,
        archive_dir: str,
        script_path: str,
        state_manager: Optional[StateManager] = None,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.incoming_dir = Path(incoming_dir)
        self.transcripts_dir = Path(transcripts_dir)
        self.archive_dir = Path(archive_dir)
        self.script_path = Path(script_path)
        self.state_manager = state_manager
        self.event_loop = event_loop
        self.processing_files: Set[str] = set()
        self.processed_files: Set[str] = set()
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'start_time': datetime.now(),
            'current_file': None,
            'last_processed': None
        }
        self.lock = threading.Lock()

        # Create directories if they don't exist
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Display startup info
        console.print()
        console.print(Panel(
            f"[bold blue]📂 Monitoring:[/bold blue] {self.incoming_dir}\n"
            f"[bold green]📁 Transcripts:[/bold green] {self.transcripts_dir}\n"
            f"[bold yellow]📦 Archive:[/bold yellow] {self.archive_dir}",
            title="🎙️ WhisperX File Watcher Daemon",
            border_style="blue"
        ))

    def _emit_event(self, coro):
        """Run an async coroutine from sync context."""
        if self.state_manager and self.event_loop:
            asyncio.run_coroutine_threadsafe(coro, self.event_loop)
    
    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        self._process_file(file_path)
    
    def on_moved(self, event):
        """Handle file move events (e.g., when a file is moved into the folder)."""
        if event.is_directory:
            return
            
        file_path = Path(event.dest_path)
        self._process_file(file_path)
    
    def _get_audio_duration(self, file_path: Path) -> float:
        """Get audio duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
            return 0.0

    def _process_file(self, file_path: Path):
        """Process a single audio file."""
        try:
            # Check if it's a supported audio format
            if file_path.suffix.lower() not in SUPPORTED_FORMATS:
                return

            # Check if file is already being processed or was processed
            file_key = str(file_path)
            if file_key in self.processing_files or file_key in self.processed_files:
                return

            # Wait for file to be completely written (avoid processing partial files)
            console.print(f"🔍 Detected new file: [cyan]{file_path.name}[/cyan]")
            console.print("⏳ Waiting for file to be completely written...")
            self._wait_for_file_stable(file_path)

            if not file_path.exists():
                console.print(f"[yellow]⚠️ File disappeared during processing: {file_path}[/yellow]")
                return

            # Mark as processing
            self.processing_files.add(file_key)
            log_info(f"Starting transcription: {file_path.name}")

            with self.lock:
                self.stats['current_file'] = file_path.name

            # Get audio duration for state manager
            duration = self._get_audio_duration(file_path)
            if duration > 0:
                log_info(f"Audio duration: {duration:.1f}s")

            # Display processing start
            console.print()
            console.rule(f"[bold green]🎙️ Processing: {file_path.name}")

            # Send start notification
            self._send_notification(
                f"Starting Transcription: {file_path.stem}",
                f"Processing audio file...",
                sound=False
            )

            # Update state to transcribing
            if self.state_manager:
                self.state_manager.set_transcribing_sync(file_path.name, duration)

            # Run transcription
            start_time = time.time()
            success, result_info = self._run_transcription(file_path)
            processing_time = time.time() - start_time

            # Update stats
            with self.lock:
                self.stats['total_processed'] += 1
                if success:
                    self.stats['successful'] += 1
                    self.stats['last_processed'] = file_path.name
                else:
                    self.stats['failed'] += 1
                self.stats['current_file'] = None

            if success:
                log_info(f"Transcription completed: {file_path.name} ({processing_time:.1f}s)")

                # Check for .noarchive marker (file was added via menu bar picker)
                noarchive_marker = file_path.parent / f"{file_path.name}.noarchive"
                if noarchive_marker.exists():
                    # Delete instead of archive - file exists elsewhere
                    file_path.unlink()
                    noarchive_marker.unlink()
                    console.print(f"🗑️  Deleted (original exists elsewhere): [dim]{file_path.name}[/dim]")
                    log_info(f"Deleted (no archive): {file_path.name}")
                else:
                    # Move to archive
                    archive_path = self.archive_dir / file_path.name
                    counter = 1
                    while archive_path.exists():
                        name_parts = file_path.stem, counter, file_path.suffix
                        archive_path = self.archive_dir / f"{name_parts[0]}_{name_parts[1]}{name_parts[2]}"
                        counter += 1

                    shutil.move(str(file_path), str(archive_path))
                    console.print(f"📦 Moved to archive: [green]{archive_path.name}[/green]")
                    log_info(f"Archived to: {archive_path.name}")

                # Mark as processed
                self.processed_files.add(file_key)

                # Update state to completed
                transcript_path = self.transcripts_dir / f"{file_path.stem}.txt"
                if self.state_manager:
                    self.state_manager.set_completed_sync(
                        filename=file_path.name,
                        transcript_path=str(transcript_path),
                        duration_seconds=duration,
                        language=result_info.get("language", "unknown"),
                        speaker_count=result_info.get("speaker_count", 0),
                    )

                # Display success summary
                console.print(Panel(
                    f"[bold green]✅ Successfully processed[/bold green]\n"
                    f"[cyan]File:[/cyan] {file_path.name}\n"
                    f"[cyan]Time:[/cyan] {processing_time:.1f}s\n"
                    f"[cyan]Archive:[/cyan] {archive_path.name}",
                    title="🎉 Success",
                    border_style="green"
                ))
            else:
                # Update state to failed
                error_msg = result_info.get("error", "Unknown error")
                log_error(f"Transcription failed: {file_path.name} - {error_msg}")
                if self.state_manager:
                    self.state_manager.set_failed_sync(file_path.name, error_msg)

                console.print(Panel(
                    f"[bold red]❌ Processing failed[/bold red]\n"
                    f"[cyan]File:[/cyan] {file_path.name}\n"
                    f"[cyan]Time:[/cyan] {processing_time:.1f}s",
                    title="🚨 Error",
                    border_style="red"
                ))

            # Remove from processing set
            self.processing_files.discard(file_key)

        except Exception as e:
            console.print(f"[red]💥 Unexpected error processing {file_path.name}: {e}[/red]")
            log_error(f"Unexpected error processing {file_path.name}: {e}")
            if self.state_manager:
                self.state_manager.set_failed_sync(file_path.name, str(e))
            self.processing_files.discard(str(file_path))
    
    def _wait_for_file_stable(self, file_path: Path, max_wait: int = 30):
        """Wait for file to be completely written by checking size stability."""
        last_size = -1
        stable_count = 0
        
        for _ in range(max_wait):
            try:
                current_size = file_path.stat().st_size
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= 3:  # File size stable for 3 seconds
                        break
                else:
                    stable_count = 0
                
                last_size = current_size
                time.sleep(1)
                
            except (OSError, FileNotFoundError):
                time.sleep(1)
                continue
    
    def _run_transcription(self, file_path: Path) -> tuple[bool, dict]:
        """Run the transcription script on the file.

        Returns:
            Tuple of (success, result_info) where result_info contains
            language, speaker_count, and optionally error message.
        """
        result_info = {"language": "unknown", "speaker_count": 0}
        try:
            cmd = [
                sys.executable,
                str(self.script_path),
                str(file_path),
                "-o", str(self.transcripts_dir),
                "--all-formats"
            ]

            # Check if filename contains "-nospeakers" to skip diarization
            if "-nospeakers" in file_path.stem.lower():
                cmd.append("--no-diarize")
                console.print("👤 Detected '-nospeakers' in filename - skipping speaker diarization")

            console.print(f"🚀 Running: [dim]{' '.join(cmd)}[/dim]")
            console.print()  # Add some spacing before transcribe.py output

            # Run transcription with timeout (let transcribe.py handle all progress display)
            result = subprocess.run(
                cmd,
                timeout=7200,  # 2 hour timeout for large files
                capture_output=False,
            )

            if result.returncode == 0:
                # Try to parse result info from the JSON output if available
                json_path = self.transcripts_dir / "formats" / f"{file_path.stem}.json"
                if json_path.exists():
                    try:
                        import json
                        with open(json_path) as f:
                            data = json.load(f)
                        result_info["language"] = data.get("language", "unknown")
                        # Count unique speakers
                        speakers = set()
                        for seg in data.get("segments", []):
                            if seg.get("speaker"):
                                speakers.add(seg["speaker"])
                        result_info["speaker_count"] = len(speakers)
                    except (json.JSONDecodeError, OSError):
                        pass
                return True, result_info
            else:
                console.print(f"[red]❌ Transcription process failed with exit code {result.returncode}[/red]")

                # Send error notification
                self._send_notification(
                    f"Transcription Failed: {file_path.stem}",
                    f"Process failed with exit code {result.returncode}",
                    sound=True
                )
                result_info["error"] = f"Exit code {result.returncode}"
                return False, result_info

        except subprocess.TimeoutExpired:
            logger.error(f"Transcription timeout: {file_path.name}")
            self._send_notification(
                f"Transcription Timeout: {file_path.stem}",
                f"Processing took too long",
                sound=True
            )
            result_info["error"] = "Timeout after 2 hours"
            return False, result_info

        except Exception as e:
            logger.error(f"Error running transcription: {e}")
            result_info["error"] = str(e)
            return False, result_info
    
    def _send_notification(self, title: str, message: str, sound: bool = True):
        """Send macOS notification."""
        try:
            sound_param = "with sound name \"Glass\"" if sound else ""
            script = f'''
            display notification "{message}" with title "{title}" {sound_param}
            '''
            subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to send notification: {e}")
    
    def get_stats_table(self) -> Table:
        """Create a stats table for live display."""
        with self.lock:
            stats = self.stats.copy()
        
        # Calculate uptime
        uptime = datetime.now() - stats['start_time']
        uptime_str = f"{uptime.seconds//3600}h {(uptime.seconds//60)%60}m {uptime.seconds%60}s"
        
        # Calculate success rate
        success_rate = (stats['successful'] / stats['total_processed'] * 100) if stats['total_processed'] > 0 else 0
        
        table = Table(title="📊 Watcher Statistics", show_header=True, header_style="bold blue")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("🕐 Uptime", uptime_str)
        table.add_row("📁 Total Processed", str(stats['total_processed']))
        table.add_row("✅ Successful", str(stats['successful']))
        table.add_row("❌ Failed", str(stats['failed']))
        table.add_row("📈 Success Rate", f"{success_rate:.1f}%")
        
        if stats['current_file']:
            table.add_row("🎙️ Currently Processing", stats['current_file'])
        if stats['last_processed']:
            table.add_row("📝 Last Completed", stats['last_processed'])
        
        return table

    def process_existing_files(self):
        """Process any existing files in the incoming directory."""
        console.print("🔍 Checking for existing files...")
        
        if not self.incoming_dir.exists():
            console.print(f"[yellow]⚠️ Incoming directory does not exist: {self.incoming_dir}[/yellow]")
            return
        
        existing_files = [f for f in self.incoming_dir.iterdir() 
                         if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS]
        
        if existing_files:
            console.print(f"📂 Found {len(existing_files)} existing files to process")
            for file_path in existing_files:
                console.print(f"  • [cyan]{file_path.name}[/cyan]")
                self._process_file(file_path)
        else:
            console.print("✨ No existing files found - ready for new uploads!")


async def run_daemon(args):
    """Run the daemon with async event loop for socket server."""
    # Resolve paths
    incoming_dir = Path(args.incoming).resolve()
    transcripts_dir = Path(args.transcripts).resolve()
    archive_dir = Path(args.archive).resolve()
    script_path = Path(args.script).resolve()

    # Validate script exists
    if not script_path.exists():
        console.print(f"[red]❌ Error: Transcription script not found: {script_path}[/red]")
        sys.exit(1)

    # Create incoming directory if it doesn't exist
    incoming_dir.mkdir(parents=True, exist_ok=True)

    # Initialize state manager
    state_manager = get_state_manager()
    state_manager.write_pid()
    log_info("Daemon starting...")
    log_info(f"PID: {os.getpid()}")

    # Start socket server for SwiftUI app
    await state_manager.start_server()
    console.print(f"[dim]🔌 Socket server listening at: {state_manager.socket_path}[/dim]")
    log_info(f"Socket server started: {state_manager.socket_path}")

    # Display configuration
    config_table = Table(title="⚙️ Configuration", show_header=True, header_style="bold blue")
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="green")

    config_table.add_row("📂 Watch Directory", str(incoming_dir))
    config_table.add_row("📁 Transcripts", str(transcripts_dir))
    config_table.add_row("📦 Archive", str(archive_dir))
    config_table.add_row("🐍 Script", str(script_path))
    config_table.add_row("🔌 Socket", str(state_manager.socket_path))
    config_table.add_row("🎵 Supported Formats", ", ".join(sorted(SUPPORTED_FORMATS)))

    console.print(config_table)

    # Get current event loop
    loop = asyncio.get_running_loop()

    # Create handler with state manager
    handler = TranscriptionHandler(
        str(incoming_dir),
        str(transcripts_dir),
        str(archive_dir),
        str(script_path),
        state_manager=state_manager,
        event_loop=loop,
    )

    # Always process existing files on startup
    handler.process_existing_files()

    if args.once:
        console.print()
        console.print("[bold green]✅ One-time processing complete![/bold green]")
        await state_manager.stop_server()
        state_manager.cleanup_pid()
        return

    # Set up file watcher
    observer = Observer()
    observer.schedule(handler, str(incoming_dir), recursive=False)
    observer.start()

    console.print()
    console.print(Panel(
        f"[bold green]👀 Watching:[/bold green] {incoming_dir}\n"
        f"[yellow]Drop audio files to start transcription![/yellow]\n"
        f"[dim]WhisperBar app can connect for status updates[/dim]\n"
        f"[dim]Press Ctrl+C to stop[/dim]",
        title="🟢 Daemon Active",
        border_style="green"
    ))

    # Set up signal handlers
    stop_event = asyncio.Event()

    def signal_handler():
        console.print()
        console.print("[yellow]🛑 Stopping daemon...[/yellow]")
        log_info("Daemon stopping (signal received)")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        # Run until stop signal
        await stop_event.wait()
    finally:
        observer.stop()
        observer.join()
        await state_manager.stop_server()
        state_manager.cleanup_pid()

        # Display final stats
        console.print()
        console.print(handler.get_stats_table())
        console.print("[bold blue]👋 Daemon stopped successfully![/bold blue]")
        log_info(f"Daemon stopped. Stats: {handler.stats['total_processed']} processed, {handler.stats['successful']} successful, {handler.stats['failed']} failed")


def main():
    # Display startup banner
    console.print()
    console.print(Panel(
        "[bold blue]👀 WhisperX Daemon[/bold blue]\n"
        "[dim]Automatic transcription with menu bar app support[/dim]",
        title="🚀 Starting",
        border_style="blue"
    ))

    parser = argparse.ArgumentParser(
        description="WhisperX daemon - watches for audio files and provides status to menu bar app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Watch with default settings
  %(prog)s --incoming /path/to/audio    # Custom input directory
  %(prog)s --process-existing          # Process existing files first
  %(prog)s --once                      # One-time batch processing
        """
    )
    parser.add_argument(
        "--incoming",
        default="./incoming",
        help="Directory to watch for new files (default: ./incoming)"
    )
    parser.add_argument(
        "--transcripts",
        default="./transcripts",
        help="Directory for transcript output (default: ./transcripts)"
    )
    parser.add_argument(
        "--archive",
        default="./recording_archive",
        help="Directory to move processed files (default: ./recording_archive)"
    )
    parser.add_argument(
        "--script",
        default="./transcribe.py",
        help="Path to transcription script (default: ./transcribe.py)"
    )
    parser.add_argument(
        "--process-existing",
        action="store_true",
        help="Process existing files on startup"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process existing files and exit (don't watch)"
    )

    args = parser.parse_args()

    # Run async daemon
    asyncio.run(run_daemon(args))


if __name__ == "__main__":
    main()