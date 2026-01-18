#!/usr/bin/env python3
"""
WhisperX Automated Transcription Script
Transcribes audio files with language detection, alignment, and diarization.
"""

import json
import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
import argparse

import whisperx
import torch
from dotenv import load_dotenv

# Progress file for daemon communication
PROGRESS_FILE = Path.home() / ".whisperx" / "progress.json"
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from datetime import datetime, timedelta
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import print as rprint
from tqdm import tqdm
import contextlib

# Initialize rich console
console = Console()

# Configure logging to be quieter for rich output
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings/errors in log file
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transcription.log'),
    ]
)
logger = logging.getLogger(__name__)

# Suppress some verbose logging
logging.getLogger("whisperx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("torch").setLevel(logging.WARNING)

# Load environment variables
load_dotenv()

# Language-specific alignment models
ALIGNMENT_MODELS = {
    "sv": "KBLab/wav2vec2-base-voxpopuli-sv-swedish",
    "en": "WAV2VEC2_ASR_LARGE_LV60K_960H"
}

# Supported audio formats
SUPPORTED_FORMATS = {'.m4a', '.mp4', '.mov', '.wav', '.mp3', '.flac', '.ogg'}


def update_progress(stage: str, percent: float, detail: str = ""):
    """Update progress file for daemon/menu bar app communication."""
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        progress_data = {
            "stage": stage,
            "percent": round(percent, 1),
            "detail": detail,
            "timestamp": datetime.now().isoformat()
        }
        PROGRESS_FILE.write_text(json.dumps(progress_data))
    except OSError:
        pass  # Ignore errors writing progress


def clear_progress():
    """Clear progress file when transcription completes."""
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    except OSError:
        pass


def send_notification(title: str, message: str, sound: bool = True):
    """Send macOS notification using osascript."""
    try:
        sound_param = "with sound name \"Glass\"" if sound else ""
        script = f'''
        display notification "{message}" with title "{title}" {sound_param}
        '''
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to send notification: {e}")


def detect_language(audio_path: str, device: str = "cpu") -> Tuple[str, float]:
    """
    Detect the language of the audio file using WhisperX with improved multi-sample detection.
    Returns (language_code, confidence_score)
    """
    console.print("🔍 Starting enhanced language detection...")
    update_progress("detecting", 5, "Starting language detection")

    try:
        # Load audio
        console.print("📁 Loading audio file...")
        audio = whisperx.load_audio(audio_path)
        total_duration = len(audio) / 16000
        console.print(f"📊 Audio duration: {total_duration:.1f} seconds")
        
        # Load model for language detection
        console.print("🤖 Loading Whisper model for language detection...")
        model = whisperx.load_model("large-v3", device, compute_type="int8")
        
        detection_results = []
        sample_positions = []
        
        # Strategy: Test multiple samples for better accuracy
        if total_duration > 120:  # > 2 minutes
            # Test beginning (30-60s), middle (60s), and later section (60s)
            sample_positions = [
                (30, 90, "beginning"),      # 30s to 90s (skip very start)
                (total_duration // 2 - 30, total_duration // 2 + 30, "middle"),
                (total_duration - 90, total_duration - 30, "later")
            ]
        elif total_duration > 60:  # 1-2 minutes
            # Test beginning and middle
            sample_positions = [
                (10, 50, "beginning"),
                (total_duration // 2, min(total_duration - 10, total_duration // 2 + 40), "middle")
            ]
        else:  # < 1 minute
            # Use most of the available audio
            sample_positions = [(5, min(total_duration - 5, 55), "full")]
        
        console.print(f"🎯 Testing {len(sample_positions)} audio samples...")

        # Test each sample
        for idx, (start_time, end_time, position) in enumerate(sample_positions):
            update_progress("detecting", 8 + (idx * 4), f"Analyzing {position} sample")
            start_sample = int(start_time * 16000)
            end_sample = int(end_time * 16000)
            
            # Ensure we don't exceed audio bounds
            start_sample = max(0, min(start_sample, len(audio) - 1000))
            end_sample = min(len(audio), max(start_sample + 1000, end_sample))
            
            audio_sample = audio[start_sample:end_sample]
            sample_duration = len(audio_sample) / 16000
            
            console.print(f"  🎵 Analyzing {position} ({sample_duration:.1f}s sample)...")
            
            # Transcribe sample - let WhisperX handle language detection internally
            with contextlib.redirect_stdout(None), contextlib.redirect_stderr(None):
                result = model.transcribe(audio_sample)
            
            detected_lang = result.get("language", "unknown")
            
            # WhisperX doesn't reliably return language_probability in result dict
            # We'll infer confidence from the text quality and detection consistency
            segments = result.get("segments", [])
            text_length = sum(len(seg.get("text", "").strip()) for seg in segments)
            
            # Estimate confidence based on text length and detection consistency
            confidence_estimate = min(0.9, text_length / 50.0) if text_length > 0 else 0.1
            
            detection_results.append({
                'language': detected_lang,
                'confidence': confidence_estimate,
                'position': position,
                'text_length': text_length,
                'sample_duration': sample_duration,
                'text_sample': segments[0].get("text", "")[:100] if segments else ""
            })
            
            console.print(f"    → {detected_lang.upper()} (text length: {text_length})")
        
        # Analyze results to determine best language
        language_votes = {}
        total_confidence = 0
        
        for result in detection_results:
            lang = result['language']
            conf = result['confidence']
            
            if lang not in language_votes:
                language_votes[lang] = {'count': 0, 'total_confidence': 0, 'results': []}
            
            language_votes[lang]['count'] += 1
            language_votes[lang]['total_confidence'] += conf
            language_votes[lang]['results'].append(result)
            total_confidence += conf
        
        # Find the most likely language
        best_language = "en"  # default
        best_score = 0
        
        for lang, data in language_votes.items():
            # Score = vote count + average confidence
            avg_confidence = data['total_confidence'] / data['count']
            score = data['count'] * 2 + avg_confidence  # Weight vote count more heavily
            
            if score > best_score and lang != "unknown":
                best_language = lang
                best_score = score
        
        # Calculate overall confidence
        if best_language in language_votes:
            final_confidence = min(0.95, language_votes[best_language]['total_confidence'] / language_votes[best_language]['count'])
        else:
            final_confidence = 0.1
        
        # Display detailed results
        console.print("\n📋 Detection Results:")
        results_table = Table(show_header=True, header_style="bold blue")
        results_table.add_column("Sample", style="cyan")
        results_table.add_column("Language", style="green") 
        results_table.add_column("Text Length", style="yellow")
        results_table.add_column("Sample Text", style="dim")
        
        for result in detection_results:
            results_table.add_row(
                result['position'].title(),
                result['language'].upper(),
                str(result['text_length']),
                result['text_sample'][:50] + "..." if len(result['text_sample']) > 50 else result['text_sample']
            )
        
        console.print(results_table)
        
        # Display final result with appropriate flag and validation
        flag = "🇸🇪" if best_language == "sv" else "🇺🇸" if best_language == "en" else "🌐"
        console.print(f"\n✅ Final detection: {flag} {best_language.upper()} (confidence: {final_confidence:.1%})")
        
        # Show vote breakdown
        if len(language_votes) > 1:
            console.print("🗳️ Vote breakdown:")
            for lang, data in sorted(language_votes.items(), key=lambda x: x[1]['count'], reverse=True):
                console.print(f"  • {lang.upper()}: {data['count']} votes (avg conf: {data['total_confidence']/data['count']:.1%})")
        
        # Warnings and suggestions for low confidence
        if final_confidence < 0.4:
            console.print("[red]⚠️ Very low confidence - consider manual language specification[/red]")
            console.print("[dim]💡 Use -l sv to force Swedish or -l en to force English[/dim]")
        elif final_confidence < 0.6:
            console.print("[yellow]⚠️ Low confidence detection - results may vary[/yellow]")
            console.print("[dim]💡 Consider using manual language specification if results are incorrect[/dim]")
        
        # Special handling for common language detection issues
        if best_language == "pt" and any(r['language'] == 'sv' for r in detection_results):
            console.print("[yellow]🤔 Detected Portuguese, but Swedish was also found in samples[/yellow]")
            console.print("[yellow]💡 If this is Swedish audio, use: -l sv[/yellow]")
        
        # Check for sparse content (might miss actual language)
        total_text_length = sum(r['text_length'] for r in detection_results)
        if total_text_length < 20:  # Very little text found
            console.print("[yellow]⚠️ Very sparse speech content detected in samples[/yellow]")
            console.print("[yellow]💡 Language detection may be unreliable with sparse audio[/yellow]")
            console.print("[dim]   Consider using manual language specification: -l sv or -l en[/dim]")
        
        # Smart suggestion based on context
        if best_language == "en" and final_confidence < 0.5:
            console.print(f"[yellow]🎯 Low confidence English detection ({final_confidence:.1%})[/yellow]")
            console.print("[yellow]💡 If this is actually Swedish audio, try: -l sv[/yellow]")
        
        return best_language, final_confidence
        
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        console.print(f"[red]❌ Language detection failed: {e}[/red]")
        console.print("[yellow]🔄 Defaulting to English[/yellow]")
        return "en", 0.0


def calculate_eta(start_time: float, current_progress: float, total_progress: float = 100) -> str:
    """Calculate estimated time of arrival based on current progress."""
    if current_progress <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    rate = current_progress / elapsed  # progress per second
    remaining = total_progress - current_progress
    
    if rate <= 0:
        return "Calculating..."
    
    eta_seconds = remaining / rate
    if eta_seconds > 3600:  # More than 1 hour
        eta_str = f"{eta_seconds/3600:.1f}h"
    elif eta_seconds > 60:  # More than 1 minute
        eta_str = f"{eta_seconds/60:.1f}m"
    else:
        eta_str = f"{eta_seconds:.0f}s"
    
    return eta_str


def transcribe_audio(
    audio_path: str,
    output_dir: str,
    device: str = "cpu",
    language: Optional[str] = None,
    diarize: bool = True,
    output_formats: list = None
) -> Dict:
    """
    Transcribe audio file with WhisperX including alignment and diarization.
    """
    # Default to just TXT output, but allow override
    if output_formats is None:
        output_formats = ['txt']
    
    start_time = time.time()
    audio_name = Path(audio_path).stem

    # Display header
    console.print()
    console.rule(f"[bold blue]🎙️ Transcribing: {audio_name}")
    console.print()

    update_progress("loading", 0, f"Starting: {audio_name}")

    try:
        # Create enhanced progress tracking with ETA
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[dim]ETA: {task.fields[eta]}[/dim]"),
            console=console,
            transient=False
        ) as progress:
            
            main_task = progress.add_task("🚀 Starting transcription...", total=100, eta="Calculating...")
            
            # Load audio
            progress.update(main_task, description="📁 Loading audio file...", advance=10, eta="Calculating...")
            update_progress("loading", 10, "Loading audio file")
            audio = whisperx.load_audio(audio_path)
            
            # Get audio duration for better progress tracking
            duration = len(audio) / 16000  # WhisperX uses 16kHz
            console.print(f"📊 Audio duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
            
            # Track the actual processing pace
            progress_start_time = time.time()
            
            # Detect language if not provided
            if language is None:
                current_progress = progress.tasks[main_task].completed + 5
                eta = calculate_eta(progress_start_time, current_progress)
                progress.update(main_task, description="🔍 Detecting language...", advance=5, eta=eta)
                language, confidence = detect_language(audio_path, device)
                if confidence < 0.5:
                    console.print("[yellow]⚠️ Low confidence language detection[/yellow]")
            else:
                # Skip language detection, advance progress
                current_progress = progress.tasks[main_task].completed + 5
                eta = calculate_eta(progress_start_time, current_progress)
                progress.update(main_task, description=f"🌍 Using specified language: {language.upper()}...", advance=5, eta=eta)
            
            # Load transcription model
            current_progress = progress.tasks[main_task].completed + 15
            eta = calculate_eta(progress_start_time, current_progress)
            progress.update(main_task, description=f"🤖 Loading Whisper model ({language.upper()})...", advance=15, eta=eta)
            update_progress("loading", 25, f"Loading Whisper model ({language.upper()})")
            model = whisperx.load_model("large-v3", device, compute_type="float32", language=language)
            
            # Transcribe (pass language explicitly to avoid WhisperX auto-detection)
            current_progress = progress.tasks[main_task].completed + 10
            eta = calculate_eta(progress_start_time, current_progress)
            progress.update(main_task, description="🎯 Starting transcription...", advance=10, eta=eta)
            
        # Exit progress context for transcription to show WhisperX progress clearly
        console.print(f"[dim]⚡ Transcription phase - WhisperX batch progress:[/dim]")

        update_progress("transcribing", 30, "Transcribing audio...")
        transcribe_start = time.time()

        # Enable WhisperX built-in progress display (outside progress context)
        result = model.transcribe(
            audio,
            batch_size=8,
            language=language,
            print_progress=True,
            combined_progress=True
        )

        transcribe_elapsed = time.time() - transcribe_start
        actual_speed = duration / transcribe_elapsed if transcribe_elapsed > 0 else 0
        console.print(f"[green]✅ Transcription complete: {actual_speed:.1f}x realtime speed[/green]")
        console.print()
        update_progress("transcribing", 60, "Transcription complete")
        
        # Create output directories and initialize variables before progress context
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        base_filename = output_path / audio_name
        saved_files = []

        # Resume with new progress context for remaining steps
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[dim]ETA: {task.fields[eta]}[/dim]"),
            console=console,
            transient=False
        ) as progress:

            main_task = progress.add_task("🔗 Post-processing...", total=100, eta="Calculating...")
            progress.update(main_task, completed=0)  # Start fresh for remaining steps

            # Load alignment model
            alignment_model_name = ALIGNMENT_MODELS.get(language, "WAV2VEC2_ASR_LARGE_LV60K_960H")
            progress.update(main_task, description=f"🔗 Loading alignment model...", advance=5)
            update_progress("aligning", 65, "Loading alignment model")

            model_a, metadata = whisperx.load_align_model(
                language_code=language,
                device=device,
                model_name=alignment_model_name
            )

            # Align whisper output
            progress.update(main_task, description="⚡ Aligning transcription...", advance=10)
            update_progress("aligning", 70, "Aligning transcription")
            result = whisperx.align(
                result["segments"],
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False
            )
            progress.update(main_task, advance=15)

            # Save intermediate transcript before diarization
            if diarize:
                progress.update(main_task, description="💾 Saving intermediate transcript...", advance=2)
                raw_txt_file = f"{base_filename}_raw.txt"
                with open(raw_txt_file, "w", encoding="utf-8") as f:
                    for segment in result["segments"]:
                        f.write(f"{segment['text'].strip()}\n")
                saved_files.append(raw_txt_file)
                console.print(f"💾 Saved intermediate transcript: [dim]{raw_txt_file}[/dim]")
            
            # Diarization (speaker identification)
            if diarize:
                hf_token = os.getenv("HF_TOKEN")
                # Try diarization without token first, fallback with warning if needed
                try:
                    current_progress = progress.tasks[main_task].completed + 5
                    eta = calculate_eta(progress_start_time, current_progress)
                    progress.update(main_task, description="👥 Identifying speakers...", advance=5, eta=eta)
                    update_progress("diarization", 75, "Identifying speakers")

                    console.print(f"[dim]🕐 Speaker diarization estimate: {duration*0.2:.0f}-{duration*0.5:.0f}s[/dim]")
                    diarize_start = time.time()
                    if hf_token:
                        diarize_model = whisperx.diarize.DiarizationPipeline(
                            use_auth_token=hf_token, 
                            device=device
                        )
                    else:
                        # Try without token (works for some languages like Swedish)
                        diarize_model = whisperx.diarize.DiarizationPipeline(device=device)
                    
                    diarize_segments = diarize_model(audio)
                    result = whisperx.assign_word_speakers(diarize_segments, result)
                    
                    diarize_elapsed = time.time() - diarize_start
                    diarize_speed = duration / diarize_elapsed if diarize_elapsed > 0 else 0
                    console.print(f"[green]✅ Diarization complete: {diarize_speed:.1f}x realtime speed[/green]")
                    update_progress("diarization", 85, "Diarization complete")

                    current_progress = progress.tasks[main_task].completed + 10
                    eta = calculate_eta(progress_start_time, current_progress)
                    progress.update(main_task, advance=10, eta=eta)
                except Exception as e:
                    console.print(f"[yellow]⚠️ Speaker diarization failed: {str(e)[:100]}[/yellow]")
                    if not hf_token:
                        console.print("[yellow]💡 For better diarization support, set HF_TOKEN in .env[/yellow]")
                    progress.update(main_task, advance=15)
            else:
                progress.update(main_task, advance=15)

            # Create separate folders for different format types
            progress.update(main_task, description="📁 Setting up output formats...", advance=2)
            update_progress("saving", 90, "Saving output files")
            formats_dir = output_path / "formats"
            if any(fmt != 'txt' for fmt in output_formats):
                formats_dir.mkdir(parents=True, exist_ok=True)

            # Count segments for progress
            num_segments = len(result["segments"])
            console.print(f"📝 Found {num_segments} segments to save")

            # Save files in requested formats
            progress_per_format = 10 // len(output_formats)  # Distribute 10% across formats
            
            for fmt in output_formats:
                if fmt == 'txt':
                    progress.update(main_task, description="💾 Saving TXT format...", advance=progress_per_format)
                    txt_file = f"{base_filename}.txt"
                    with open(txt_file, "w", encoding="utf-8") as f:
                        for segment in result["segments"]:
                            speaker = f"[{segment.get('speaker', 'UNKNOWN')}] " if diarize else ""
                            f.write(f"{speaker}{segment['text'].strip()}\n")
                    saved_files.append(txt_file)
                
                elif fmt == 'json':
                    progress.update(main_task, description="💾 Saving JSON format...", advance=progress_per_format)
                    import json
                    json_file = formats_dir / f"{audio_name}.json"
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    saved_files.append(str(json_file))
                
                elif fmt == 'srt':
                    progress.update(main_task, description="💾 Saving SRT format...", advance=progress_per_format)
                    srt_file = formats_dir / f"{audio_name}.srt"
                    with open(srt_file, "w", encoding="utf-8") as f:
                        for i, segment in enumerate(result["segments"], 1):
                            start_time_srt = format_time_srt(segment["start"])
                            end_time_srt = format_time_srt(segment["end"])
                            speaker = f"[{segment.get('speaker', 'UNKNOWN')}] " if diarize else ""
                            f.write(f"{i}\n{start_time_srt} --> {end_time_srt}\n{speaker}{segment['text'].strip()}\n\n")
                    saved_files.append(str(srt_file))
                
                elif fmt == 'vtt':
                    progress.update(main_task, description="💾 Saving VTT format...", advance=progress_per_format)
                    vtt_file = formats_dir / f"{audio_name}.vtt"
                    with open(vtt_file, "w", encoding="utf-8") as f:
                        f.write("WEBVTT\n\n")
                        for segment in result["segments"]:
                            start_time_vtt = format_time_vtt(segment["start"])
                            end_time_vtt = format_time_vtt(segment["end"])
                            speaker = f"[{segment.get('speaker', 'UNKNOWN')}] " if diarize else ""
                            f.write(f"{start_time_vtt} --> {end_time_vtt}\n{speaker}{segment['text'].strip()}\n\n")
                    saved_files.append(str(vtt_file))
                
                elif fmt == 'tsv':
                    progress.update(main_task, description="💾 Saving TSV format...", advance=progress_per_format)
                    tsv_file = formats_dir / f"{audio_name}.tsv"
                    with open(tsv_file, "w", encoding="utf-8") as f:
                        f.write("start\tend\tspeaker\ttext\n")
                        for segment in result["segments"]:
                            speaker = segment.get('speaker', 'UNKNOWN') if diarize else 'SPEAKER_00'
                            f.write(f"{segment['start']:.3f}\t{segment['end']:.3f}\t{speaker}\t{segment['text'].strip()}\n")
                    saved_files.append(str(tsv_file))
            
            # Complete the progress
            progress.update(main_task, description="✅ Transcription complete!", completed=100)
            update_progress("complete", 100, "Transcription complete")
        
        processing_time = time.time() - start_time
        
        # Display success summary
        console.print()
        
        # Count speakers
        speakers = set()
        if diarize and result.get("segments"):
            speakers = {seg.get('speaker') for seg in result["segments"] if seg.get('speaker')}
            speakers.discard(None)
        
        # Create success table
        table = Table(title="🎉 Transcription Results", show_header=True, header_style="bold blue")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        flag = "🇸🇪" if language == "sv" else "🇺🇸" if language == "en" else "🌐"
        table.add_row("Language", f"{flag} {language.upper()}")
        table.add_row("Duration", f"{duration:.1f}s ({duration/60:.1f}min)")
        table.add_row("Processing Time", f"{processing_time:.1f}s")
        table.add_row("Speed Factor", f"{duration/processing_time:.1f}x")
        table.add_row("Segments", str(num_segments))
        if diarize and speakers:
            table.add_row("Speakers", f"{len(speakers)} identified")
        table.add_row("Output Files", ", ".join(fmt.upper() for fmt in output_formats))
        
        console.print(table)
        console.print(f"📁 Files saved to: [bold green]{output_path}[/bold green]")
        
        # Send success notification
        speakers_text = f" | {len(speakers)} speakers" if diarize and speakers else ""
        send_notification(
            f"Transcription Complete: {audio_name}",
            f"Language: {language.upper()} | Time: {processing_time:.1f}s{speakers_text}"
        )

        # Clear progress file on success
        clear_progress()

        return {
            "status": "success",
            "language": language,
            "processing_time": processing_time,
            "output_files": saved_files
        }
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Transcription failed for {audio_name}: {str(e)}"
        logger.error(error_msg)
        
        # Display error
        console.print()
        console.print(Panel(
            f"[red]❌ Transcription Failed[/red]\n\n"
            f"[yellow]File:[/yellow] {audio_name}\n"
            f"[yellow]Error:[/yellow] {str(e)}\n"
            f"[yellow]Time:[/yellow] {processing_time:.1f}s",
            title="🚨 Error",
            border_style="red"
        ))
        
        # Send error notification
        send_notification(
            f"Transcription Failed: {audio_name}",
            f"Error: {str(e)[:100]}...",
            sound=True
        )

        # Clear progress file on error
        clear_progress()

        return {
            "status": "error",
            "error": str(e),
            "processing_time": processing_time
        }


def format_time_srt(seconds: float) -> str:
    """Format time for SRT subtitle format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')


def format_time_vtt(seconds: float) -> str:
    """Format time for VTT subtitle format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def main():
    # Display startup banner
    console.print()
    console.print(Panel(
        "[bold blue]🎙️ WhisperX Automated Transcription System[/bold blue]\n"
        "[dim]High-quality speech-to-text with speaker diarization[/dim]",
        title="🚀 Welcome",
        border_style="blue"
    ))
    
    parser = argparse.ArgumentParser(
        description="Transcribe audio files with WhisperX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s recording.m4a                    # Basic transcription (TXT only)
  %(prog)s meeting.wav -o ./output         # Custom output directory
  %(prog)s interview.mp3 -l sv             # Force Swedish language
  %(prog)s call.m4a --no-diarize          # Skip speaker identification
  %(prog)s audio.m4a --formats txt,srt    # TXT + SRT formats
  %(prog)s video.mp4 --all-formats         # All formats (TXT,JSON,SRT,VTT,TSV)
        """
    )
    parser.add_argument("input", help="Input audio file path")
    parser.add_argument("-o", "--output", default="./transcripts", help="Output directory (default: ./transcripts)")
    parser.add_argument("-l", "--language", help="Language code (sv/en, auto-detected if not provided)")
    parser.add_argument("--no-diarize", action="store_true", help="Skip speaker diarization")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Processing device (default: cpu)")
    parser.add_argument("--formats", default="txt", help="Output formats (comma-separated): txt,json,srt,vtt,tsv (default: txt)")
    parser.add_argument("--all-formats", action="store_true", help="Output all formats (txt,json,srt,vtt,tsv)")
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]❌ Error: Input file not found: {args.input}[/red]")
        sys.exit(1)
    
    if input_path.suffix.lower() not in SUPPORTED_FORMATS:
        console.print(f"[red]❌ Error: Unsupported format: {input_path.suffix}[/red]")
        console.print(f"[yellow]Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}[/yellow]")
        sys.exit(1)
    
    # Check for GPU availability
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        console.print("[yellow]⚠️ CUDA not available, falling back to CPU[/yellow]")
        device = "cpu"
    
    # Parse output formats
    if args.all_formats:
        output_formats = ['txt', 'json', 'srt', 'vtt', 'tsv']
    else:
        # Parse comma-separated formats
        output_formats = [fmt.strip().lower() for fmt in args.formats.split(',')]
        # Validate formats
        valid_formats = {'txt', 'json', 'srt', 'vtt', 'tsv'}
        invalid_formats = set(output_formats) - valid_formats
        if invalid_formats:
            console.print(f"[red]❌ Invalid formats: {', '.join(invalid_formats)}[/red]")
            console.print(f"[yellow]Valid formats: {', '.join(sorted(valid_formats))}[/yellow]")
            sys.exit(1)
    
    # Display processing info
    console.print(f"📂 Input file: [green]{input_path}[/green]")
    console.print(f"📁 Output directory: [green]{args.output}[/green]")
    console.print(f"💻 Device: [blue]{device.upper()}[/blue]")
    console.print(f"👥 Speaker diarization: [blue]{'Enabled' if not args.no_diarize else 'Disabled'}[/blue]")
    console.print(f"📄 Output formats: [blue]{', '.join(fmt.upper() for fmt in output_formats)}[/blue]")
    if args.language:
        flag = "🇸🇪" if args.language == "sv" else "🇺🇸" if args.language == "en" else "🌐"
        console.print(f"🌍 Language: [blue]{flag} {args.language.upper()}[/blue]")
    else:
        console.print("🌍 Language: [blue]🔍 Auto-detect[/blue]")
    
    # Transcribe
    result = transcribe_audio(
        audio_path=str(input_path),
        output_dir=args.output,
        device=device,
        language=args.language,
        diarize=not args.no_diarize,
        output_formats=output_formats
    )
    
    if result["status"] == "success":
        console.print("\n[bold green]🎉 Success! Transcription completed successfully![/bold green]")
        sys.exit(0)
    else:
        console.print("\n[bold red]💥 Transcription failed![/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()