"""
Skill: voice_input
Description: Voice input using OpenAI Whisper (local, offline speech-to-text).
Requires: pip install openai-whisper (or faster-whisper for GPU)
Note: First run will download the model (~1-3 GB depending on size).
Author: Jane's Agent Builder
"""

import os
import threading

SKILL_NAME = "voice_input"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Voice input — speak to the agent using your microphone (Whisper STT)"
SKILL_TOOLS = {
    "voice_listen": {
        "description": "Start listening to the microphone and transcribe speech",
        "args": {"duration": "Recording duration in seconds (default 5)", "language": "Language hint: ru, en, sv (optional)"},
        "example": '{"tool": "voice_listen", "args": {"duration": 5, "language": "ru"}}'
    },
    "voice_transcribe": {
        "description": "Transcribe an audio file to text",
        "args": {"path": "Path to audio file (mp3, wav, m4a, etc.)"},
        "example": '{"tool": "voice_transcribe", "args": {"path": "C:/Users/Dator/Desktop/recording.wav"}}'
    },
    "voice_status": {
        "description": "Check voice input status — Whisper model availability and microphone",
        "args": {},
        "example": '{"tool": "voice_status", "args": {}}'
    }
}

_whisper_model = None
_model_lock = threading.Lock()


def _load_whisper():
    """Load Whisper model (lazy loading)"""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    
    with _model_lock:
        if _whisper_model is not None:
            return _whisper_model
        
        try:
            import whisper
            # Use 'base' model — good balance of speed/quality
            # Options: tiny, base, small, medium, large
            _whisper_model = whisper.load_model("base")
            return _whisper_model
        except ImportError:
            return None


def voice_listen(duration: int = 5, language: str = "") -> str:
    """Record from microphone and transcribe"""
    try:
        import sounddevice as sd
        import numpy as np
        import tempfile
        import wave
    except ImportError:
        return ("Voice input requires additional packages.\n"
                "Run in PowerShell:\n"
                "  pip install sounddevice numpy openai-whisper\n\n"
                "Note: First use downloads the Whisper model (~140 MB for 'base').")
    
    model = _load_whisper()
    if model is None:
        return ("Whisper not installed.\n"
                "Run: pip install openai-whisper\n"
                "Or for faster GPU version: pip install faster-whisper")
    
    duration = min(max(int(duration), 1), 30)  # 1-30 seconds
    sample_rate = 16000
    
    try:
        print(f"  🎤 Recording for {duration} seconds...")
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate,
                       channels=1, dtype='float32')
        sd.wait()
        print("  🎤 Recording complete. Transcribing...")
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name
            # Convert float32 to int16 for wav
            audio_int16 = (audio * 32767).astype(np.int16)
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_int16.tobytes())
        
        # Transcribe
        options = {}
        if language:
            options["language"] = language
        
        result = model.transcribe(temp_path, **options)
        text = result.get("text", "").strip()
        detected_lang = result.get("language", "unknown")
        
        # Clean up
        os.unlink(temp_path)
        
        if not text:
            return "No speech detected. Try speaking louder or closer to the microphone."
        
        return f"🎤 Transcribed ({detected_lang}):\n{text}"
    
    except Exception as e:
        return f"Voice recording error: {str(e)}"


def voice_transcribe(path: str) -> str:
    """Transcribe an audio file"""
    if not os.path.exists(path):
        return f"File not found: {path}"
    
    model = _load_whisper()
    if model is None:
        return "Whisper not installed. Run: pip install openai-whisper"
    
    try:
        result = model.transcribe(path)
        text = result.get("text", "").strip()
        lang = result.get("language", "unknown")
        
        segments = result.get("segments", [])
        
        lines = [f"=== Transcription: {os.path.basename(path)} ==="]
        lines.append(f"Language: {lang}")
        lines.append(f"Duration: {segments[-1]['end']:.1f}s" if segments else "")
        lines.append("")
        lines.append(text)
        
        if len(segments) > 1:
            lines.append("\n--- Segments ---")
            for seg in segments[:50]:
                start = f"{seg['start']:.1f}s"
                end = f"{seg['end']:.1f}s"
                lines.append(f"  [{start} - {end}] {seg['text'].strip()}")
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"Transcription error: {str(e)}"


def voice_status() -> str:
    """Check voice system status"""
    lines = ["=== Voice Input Status ==="]
    
    # Check Whisper
    try:
        import whisper
        lines.append(f"Whisper: ✅ installed")
        if _whisper_model:
            lines.append(f"Model: loaded (base)")
        else:
            lines.append(f"Model: not loaded yet (will load on first use)")
    except ImportError:
        lines.append(f"Whisper: ❌ not installed")
        lines.append(f"  Install: pip install openai-whisper")
    
    # Check sounddevice (microphone)
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        lines.append(f"Microphone: ✅ {len(input_devices)} input device(s)")
        if input_devices:
            default = sd.query_devices(kind='input')
            lines.append(f"  Default: {default['name']}")
    except ImportError:
        lines.append(f"Microphone: ❌ sounddevice not installed")
        lines.append(f"  Install: pip install sounddevice")
    except Exception as e:
        lines.append(f"Microphone: ⚠️ {str(e)}")
    
    # Check numpy
    try:
        import numpy
        lines.append(f"NumPy: ✅ {numpy.__version__}")
    except ImportError:
        lines.append(f"NumPy: ❌ not installed (pip install numpy)")
    
    lines.append(f"\nFull setup: pip install openai-whisper sounddevice numpy")
    return "\n".join(lines)


TOOLS = {
    "voice_listen": lambda args: voice_listen(args.get("duration", 5), args.get("language", "")),
    "voice_transcribe": lambda args: voice_transcribe(args.get("path", "")),
    "voice_status": lambda args: voice_status(),
}
