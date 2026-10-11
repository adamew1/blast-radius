# Offline demonstration

`blast-radius-two-minute.webm` records actual browser interactions with the final
Snapshot/Live mode selector and audited baseline. Recorded on 2026-10-11; the
story is 120.03 seconds and the source file includes launch pre-roll. Captions are
editorial; financial results come from the Python engine. There is no narration;
use the root `DEMO.md` script.

`blast-radius-two-minute.mp4` is the H264/yuv420p fallback (119.96 seconds), exported
after removing 1.41 seconds of measured launch pre-roll. Full FFmpeg decoding
passed. `recording_manifest.json` records hashes, source hashes, stage timings and
the absence of external browser requests and JavaScript errors.

Re-record with `scripts/record_demo.py --url <local-url>`.

For this capture only, export with:

```powershell
ffmpeg -ss 1.41 -i blast-radius-two-minute.webm -t 120 -an -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -movflags +faststart blast-radius-two-minute.mp4
```

Inspect actual durations and regenerate hashes after a new capture; do not reuse
this trim blindly. The recording demonstrates Snapshot Mode, not fresh Live Mode.
