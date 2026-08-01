"""
Export a DownbeatTimeline to a Reaper (.rpp) project file.

Produces four tracks, in order:
  1. Empty — carries the pre-built video-processor FXCHAIN (see FXCHAIN_1).
  2. Outer — one item per downbeat that has an assigned ``path_outer``.
     Feeds the left & right panels of the 3x1 video processor.
  3. Video — one item per downbeat that has an assigned ``path``.
     Feeds the center panel. Downbeat intervals with no assigned video
     are filled by extending the *previous* video's item to cover the gap.
  4. Audio — the source audio, one item spanning the full duration.

Media is linked by absolute path (not copied/embedded), matching how the
JSON timeline already stores paths.

RPP is a plain-text, nested-chunk format. It isn't officially documented but
is stable and well understood; whitespace/indentation is cosmetic only —
REAPER parses purely on the `<...>` token structure, so chunks (like the
FXCHAIN below) can be embedded as-is without reindenting.
"""

from pathlib import Path

from api.schema import DownbeatTimeline

# Extensions Reaper treats as WAVE-like PCM containers vs. compressed/other.
# This only affects the SOURCE tag name; Reaper primarily trusts the FILE
# extension, so an inexact match here is harmless.
_AUDIO_SOURCE_TYPES = {
    '.wav': 'WAVE', '.aiff': 'WAVE', '.aif': 'WAVE',
    '.mp3': 'MP3',
    '.flac': 'FLAC',
    '.ogg': 'OGG',
    '.m4a': 'VIDEO',  # m4a/aac containers open fine under the VIDEO source in practice
    '.aac': 'VIDEO',
    '.wma': 'VIDEO',
}
_VIDEO_SOURCE_TYPES = {
    '.mp4': 'VIDEO', '.mov': 'VIDEO', '.avi': 'VIDEO',
    '.mkv': 'VIDEO', '.webm': 'VIDEO',
}

