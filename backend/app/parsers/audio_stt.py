import os
import logging
from typing import Optional
from google.cloud import speech

logger = logging.getLogger(__name__)

def transcribe_audio_gcs(gcs_uri: str, language_code: str = "en-US") -> Optional[str]:
    """Transcribes an audio file on GCS using Google Cloud Speech-to-Text LongRunningRecognize."""
    if os.environ.get("CINESPINE_DISABLE_STT", "").strip().lower() in ("1", "true", "yes"):
        return None
        
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning("GOOGLE_CLOUD_PROJECT not set, STT disabled.")
        return None

    try:
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(uri=gcs_uri)
        
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=48000, # Assuming standard production audio, usually 48kHz
            language_code=language_code,
            enable_automatic_punctuation=True,
            model="video" # Video model works well for production dialogue
        )

        logger.info("Starting STT long-running recognize for %s", gcs_uri)
        operation = client.long_running_recognize(config=config, audio=audio)
        
        response = operation.result(timeout=600)
        
        transcript = []
        for result in response.results:
            transcript.append(result.alternatives[0].transcript)
            
        return "\n".join(transcript).strip()
    except Exception as e:
        logger.error("STT transcription failed for %s: %s", gcs_uri, e)
        return None
