#!/usr/bin/env python3
"""
WhisperX Performance Benchmark Tool
Compare different compute types, batch sizes, and model configurations.
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

import whisperx
import torch
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text

console = Console()

@dataclass
class BenchmarkResult:
    """Store benchmark results for a single configuration."""
    compute_type: str
    batch_size: int
    model: str
    device: str
    language: str
    duration: float
    transcribe_time: float
    align_time: float
    total_time: float
    realtime_factor: float
    memory_peak: Optional[float] = None
    segments_count: int = 0
    words_count: int = 0

class PerformanceBenchmark:
    """Benchmark different WhisperX configurations."""
    
    def __init__(self, audio_path: str, output_dir: str = "./benchmark_results"):
        self.audio_path = Path(audio_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[BenchmarkResult] = []
        
        # Load audio once for all tests
        console.print("📁 Loading audio file for benchmarking...")
        self.audio = whisperx.load_audio(str(audio_path))
        self.duration = len(self.audio) / 16000
        
        console.print(f"📊 Audio duration: {self.duration:.1f}s ({self.duration/60:.1f}min)")
        console.print(f"📁 Results will be saved to: {self.output_dir}")
    
    def benchmark_configuration(
        self, 
        compute_type: str, 
        batch_size: int, 
        model: str = "large-v3",
        device: str = "cpu",
        language: str = "sv"
    ) -> BenchmarkResult:
        """Benchmark a single configuration."""
        
        console.print(f"\n🔥 Testing: {compute_type} | batch={batch_size} | {device.upper()}")
        
        total_start = time.time()
        
        try:
            # Load model
            console.print("🤖 Loading model...")
            model_start = time.time()
            whisper_model = whisperx.load_model(model, device, compute_type=compute_type, language=language)
            model_load_time = time.time() - model_start
            
            # Track memory usage if CUDA
            initial_memory = None
            peak_memory = None
            if device == "cuda" and torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
                initial_memory = torch.cuda.memory_allocated() / 1024**2  # MB
            
            # Transcribe
            console.print("🎯 Transcribing...")
            transcribe_start = time.time()
            result = whisper_model.transcribe(
                self.audio, 
                batch_size=batch_size,
                language=language,
                print_progress=True,
                combined_progress=True
            )
            transcribe_time = time.time() - transcribe_start
            
            # Check memory peak
            if device == "cuda" and torch.cuda.is_available():
                peak_memory = torch.cuda.max_memory_allocated() / 1024**2  # MB
            
            # Load alignment model
            console.print("🔗 Loading alignment...")
            align_start = time.time()
            alignment_model_name = "KBLab/wav2vec2-base-voxpopuli-sv-swedish" if language == "sv" else "WAV2VEC2_ASR_LARGE_LV60K_960H"
            model_a, metadata = whisperx.load_align_model(
                language_code=language, 
                device=device,
                model_name=alignment_model_name
            )
            
            # Align
            result = whisperx.align(
                result["segments"], 
                model_a, 
                metadata, 
                self.audio, 
                device, 
                return_char_alignments=False
            )
            align_time = time.time() - align_start
            
            total_time = time.time() - total_start
            realtime_factor = self.duration / transcribe_time if transcribe_time > 0 else 0
            
            # Count segments and words
            segments_count = len(result.get("segments", []))
            words_count = sum(len(seg.get("words", [])) for seg in result.get("segments", []))
            
            benchmark_result = BenchmarkResult(
                compute_type=compute_type,
                batch_size=batch_size,
                model=model,
                device=device,
                language=language,
                duration=self.duration,
                transcribe_time=transcribe_time,
                align_time=align_time,
                total_time=total_time,
                realtime_factor=realtime_factor,
                memory_peak=peak_memory,
                segments_count=segments_count,
                words_count=words_count
            )
            
            console.print(f"[green]✅ Complete: {realtime_factor:.1f}x realtime[/green]")
            if peak_memory:
                console.print(f"[blue]💾 Peak GPU memory: {peak_memory:.0f}MB[/blue]")
            
            # Clean up GPU memory
            if device == "cuda":
                del whisper_model, model_a
                torch.cuda.empty_cache()
            
            return benchmark_result
            
        except Exception as e:
            console.print(f"[red]❌ Failed: {e}[/red]")
            return BenchmarkResult(
                compute_type=compute_type,
                batch_size=batch_size,
                model=model,
                device=device,
                language=language,
                duration=self.duration,
                transcribe_time=0,
                align_time=0,
                total_time=0,
                realtime_factor=0,
                memory_peak=None,
                segments_count=0,
                words_count=0
            )
    
    def run_comprehensive_benchmark(
        self, 
        compute_types: List[str] = None,
        batch_sizes: List[int] = None,
        device: str = "cpu",
        language: str = "sv"
    ):
        """Run comprehensive benchmark across multiple configurations."""
        
        if compute_types is None:
            compute_types = ["int8", "float16", "float32"] if device == "cuda" else ["int8", "float32"]
        
        if batch_sizes is None:
            batch_sizes = [4, 8, 16] if device == "cuda" else [4, 8]
        
        console.print(Panel(
            f"[bold blue]🏁 Starting Comprehensive Benchmark[/bold blue]\n"
            f"[cyan]Audio:[/cyan] {self.audio_path.name} ({self.duration:.1f}s)\n"
            f"[cyan]Device:[/cyan] {device.upper()}\n"
            f"[cyan]Language:[/cyan] {language.upper()}\n"
            f"[cyan]Configurations:[/cyan] {len(compute_types)} × {len(batch_sizes)} = {len(compute_types) * len(batch_sizes)} tests",
            title="🔥 Benchmark Suite",
            border_style="red"
        ))
        
        total_tests = len(compute_types) * len(batch_sizes)
        current_test = 0
        
        for compute_type in compute_types:
            for batch_size in batch_sizes:
                current_test += 1
                console.print(f"\n[bold]Test {current_test}/{total_tests}[/bold]")
                
                result = self.benchmark_configuration(
                    compute_type=compute_type,
                    batch_size=batch_size,
                    device=device,
                    language=language
                )
                self.results.append(result)
                
                # Short pause between tests
                time.sleep(2)
        
        console.print(f"\n[green]🎉 Benchmark complete! {len(self.results)} configurations tested.[/green]")
    
    def display_results(self):
        """Display benchmark results in a formatted table."""
        
        if not self.results:
            console.print("[red]No benchmark results to display.[/red]")
            return
        
        # Sort by realtime factor (fastest first)
        sorted_results = sorted(self.results, key=lambda r: r.realtime_factor, reverse=True)
        
        # Create results table
        table = Table(title="🏆 Benchmark Results", show_header=True, header_style="bold blue")
        table.add_column("Compute", style="cyan")
        table.add_column("Batch", style="yellow")
        table.add_column("Transcribe", style="green")
        table.add_column("Align", style="blue")
        table.add_column("Total", style="magenta")
        table.add_column("Speed", style="bold green")
        table.add_column("Memory", style="dim")
        table.add_column("Quality", style="white")
        
        for result in sorted_results:
            # Speed ranking emoji
            if result.realtime_factor >= 10:
                speed_emoji = "🚀"
            elif result.realtime_factor >= 5:
                speed_emoji = "⚡"
            elif result.realtime_factor >= 2:
                speed_emoji = "🏃"
            elif result.realtime_factor >= 1:
                speed_emoji = "🚶"
            else:
                speed_emoji = "🐌"
            
            memory_str = f"{result.memory_peak:.0f}MB" if result.memory_peak else "N/A"
            quality_str = f"{result.segments_count}seg" if result.segments_count > 0 else "Failed"
            
            table.add_row(
                result.compute_type,
                str(result.batch_size),
                f"{result.transcribe_time:.1f}s",
                f"{result.align_time:.1f}s", 
                f"{result.total_time:.1f}s",
                f"{speed_emoji} {result.realtime_factor:.1f}x",
                memory_str,
                quality_str
            )
        
        console.print(table)
        
        # Show best configuration
        best = sorted_results[0]
        if best.realtime_factor > 0:
            console.print(Panel(
                f"[bold green]🏆 Best Configuration[/bold green]\n"
                f"[cyan]Compute Type:[/cyan] {best.compute_type}\n"
                f"[cyan]Batch Size:[/cyan] {best.batch_size}\n"
                f"[cyan]Speed:[/cyan] {best.realtime_factor:.1f}x realtime\n"
                f"[cyan]Total Time:[/cyan] {best.total_time:.1f}s for {best.duration:.1f}s audio",
                title="🎯 Recommendation",
                border_style="green"
            ))
    
    def save_results(self, filename: str = None):
        """Save benchmark results to JSON file."""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_{self.audio_path.stem}_{timestamp}.json"
        
        output_file = self.output_dir / filename
        
        # Convert results to serializable format
        results_data = {
            "audio_file": str(self.audio_path),
            "audio_duration": self.duration,
            "timestamp": datetime.now().isoformat(),
            "results": [
                {
                    "compute_type": r.compute_type,
                    "batch_size": r.batch_size,
                    "model": r.model,
                    "device": r.device,
                    "language": r.language,
                    "duration": r.duration,
                    "transcribe_time": r.transcribe_time,
                    "align_time": r.align_time,
                    "total_time": r.total_time,
                    "realtime_factor": r.realtime_factor,
                    "memory_peak": r.memory_peak,
                    "segments_count": r.segments_count,
                    "words_count": r.words_count
                }
                for r in self.results
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        console.print(f"[green]💾 Results saved to: {output_file}[/green]")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark WhisperX performance across different configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s audio.m4a                           # Quick CPU benchmark
  %(prog)s audio.m4a --device cuda             # GPU benchmark
  %(prog)s audio.m4a --compute-types int8      # Test only int8
  %(prog)s audio.m4a --batch-sizes 4,8,16      # Test specific batch sizes
        """
    )
    parser.add_argument("audio", help="Input audio file path")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Processing device")
    parser.add_argument("--language", "-l", default="sv", help="Language code (default: sv)")
    parser.add_argument("--compute-types", help="Comma-separated compute types (e.g., int8,float16,float32)")
    parser.add_argument("--batch-sizes", help="Comma-separated batch sizes (e.g., 4,8,16)")
    parser.add_argument("--output-dir", default="./benchmark_results", help="Output directory for results")
    parser.add_argument("--save", action="store_true", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Validate audio file
    audio_path = Path(args.audio)
    if not audio_path.exists():
        console.print(f"[red]❌ Audio file not found: {args.audio}[/red]")
        sys.exit(1)
    
    # Check device availability
    if args.device == "cuda" and not torch.cuda.is_available():
        console.print("[yellow]⚠️ CUDA not available, falling back to CPU[/yellow]")
        args.device = "cpu"
    
    # Parse compute types
    compute_types = None
    if args.compute_types:
        compute_types = [ct.strip() for ct in args.compute_types.split(',')]
    
    # Parse batch sizes
    batch_sizes = None
    if args.batch_sizes:
        batch_sizes = [int(bs.strip()) for bs in args.batch_sizes.split(',')]
    
    # Run benchmark
    benchmark = PerformanceBenchmark(args.audio, args.output_dir)
    benchmark.run_comprehensive_benchmark(
        compute_types=compute_types,
        batch_sizes=batch_sizes,
        device=args.device,
        language=args.language
    )
    
    # Display and optionally save results
    benchmark.display_results()
    
    if args.save:
        benchmark.save_results()


if __name__ == "__main__":
    main()