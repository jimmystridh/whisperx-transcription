#!/usr/bin/env python3
"""
Quick language detection test - compares auto-detection vs forced Swedish
"""

import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def run_transcription_test(audio_path: str, language: str = None) -> dict:
    """Run transcription and return basic info."""
    try:
        cmd = [
            sys.executable,
            "transcribe.py",
            audio_path,
            "--no-diarize",
            "-o", "./test_output"
        ]
        
        if language:
            cmd.extend(["-l", language])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        # Try to read the output file
        audio_name = Path(audio_path).stem
        output_file = Path("./test_output") / f"{audio_name}.txt"
        
        transcribed_text = ""
        if output_file.exists():
            with open(output_file, 'r', encoding='utf-8') as f:
                transcribed_text = f.read().strip()
        
        return {
            'success': result.returncode == 0,
            'text': transcribed_text,
            'language': language or "auto-detect",
            'stdout': result.stdout
        }
    
    except Exception as e:
        return {
            'success': False,
            'text': f"Error: {e}",
            'language': language or "auto-detect",
            'stdout': ""
        }

def main():
    if len(sys.argv) != 2:
        console.print("[red]Usage: python quick_language_test.py <audio_file>[/red]")
        sys.exit(1)
    
    audio_path = sys.argv[1]
    if not Path(audio_path).exists():
        console.print(f"[red]File not found: {audio_path}[/red]")
        sys.exit(1)
    
    console.print(Panel(
        f"[bold blue]🧪 Quick Language Detection Test[/bold blue]\n"
        f"[dim]Testing: {Path(audio_path).name}[/dim]",
        title="🔍 Language Comparison",
        border_style="blue"
    ))
    
    # Test auto-detection
    console.print("🔍 Testing auto-detection...")
    auto_result = run_transcription_test(audio_path)
    
    # Test forced Swedish
    console.print("🇸🇪 Testing forced Swedish...")
    swedish_result = run_transcription_test(audio_path, "sv")
    
    # Test forced English
    console.print("🇺🇸 Testing forced English...")
    english_result = run_transcription_test(audio_path, "en")
    
    # Display results
    console.print("\n📊 Results Comparison:")
    
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Mode", style="cyan")
    table.add_column("Success", style="green")
    table.add_column("Transcribed Text", style="yellow")
    
    results = [
        ("Auto-detect", auto_result),
        ("Swedish (sv)", swedish_result),
        ("English (en)", english_result)
    ]
    
    for mode, result in results:
        success_icon = "✅" if result['success'] else "❌"
        text_preview = result['text'][:100] + "..." if len(result['text']) > 100 else result['text']
        table.add_row(mode, success_icon, text_preview)
    
    console.print(table)
    
    # Analysis
    console.print("\n💡 Analysis:")
    
    if auto_result['text'] and swedish_result['text']:
        if auto_result['text'].strip() == swedish_result['text'].strip():
            console.print("[green]✅ Auto-detection correctly identified Swedish![/green]")
        elif len(swedish_result['text']) > len(auto_result['text']):
            console.print("[yellow]⚠️ Swedish transcription is longer - may be more accurate[/yellow]")
            console.print("[yellow]💡 Consider using -l sv for Swedish audio[/yellow]")
        else:
            console.print("[blue]ℹ️ Different results between auto and Swedish transcription[/blue]")
    
    # Show recommendation
    text_lengths = {
        'auto': len(auto_result['text']) if auto_result['text'] else 0,
        'sv': len(swedish_result['text']) if swedish_result['text'] else 0,
        'en': len(english_result['text']) if english_result['text'] else 0
    }
    
    best_mode = max(text_lengths, key=text_lengths.get)
    
    if text_lengths[best_mode] > 0:
        console.print(f"\n🏆 Best result: [bold green]{best_mode}[/bold green] ({text_lengths[best_mode]} characters)")
        if best_mode == 'sv':
            console.print("[green]💡 Recommendation: Use -l sv for this audio[/green]")
        elif best_mode == 'en':
            console.print("[green]💡 Recommendation: Use -l en for this audio[/green]")
        else:
            console.print("[green]💡 Auto-detection works well for this audio[/green]")
    else:
        console.print("[red]❌ No successful transcriptions - check audio file[/red]")

if __name__ == "__main__":
    main()