# Track 1's FXCHAIN — the "3x1 horizontal strip with mirroring" video
# processor. Embedded verbatim; inserted as-is inside the TRACK chunk.
FXCHAIN_1 = r'''<FXCHAIN
      WNDRECT 249 85 1219 598
      SHOW 0
      LASTSEL 0
      DOCKED 0
      BYPASS 0 0 0
      <VIDEO_EFFECT "Video processor" ""
        <CODE
          |// 3x1 horizontal strip with mirroring
          |// only needs 2 source tracks
          |// Left & right panels both come from track 0; middle comes from track 1.
          |// Center panel's width is adjustable; the two side panels shrink/grow to fill the remaining space.
          |// All panels: scale by whichever axis is needed to fully cover their cell with no blank space.
          |// Mirror mode: one outer panel is a horizontal mirror of the other (flip_side picks which).
          |// Flip mode (mirror off): flip_side toggles both outer panels flipping together.
          |// If a track has no video, that panel is filled with black.
          |
          |//@param1:flip_side 'Flip side' 0 0 1 0.5 1
          |//@param2:center_width 'Center width' 0.3333 0.05 0.9 0.3333 0.01
          |//@param3:enable_mirror 'Mirror' 1 0 1 0.5 1
          |
          |cellh = project_h;
          |
          |// integer pixel boundaries computed once, last cell absorbs any rounding remainder
          |sidew_px = ((project_w * (1 - center_width)) * 0.5)|0;
          |centerw_px = (project_w - 2*sidew_px)|0;
          |x0 = 0;
          |x1 = sidew_px;
          |x2 = sidew_px + centerw_px;
          |x3 = project_w|0;  // true right edge, no rounding drift
          |
          |mirror_idx = enable_mirror < 0.5 ? -1 : (flip_side < 0.5 ? 2 : 0);  // -1 = no panel mirrored
          |
          |x = 0;
          |loop(3,
          |  src_track = (x == 1) ? 1 : 0;  // middle panel = track 1, left & right panels = track 0
          |  img = input_track_exact(src_track);  // exact track position, no skipping blank tracks
          |
          |  // per-panel cell position/size, using shared integer boundaries (no gaps/seams)
          |  x == 1 ? (
          |    cellx = x1; cellw = x2 - x1;
          |  ) : x == 0 ? (
          |    cellx = x0; cellw = x1 - x0;
          |  ) : (
          |    cellx = x2; cellw = x3 - x2;
          |  );
          |
          |  // decide if this panel should be flipped:
          |  // - mirror on: only the chosen side (mirror_idx) flips, relative to the other
          |  // - mirror off: both outer panels flip together, based on flip_side
          |  do_flip = (x != 1) && (enable_mirror >= 0.5 ? (x == mirror_idx) : (flip_side >= 0.5));
          |
          |  (img >= 0) && input_info(img, sw, sh) ? (
          |    scale = max(cellw / sw, cellh / sh);  // cover-fit: fill the cell completely, no gaps
          |    vis_w = cellw / scale;         // width of source visible at that scale
          |    vis_h = cellh / scale;         // height of source visible at that scale
          |    cropx = (sw - vis_w) * 0.5;    // center-crop horizontally
          |    cropy = (sh - vis_h) * 0.5;    // center-crop vertically
          |
          |    do_flip ? (
          |      // flip: scan the source backwards (right-to-left) as we go left-to-right in the dest
          |      gfx_deltablit(img,
          |        cellx|0, 0, cellw|0, cellh|0,       // dest: x,y,w,h
          |        (cropx+vis_w)|0, cropy|0,           // src start point: right edge of the crop window
          |        -(vis_w/cellw), 0,                  // dsdx (negative = flip), dtdx
          |        0, vis_h/cellh,                     // dsdy, dtdy
          |        0, 0                                // dsdxdy, dtdxdy
          |      );
          |    ) : (
          |      gfx_blit(img, 0,
          |               cellx|0, 0, cellw|0, cellh|0,   // dest rect
          |               cropx|0, cropy|0, vis_w|0, vis_h|0); // src rect
          |    );
          |  ) : (
          |    // no video available on this track right now - fill the cell with black
          |    gfx_set(0,0,0,1);
          |    gfx_fillrect(cellx|0, 0, cellw|0, cellh|0);
          |  );
          |  x += 1;
          |);
        >
        CODEPARM 1 0.33 1 1 0 0 0 1 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
      >
      PRESETNAME "Rob: 3x1 horizontal strip with mirroring"
      FLOATPOS 0 0 0 0
      FXID {0C0E67DE-42CD-DA48-8BF5-B19D994D83EA}
      <PARMENV 0 0 1 0.5 "Flip side / 3x1 horizontal strip with mirroring - video processor"
        EGUID {8EDF933D-4F25-1749-9EF6-9E6A11C9B0A0}
        ACT 0 -1
        VIS 0 1 1
        LANEHEIGHT 0 0
        ARM 0
        DEFSHAPE 1 -1 -1
        PT 0 1 1
      >
      WAK 0 0
    >
'''


def _source_type(path: str, default: str) -> str:
    ext = Path(path).suffix.lower()
    return _AUDIO_SOURCE_TYPES.get(ext) or _VIDEO_SOURCE_TYPES.get(ext) or default


def _esc(name: str) -> str:
    """Quote a string for an RPP field, escaping embedded double quotes."""
    return name.replace('"', '\\"')


def _item_chunk(*, position: float, length: float, name: str, file_path: str,
                 source_type: str, indent: str, extra: str = None) -> str:
    """Build a single <ITEM> chunk with a linked (non-embedded) media source."""
    inner = indent + '  '
    return (
        f'{indent}<ITEM\n'
        f'{inner}POSITION {position:.6f}\n'
        f'{inner}LENGTH {length:.6f}\n'
        f'{inner}NAME "{_esc(name)}"\n'
        f'{inner}<SOURCE {source_type}\n'
        # f'{inner}  {extra}\n' if extra else ''
        f'{inner}  FILE "{_esc(file_path)}"\n'
        f'{inner}>\n'
        f'{indent}>\n'
    )


