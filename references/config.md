# project.json settings

One file per project, `projects/<name>/project.json`. `pipeline.py new` creates it from `project.template.json`; later
stages read it. Edit it by hand (or with Claude) at the checkpoints.

**Two kinds of time:** `window`, `edits`, `exclude` and `keep` are **source seconds** (seconds into the camera file).
Template beats in `design` are anchored to **spoken words**, not times.

**4K units:** crop and face positions, `face_fallback` and `cutting.laptop` are written as if the frame were 3840x2160,
whatever the camera's real size. A 1080p camera works the same way; the pipeline converts. On a 4K frame, 4K units are
simply pixels.

| Key | Set by | Meaning |
|---|---|---|
| `name` | `new` | Project name; exports go to `exports/<name>/`. |
| `source` | `new` | The camera file (read-only). |
| `window` | `new` | `[start, end]` of the recording that is transcribed and edited. Its start is the transcript's zero point. |
| `fps` | `new` | The camera's frame rate (a number); `camera.fps` keeps the exact form, e.g. `30000/1001`. |
| `camera` | `new` | What intake found (size, frame rate, colour transfer, log profile, audio channels), its warnings, and any problems accepted with `--accept-risk`. |
| `transcription` | you | `engine`: `"elevenlabs"` (paid, speaker labels) or `"whisper"` (free, local, one label). `whisper_model`: `small.en` (English, default), `medium.en` (slower, better on noisy audio), or `small`/`large-v3` with `language` (e.g. `"es"`) for other languages. |
| `grade` | you | `camera_lut`: the camera maker's log to Rec.709 LUT (a `.cube` path, absolute or relative to the project), or null for normal footage. `look_lut`: your own look, applied after it, or null. `vignette`: 0 (off) to about 0.3. See `make-it-yours.md`. |
| `speakers` | you, after `speakers` | Speaker label to side: `{"speaker_0": "R", "speaker_1": "L"}`. One person: map every label to their side. Two people with Whisper: `{"speaker_0": "both"}`. |
| `people` | you | Who sits where, for your notes and plans only: `{"L": "host, blue shirt"}`. Never shown on screen. |
| `top` | you | Which side (`"L"` or `"R"`) sits on top in stacked 9:16 half-and-half shots. |
| `seam` | you | The line between the two halves: a colour like `"#FFFFFF"`, or `"none"`. |
| `face_fallback` | `faces` | Median face centre per side (4K units), used when detection misses a moment. Set by hand if needed. |
| `captions.fixes` | brief | Word replacements for misheard names and spelling: `{"colors": "colours"}`. Matching ignores trailing punctuation, and a lower-case key also fixes the capitalised word. A fix can't add or remove punctuation. |
| `captions.merge` | brief | `[first, starts_with, replacement]`: a split word captioned as the real term, e.g. `["physio-", "therapy", "physiotherapy"]`. The audio stays as spoken. |
| `captions.style` | you / studio | The caption look. See the table below. |
| `claims` | you | `"ahpra"`, `"general"` or `"off"`: what the brief flags (SKILL.md stage 5). |
| `cutting.auto` | template | `true`: fillers, swears, cut-off fragments and the first of a stutter are cut from the audio. `false` keeps them all in the audio and the captions (fillers are never captioned). |
| `cutting.swears` | you | Words cut automatically. Default: four common swear words. `[]` keeps every word. |
| `cutting.laptop` | you, before `laptop` | `[x0, y0, x1, y1]` in 4K units: the desk beside a laptop, clear of gesturing hands. Leave out when there's no laptop. |
| `loudness` | template | Integrated LUFS target for finished files: `{"reel": -14, "wide": -14}`. |
| `logo` | you | Optional corner logo: `{"file": "/path/logo.png", "corner": "top-right", "width": 0.12, "margin": 0.04, "opacity": 0.9}`. `corner` is `top`/`bottom` + `-left`/`-right`; `width` is a share of the frame width; `margin` a share of the height. |
| `templates_dir` | you / studio | A folder holding your own templates (see `templates.md`). The project's own `templates/` folder is searched first, then this, then the skill's example. |
| `edits` | brief (approved) | `{name: {"format": "reel" or "wide", "ranges": [[a, b], ...], "exclude": [[a, b]], "keep": [[a, b]]}}`. Ranges are in time order with no overlaps (reordering isn't supported). `exclude` cuts extra stretches (shown as [by hand] in the cut report); `keep` restores automatic cuts that were deliberate. |
| `design` | beat plan (approved) | Per edit, a list of template beats. Format in `templates.md`. |
| `paths` | rarely | Override file locations: `transcript`, `audio`, `speech`, `faces`, `laptop`, `exports`. Relative paths are from the workspace root. Used to reuse another project's transcript or faces. |

## captions.style

| Key | Default | Meaning |
|---|---|---|
| `font` | `"Inter"` | Font family. HyperFrames bundles common open fonts (Inter, Roboto, Montserrat and others) automatically. Any other font needs `font_file`. |
| `font_file` | null | Path to a `.woff2`, `.ttf` or `.otf` you're licensed to use; it's copied into the page. Never commit commercial fonts to a public repo. |
| `weight` | 800 | 100–900. |
| `uppercase` | false | All capitals. |
| `size_wide`, `size_reel` | 64, 70 | Font size in pixels on the 1920x1080 and 1080x1920 frames. |
| `colour` | `"#FFFFFF"` | Caption text. |
| `highlight` | `"#FFD84D"` | The word being spoken. Set it to the same as `colour` for no highlight. |
| `outline` | `"#000000"` | Outline around the letters, for legibility on any background. |
| `max_words`, `max_chars` | 4, 26 | Most words and characters on screen at once. Groups also break at sentence ends, pauses and speaker changes. |
| `position_wide`, `position_reel` | 0.86, 0.72 | Where the caption's centre sits, as a share of the frame height from the top. Keep reels clear of the app's bottom text (about 0.80 and below). In stacked 9:16 shots, captions always move to the seam (0.5). |
