#!/usr/bin/env python3
"""
Test script to analyze language detection issues
"""

import sys
import time
from pathlib import Path
import whisperx
import torch
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def test_language_detection_methods(audio_path: str, sample_durations=[10, 30, 60]):
    """Test different language detection methods and durations."""
    
    console.print(Panel(
        f"[bold blue]🔍 Language Detection Analysis[/bold blue]\n"
        f"[dim]Testing file: {Path(audio_path).name}[/dim]",
        title="🧪 Testing",
        border_style="blue"
    ))
    
    try:
        # Load audio
        console.print("📁 Loading audio file...")
        audio = whisperx.load_audio(audio_path)
        total_duration = len(audio) / 16000
        console.print(f"📊 Total duration: {total_duration:.1f} seconds")
        
        # Load model
        console.print("🤖 Loading Whisper model...")
        device = "cpu"
        model = whisperx.load_model("large-v3", device, compute_type="int8")
        
        # Test different sample durations
        results = []
        for duration in sample_durations:
            console.print(f"\n🎯 Testing with {duration}s sample...")
            
            # Get sample (in samples, not seconds)
            sample_length = min(duration * 16000, len(audio))
            audio_sample = audio[:sample_length]
            
            # Test from beginning
            start_time = time.time()
            result_start = model.transcribe(audio_sample)
            detection_time = time.time() - start_time
            
            # Test from middle
            middle_start = max(0, len(audio) // 2 - sample_length // 2)
            middle_end = min(len(audio), middle_start + sample_length)
            audio_middle = audio[middle_start:middle_end]
            
            result_middle = model.transcribe(audio_middle)
            
            results.append({
                'duration': duration,
                'start_lang': result_start.get("language", "unknown"),
                'start_conf': result_start.get("language_probability", 0.0),
                'start_text': result_start.get("segments", [{}])[0].get("text", "")[:100] if result_start.get("segments") else "",
                'middle_lang': result_middle.get("language", "unknown"),
                'middle_conf': result_middle.get("language_probability", 0.0),
                'middle_text': result_middle.get("segments", [{}])[0].get("text", "")[:100] if result_middle.get("segments") else "",
                'detection_time': detection_time
            })
            
            console.print(f"  🟢 Beginning: {result_start.get('language', 'unknown')} "
                         f"(conf: {result_start.get('language_probability', 0.0):.1%})")
            console.print(f"  🟡 Middle: {result_middle.get('language', 'unknown')} "
                         f"(conf: {result_middle.get('language_probability', 0.0):.1%})")
        
        # Display results table
        console.print("\n📋 Detection Results Summary:")
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Duration", style="cyan")
        table.add_column("Start Lang", style="green")
        table.add_column("Start Conf", style="green")
        table.add_column("Middle Lang", style="yellow")
        table.add_column("Middle Conf", style="yellow")
        table.add_column("Time", style="dim")
        
        for r in results:
            table.add_row(
                f"{r['duration']}s",
                f"{r['start_lang'].upper()}",
                f"{r['start_conf']:.1%}",
                f"{r['middle_lang'].upper()}",
                f"{r['middle_conf']:.1%}",
                f"{r['detection_time']:.1f}s"
            )
        
        console.print(table)
        
        # Show sample transcripts
        console.print("\n📝 Sample Transcripts:")
        for r in results:
            if r['start_text'].strip():
                console.print(f"[cyan]{r['duration']}s start:[/cyan] {r['start_text']}")
            if r['middle_text'].strip():
                console.print(f"[yellow]{r['duration']}s middle:[/yellow] {r['middle_text']}")
        
        return results
        
    except Exception as e:
        console.print(f"[red]❌ Error during testing: {e}[/red]")
        return []

def main():
    if len(sys.argv) != 2:
        console.print("[red]Usage: python test_language_detection.py <audio_file>[/red]")
        sys.exit(1)
    
    audio_path = sys.argv[1]
    if not Path(audio_path).exists():
        console.print(f"[red]File not found: {audio_path}[/red]")
        sys.exit(1)
    
    # Test different durations
    results = test_language_detection_methods(audio_path, [10, 30, 60])
    
    if results:
        console.print("\n💡 Recommendations:")
        
        # Analyze results
        swedish_detections = sum(1 for r in results if r['start_lang'] == 'sv' or r['middle_lang'] == 'sv')
        english_detections = sum(1 for r in results if r['start_lang'] == 'en' or r['middle_lang'] == 'en')
        
        if swedish_detections > english_detections:
            console.print("[green]✅ Swedish appears to be correctly detected in some samples[/green]")
            console.print("[yellow]💡 Consider using longer samples or middle portions for detection[/yellow]")
        elif swedish_detections > 0:
            console.print("[yellow]⚠️ Mixed results - Swedish detected sometimes[/yellow]")
            console.print("[yellow]💡 May need multiple sample points for better accuracy[/yellow]")
        else:
            console.print("[red]❌ Swedish not detected in any samples[/red]")
            console.print("[yellow]💡 Consider manual language override or different detection strategy[/yellow]")
        
        # Check confidence levels
        high_conf_results = [r for r in results if max(r['start_conf'], r['middle_conf']) > 0.8]
        if high_conf_results:
            console.print(f"[green]📈 High confidence detections found ({len(high_conf_results)} samples)[/green]")
        else:
            console.print("[yellow]📉 All detections have low confidence - consider multiple samples[/yellow]")

if __name__ == "__main__":
    main()