def _track_chunk(*, name: str, item_chunks: str = '', fx_chunk: str = '') -> str:
    """Build a <TRACK> chunk, optionally carrying an FXCHAIN and/or item(s)."""
    return (
        '  <TRACK\n'
        f'    NAME "{_esc(name)}"\n'
        f'{fx_chunk}'
        f'{item_chunks}'
        '  >\n'
    )


def _audio_item_chunk(timeline: DownbeatTimeline) -> str:
    duration = timeline.duration or 0.0
    source_type = _source_type(timeline.path, default='WAVE')
    return _item_chunk(
        position=0.0,
        length=duration,
        name=Path(timeline.path).name,
        file_path=timeline.path,
        source_type=source_type,
        indent='    ',
        extra='VIDEO_DISABLED'
    )


def _video_item_chunks(timeline: DownbeatTimeline, path_field: str = 'path') -> str:
    """
    Build the video items for a given path field ('path' or 'path_outer').
    Walks downbeat intervals in order; a downbeat with no path doesn't get
    its own item — instead the previous video's item is extended to cover
    that interval too, so there's never a gap once at least one video has
    been assigned. A leading gap (no video assigned yet at all) is left
    empty, since there's nothing to extend backwards from.
    """
    duration = timeline.duration or 0.0
    downbeats = sorted(timeline.downbeats, key=lambda db: db.time)

    # Interval boundaries: downbeat times plus the audio's end.
    bounds = [db.time for db in downbeats] + [duration]

    items: list[dict] = []  # each: {position, end, path}
    for i, db in enumerate(downbeats):
        interval_end = bounds[i + 1]
        vid_path = getattr(db, path_field)
        if vid_path:
            items.append({'position': db.time, 'end': interval_end, 'path': vid_path})
        elif items:
            # No video for this interval — extend the previous item to cover it.
            items[-1]['end'] = interval_end
        # else: no video assigned yet at all — nothing to extend, interval stays empty.

    chunks = []
    for item in items:
        source_type = _source_type(item['path'], default='VIDEO')
        chunks.append(_item_chunk(
            position=item['position'],
            length=item['end'] - item['position'],
            name=Path(item['path']).name,
            file_path=item['path'],
            source_type=source_type,
            indent='    ',
        ))

    return ''.join(chunks)


def _marker_lines(timeline: DownbeatTimeline) -> str:
    """One MARKER line per beat and per downbeat (downbeats labelled, beats not)."""
    downbeat_times = {db.time for db in timeline.downbeats}
    lines = []
    idx = 1
    for t in sorted(set(timeline.beats) | downbeat_times):
        label = 'Downbeat' if t in downbeat_times else ''
        lines.append(f'  MARKER {idx} {t:.6f} "{_esc(label)}" 0 0 0 0\n')
        idx += 1
    return ''.join(lines)


def export_to_rpp(timeline: DownbeatTimeline, output_path: str) -> None:
    """
    Write ``timeline`` to ``output_path`` as a Reaper project file with four
    tracks (FX-processor / outer-video / inner-video / audio). Media is
    linked by absolute path, not copied or embedded.
    """
    tempo_line = f'  TEMPO {timeline.tempo:.4f} 4 4\n' if timeline.tempo else ''

    track1 = _track_chunk(name='Video FX', fx_chunk=FXCHAIN_1)
    track2 = _track_chunk(name='Outer', item_chunks=_video_item_chunks(timeline, 'path_outer'))
    track3 = _track_chunk(name='Video', item_chunks=_video_item_chunks(timeline, 'path'))
    track4 = _track_chunk(name=f'{Path(timeline.path).stem} (audio)',
                           item_chunks=_audio_item_chunk(timeline))

    project = (
        '<REAPER_PROJECT 0.1 "6.0" 0\n'
        f'{tempo_line}'
        f'{_marker_lines(timeline)}'
        f'{track1}'
        f'{track2}'
        f'{track3}'
        f'{track4}'
        '>\n'
    )

    Path(output_path).write_text(project)