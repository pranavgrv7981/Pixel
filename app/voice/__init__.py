"""Voice, Speech-to-Text, and Text-to-Speech package."""

from app.voice.audio import AudioRecorder, get_default_microphone, list_microphones, select_microphone
from app.voice.manager import VoiceManager
from app.voice.models import AudioDevice, TranscriptionResult, VoiceState, VoiceStatus
from app.voice.providers import FasterWhisperProvider, MockSpeechToTextProvider, SpeechToTextProvider
from app.voice.text_sanitizer import sanitize_text_for_speech
from app.voice.tts_audio import AudioPlayer, get_default_output_device, list_output_devices, select_output_device
from app.voice.tts_manager import TTSManager
from app.voice.tts_models import AudioOutputDevice, TTSResult, TTSState, TTSStatus, VoiceInfo
from app.voice.tts_providers import MockTTSProvider, Pyttsx3Provider, TextToSpeechProvider

__all__ = [
    "AudioDevice",
    "AudioOutputDevice",
    "AudioPlayer",
    "AudioRecorder",
    "FasterWhisperProvider",
    "MockSpeechToTextProvider",
    "MockTTSProvider",
    "Pyttsx3Provider",
    "SpeechToTextProvider",
    "TTSManager",
    "TTSResult",
    "TTSState",
    "TTSStatus",
    "TextToSpeechProvider",
    "TranscriptionResult",
    "VoiceInfo",
    "VoiceManager",
    "VoiceState",
    "VoiceStatus",
    "get_default_microphone",
    "get_default_output_device",
    "list_microphones",
    "list_output_devices",
    "sanitize_text_for_speech",
    "select_microphone",
    "select_output_device",
]
