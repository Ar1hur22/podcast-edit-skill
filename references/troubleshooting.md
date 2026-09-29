# Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| Intake says STOP | The file isn't one landscape 16:9 video stream with audio, or the time window is wrong | Read the listed problems. Portrait phone footage and multi-stream files aren't supported. `--accept-risk` only if the host agrees. |
| "not transcribing again" | A transcript already exists, or another project transcribed an overlapping part of the same file | Reuse it: set `paths.transcript` and the same `window` start. Delete the old transcript only if you really mean to pay again. |
| ElevenLabs request failed | Missing or wrong key in `.env`, no credits, or the network | Fix the cause and re-run. The pipeline never switches service by itself. |
| Whisper failed | whisper-cpp isn't installed, or the first run is still downloading its model | `brew install whisper-cpp`, then re-run. |
| Whisper edit keeps pauses | A noisy recording: the quiet stretches aren't quiet enough to detect | Cut them with `exclude` ranges, or use ElevenLabs for that recording. |
| "speakers must map ..." | A transcript label isn't in `speakers` | Run `speakers`, look at `work/speakers.png`, map every label. |
| "faces were not found on both sides" | Two people, but only one side's face was detected | Check `work/frames-2s/`; set `face_fallback` by hand in 4K units, or map the recording as one person. |
| A crop looks off-centre | Face detection drifted, or the person moved | Check that moment's frames; set `face_fallback` by hand if the median is wrong. |
| Grey, flat footage | Log footage without a camera LUT | Set `grade.camera_lut` (make-it-yours.md). |
| Colours too contrasty or orange | A camera LUT on footage that was already Rec.709 | Set `grade.camera_lut` to null. |
| "edits.json changed since ..." | `edits --rebuild` after `media` | Move the named files aside and re-run `media`; unchanged shots are reused. |
| "phrase not found" in `captions` | A beat's `at`/`until` words aren't in the edit as spoken | Copy the words from the cut report's remaining text; a longer phrase helps when a short one repeats. |
| "has no setting called ..." | A beat sets a value the template doesn't have | Check the spelling against the template's variables. |
| hyperframes check failed | A template or caption page has an error | Read the listed error. Template errors usually mean a style or script outside `<template>`, or an id used twice. |
| Render fails with "Target closed" or a detached frame | The capture browser ran out of memory | Close other heavy work (other renders, `media`) and render again. |
| Loudness note: "true peak limits the gain" | The final file couldn't reach the target without clipping | Usually harmless (within a dB). For a very dynamic recording, lower `loudness` or accept it. |
| verify FAIL on frames | An export from before a re-cut (expected: it no longer matches the current edit), or the render and the cut footage disagree | Old versions: ignore or delete them. The newest one: re-run `captions`, then `render --tag v2`; if it repeats, report the frame rate and HyperFrames version. |
| Captions show a word you cut | Captions come from the cut edit, so the edit wasn't rebuilt | `edits --rebuild`, then `media` (moving files aside as told), `captions`, `render --tag v2`. |
