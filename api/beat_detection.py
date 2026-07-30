"""
Beat detection utility using librosa library.
Detects beats and downbeats from audio files.
"""

import librosa
import numpy as np
import logging

logger = logging.getLogger(__name__)


def detect_beats_and_downbeats(audio_file_path: str) -> dict:
    """
    Detect beats from an audio file using librosa.
    Downbeats are estimated by assuming 4/4 time and that the first
    detected beat is beat 1 of a bar — this is a naive placeholder;
    swap in madmom's DBNDownBeatTrackingProcessor for real bar-position
    detection later.
    """
    try:
        y, sr = librosa.load(audio_file_path, sr=None)

        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
        beats_list = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        # Naive placeholder — see docstring
        downbeats = beats_list[::4]

        return {
            'success': True,
            'beats': beats_list,
            'downbeats': downbeats,
            'downbeats_estimated': True,
            'total_beats': len(beats_list),
            'total_downbeats': len(downbeats),
            'tempo': float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo),
            'sample_rate': sr
        }
    except Exception as e:
        logger.error(f"Error detecting beats: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'beats': [],
            'downbeats': []
        }
