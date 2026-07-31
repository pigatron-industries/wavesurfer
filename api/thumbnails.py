"""
Video thumbnail and metadata utilities.
Extracts the first frame of a video as a small base64 data URL for use as a
library thumbnail, and reads video duration — all without needing a static file
server or temp files on disk.
"""

import base64
import logging

import cv2

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 96


def get_thumbnail_data_url(video_path: str) -> str | None:
    """
    Extract the first frame of `video_path` and return it as a
    'data:image/jpeg;base64,...' URL, resized to THUMBNAIL_WIDTH wide while
    preserving aspect ratio. Returns None if no frame could be read (e.g. an
    audio-only file, a corrupt video, or an unsupported codec) so callers can
    fall back to a generic icon.
    """
    cap = cv2.VideoCapture(video_path)
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            return None

        height, width = frame.shape[:2]
        if width == 0 or height == 0:
            return None
        scale = THUMBNAIL_WIDTH / width
        resized = cv2.resize(frame, (THUMBNAIL_WIDTH, max(1, int(height * scale))))

        ok, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return None

        b64 = base64.b64encode(buffer).decode('ascii')
        return f'data:image/jpeg;base64,{b64}'
    except Exception as e:
        logger.warning(f"Could not extract thumbnail for {video_path}: {e}")
        return None
    finally:
        cap.release()


def get_video_duration(video_path: str) -> float | None:
    """
    Return the duration of `video_path` in seconds, or None if it can't be read.
    """
    cap = cv2.VideoCapture(video_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frames <= 0:
            return None
        return frames / fps
    except Exception as e:
        logger.warning(f"Could not read duration for {video_path}: {e}")
        return None
    finally:
        cap.release()