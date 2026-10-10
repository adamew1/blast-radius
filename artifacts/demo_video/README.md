# Offline demonstration

`blast-radius-two-minute.mp4` is the 120-second H264 fallback. `blast-radius-two-minute.webm` is the original 122.76-second clean-launch browser recording. The story itself lasted 120.08 seconds. Captions are editorial; financial output comes from the audited Python engine. There is no recorded narration; use `DEMO.md`.

`recording_manifest.json` records stage times, no external requests or JavaScript errors, and hashes for both files.

Re-record the browser with `scripts/record_demo.py --url <local-url>`. For this capture, export the MP4 with:

```
ffmpeg -ss 2.68 -i blast-radius-two-minute.webm -t 120 -an -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -movflags +faststart blast-radius-two-minute.mp4
```

The trim removes only application-launch pre-roll. Do not reuse the old trim or manifest after replacing the source recording; inspect its actual duration and update the derived-file hash.
