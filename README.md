# 🎙️ WhisperX Automated Transcription System

<div align="center">

**Transform your audio recordings into accurate transcripts with speaker identification**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![WhisperX](https://img.shields.io/badge/WhisperX-3.1+-green.svg)](https://github.com/m-bain/whisperX)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)

</div>

---

## ✨ Features

- 🤖 **Smart Language Detection** - Automatically detects Swedish and English (for optimal alignment models)
- 👥 **Speaker Diarization** - Identifies who said what in multi-speaker recordings (Swedish works without HF_TOKEN)
- 🔄 **Automated Workflow** - Drop files → Get transcripts → Files archived
- 📱 **Native Notifications** - macOS notifications for processing status
- 📄 **Multiple Formats** - Default TXT output, customizable to include JSON, SRT, VTT, and TSV
- ⚡ **Optimized Performance** - float32 compute type for better quality (configurable)
- 🛡️ **Production Ready** - Built with uv for reliable dependency management

## 🚀 Quick Start

### Prerequisites
- **macOS only** (notifications and system integration)
- Python 3.9-3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- [HuggingFace account](https://huggingface.co/join) for speaker diarization (optional for Swedish)

### Installation

```bash
# Clone this repository
git clone https://github.com/jimmystridh/whisperx-transcription.git
cd whisperx-transcription

# Install dependencies
uv sync

# Configure your HuggingFace token (optional for Swedish)
cp .env.sample .env
# Edit .env and add your HF_TOKEN from https://huggingface.co/settings/tokens
# Note: Swedish diarization works without HF_TOKEN
```

### Test Drive

```bash
# Test with a single file
uv run python transcribe.py path/to/your/audio.m4a

# Start automatic processing
uv run python watcher.py
```

That's it! Drop audio files in `incoming/` and watch the magic happen! ✨

## 📁 Project Structure

```
whisperx-transcription/
├── 📂 incoming/           # Drop new recordings here
├── 📂 transcripts/        # Your transcripts appear here
├── 📂 recording_archive/  # Processed files stored here
├── 🐍 transcribe.py       # Core transcription engine
├── 👀 watcher.py          # File monitoring daemon
├── ⚙️  .env               # Your configuration
├── 📦 pyproject.toml      # Project dependencies
└── 📖 README.md          # This guide
```

## 💡 How It Works

1. **Drop** audio files into the `incoming/` folder
2. **Detection** - System detects language and loads optimal models
3. **Transcription** - WhisperX processes with timestamps and alignment
4. **Diarization** - Identifies different speakers (if enabled)
5. **Output** - Multiple format files saved to `transcripts/`
6. **Archive** - Original files moved to `recording_archive/`
7. **Notify** - macOS notification confirms completion

## 🎯 Usage Modes

### 🤖 Automatic Mode (Recommended)
Perfect for ongoing transcription needs:
```bash
uv run python watcher.py
```
- **Processes existing files first** (no need to move files around)
- Monitors `incoming/` folder continuously
- Processes files as soon as they're added
- Sends macOS notifications for each completed transcription

### 🔧 Manual Mode
For one-off transcriptions:
```bash
uv run python transcribe.py my-recording.m4a -o ./transcripts
```

### 📦 Batch Processing
Process existing files all at once:
```bash
uv run python watcher.py --process-existing --once
```

## 🎛️ Configuration Options

### Transcription Options
```bash
uv run python transcribe.py [file] [options]
  -o, --output DIR      Output directory (default: ./transcripts)
  -l, --language CODE   Force language (sv/en, auto-detected by default)
  --no-diarize         Skip speaker identification
  --device DEVICE      cpu or cuda (default: cpu)
  --formats FORMAT     Output formats (default: txt)
  --all-formats        Generate all output formats
```

### Watcher Options
```bash
uv run python watcher.py [options]
  --incoming DIR        Watch directory (default: ./incoming)
  --transcripts DIR     Output directory (default: ./transcripts)
  --archive DIR         Archive directory (default: ./recording_archive)
  --process-existing    Process files already in incoming/
  --once               Process once and exit (don't watch)
```

## 🎵 Supported Formats

| Format | Extension | Notes |
|--------|-----------|--------|
| MPEG-4 Audio | `.m4a` | Recommended |
| MPEG-4 Video | `.mp4` | Audio extracted |
| QuickTime | `.mov` | Audio extracted |
| WAVE | `.wav` | Uncompressed |
| MP3 | `.mp3` | Compressed |
| FLAC | `.flac` | Lossless |
| OGG | `.ogg` | Open source |

## 🌍 Language Support

**Smart Detection:** The system automatically detects Swedish vs English to select optimal alignment models.

| Language | Alignment Model | Auto-Detection | Diarization |
|----------|----------------|----------------|-------------|
| 🇸🇪 Swedish | `KBLab/wav2vec2-base-voxpopuli-sv-swedish` | ✅ Supported | No HF_TOKEN needed |
| 🇺🇸 English | `WAV2VEC2_ASR_LARGE_LV60K_960H` | ✅ Supported | Requires HF_TOKEN |
| 🌐 Others | English model (fallback) | ❌ Manual only | Requires HF_TOKEN |

**Note:** Language detection currently focuses on Swedish/English optimization. Other languages require manual specification with `-l` flag.

## 📄 Output Formats

By default, each audio file generates **TXT output** (customizable):

| Format | File | Description |
|--------|------|-------------|
| 📝 Plain Text | `filename.txt` | Clean transcript with speaker labels |
| 🔧 JSON | `filename.json` | Full metadata, timestamps, confidence scores |
| 🎬 SRT | `filename.srt` | Subtitle format for video players |
| 🌐 WebVTT | `filename.vtt` | Web-compatible subtitle format |
| 📊 TSV | `filename.tsv` | Spreadsheet-friendly with precise timings |

### Example Output Structure
```
transcripts/
├── meeting-2025-01-15.txt     # [Speaker 1] Welcome everyone...
├── meeting-2025-01-15.json    # {"segments": [{"start": 0.5, ...}]}
├── meeting-2025-01-15.srt     # 1\n00:00:00,500 --> 00:00:03,200\n...
├── meeting-2025-01-15.vtt     # WEBVTT\n\n00:00:00.500 --> 00:00:03.200\n...
└── meeting-2025-01-15.tsv     # start    end    speaker    text
```

## 🔔 macOS Notifications

Stay informed with native notifications:

- **🚀 Processing Started** - When transcription begins
- **✅ Transcription Complete** - With language, duration, and speaker info
- **❌ Processing Failed** - Error details for troubleshooting

<div align="center">
<img src="https://via.placeholder.com/400x100/007ACC/FFFFFF?text=🔔+Transcription+Complete!+Swedish+•+3m+42s+•+2+speakers" alt="Notification Example" />
</div>

## 🛠️ Advanced Setup

### GPU Acceleration (CUDA)
```bash
# Note: Primarily tested on macOS (CPU-only)
# GPU support available but not extensively tested on macOS
uv sync --extra gpu  # Install CUDA support
uv run python transcribe.py file.m4a --device cuda
```

### Performance Benchmarking
```bash
# Compare different configurations (float32 is now default)
uv run python benchmark.py audio.m4a
uv run python benchmark.py audio.m4a --compute-types "float32,int8,float16"
```

### Development Mode
```bash
uv sync --extra dev   # Install Jupyter, matplotlib, etc.
```

### Run as Background Service
Set up automatic startup with launchd:

```bash
# Create service file
cat > ~/Library/LaunchAgents/com.user.whisperx-watcher.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.whisperx-watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>uv</string>
        <string>run</string>
        <string>python</string>
        <string>watcher.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/your/whisperx-transcription</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/your/whisperx-transcription/watcher.out.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/your/whisperx-transcription/watcher.err.log</string>
</dict>
</plist>
EOF

# Start service
launchctl load ~/Library/LaunchAgents/com.user.whisperx-watcher.plist
```

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "HF_TOKEN not found" | Create `.env` file with your HuggingFace token (not needed for Swedish) |
| "CUDA not available" | Normal on Mac - system automatically uses CPU |
| Files not processing | Check file format, ensure complete upload, verify macOS compatibility |
| Slow processing | Use benchmark tool to find optimal settings for your hardware |
| No notifications | Check macOS notification permissions in System Preferences |
| Language detection issues | Currently optimized for Swedish/English only - use `-l` flag for others |

### Debug Logs
Monitor system activity:
```bash
tail -f transcription.log    # Transcription process
tail -f watcher.log         # File monitoring
```

### Test Setup
```bash
# Quick system test
uv run python transcribe.py --help
uv run python watcher.py --help

# Process test file
uv run python watcher.py --process-existing --once
```

## 🚀 Performance Tips

- **🕐 Timing**: Run during off-hours for CPU-intensive tasks
- **📁 File Size**: Split very long recordings (>2 hours) for better processing
- **🔄 Batch Mode**: Use `--process-existing` for multiple files
- **💾 Storage**: Archive old transcripts to save disk space

## 📝 Example Workflow

Here's a typical day with the system:

```bash
# Morning: Start the watcher
uv run python watcher.py

# During the day: Drop recordings in incoming/
# - meeting-notes.m4a
# - interview-candidate.mov  
# - conference-call.wav

# System automatically:
# ✅ Detects languages
# ✅ Transcribes with speakers
# ✅ Saves multiple formats
# ✅ Archives originals
# ✅ Sends notifications

# Evening: Find all transcripts ready in transcripts/
```

## 🤝 Contributing

Found a bug or have a feature request? 
- Check existing issues
- Create detailed bug reports
- Share your use cases

## 📄 License

This project is open source. Feel free to modify and adapt for your needs.

---

<div align="center">

**Made with ❤️ for seamless audio transcription**

[⬆️ Back to Top](#️-whisperx-automated-transcription-system)

</div>