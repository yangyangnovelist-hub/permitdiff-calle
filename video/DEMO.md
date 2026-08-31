# PermitDiff demo build

Run `bash scripts/build-demo.sh` to create `video/build/permitdiff-demo.mp4` plus two 3:2 Devpost
gallery images in `assets/`.

The build reuses the proven IncidentBridge recording pattern: Playwright records the public judge
and evidence surfaces, Kokoro-82M generates subtitle-timed narration, and FFmpeg burns the reviewed
English captions into an H.264/AAC MP4. It never enables live mode and cannot place a phone call.

Before upload, watch the entire video and verify that:

- deterministic outcomes are never described as real permit-office calls;
- the merged PR and current test count are accurate;
- no real-provider result is claimed unless a reviewed public artifact exists; and
- the duration remains below three minutes.
