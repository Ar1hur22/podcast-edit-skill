# podcast-edit-skill

A [Claude Code](https://claude.com/claude-code) skill that turns a camera recording of one or two people talking
(a podcast, an interview, a course lesson, a video to camera) into finished **9:16 reels** and **16:9 videos**. Claude runs
the steps and stops at checkpoints so you approve the important decisions before they're baked in.

## What it does
- **Checks the camera file**: one landscape 16:9 video stream with audio; warns about sub-4K footage, frame rates other than 25p and HDR, and about log
  footage when the camera's sidecar file says so (Sony). For other log cameras, you tell it.
- **Transcribes**: ElevenLabs Scribe (paid, knows who is speaking) or Whisper on your Mac (free, private).
- **Cuts automatically**: pauses over 0.45 s, "um"s and "uh"s, stutters, cut-off words, an optional swear list, and laptop
  clicks or reaches at the end of sentences. A cut report shows every word removed, so nothing disappears unseen.
- **Frames like a multi-camera shoot from one camera**: face-centred crops that change at every cut, with side-by-side
  (16:9) or stacked (9:16) half-and-half shots when two people go back and forth.
- **Grades** with your own LUTs (optional).
- **Captions** word by word in your own style (font, colours, highlight, size, position), plus an SRT file.
- **Templates**: your own animated graphics (a statistic counting up, a highlighted phrase...) placed at the words you choose.
  A guided "template studio" helps you design 3-4 of your own.
- **Finishes properly**: -14 LUFS loudness measured on the final file, BT.709 colour tags, and a file check on every export.
- **Flags risky claims** at the planning stage: AHPRA rules for Australian health practitioners, a general check, or off.
  It flags; you decide.

It does **not** publish anything, handle three or more people or a moving camera, or cut between multiple cameras. It needs
**macOS** (face detection uses Apple's built-in Vision framework).

## Cost
- **ElevenLabs Scribe v2:** US$0.22 per hour of audio on the pay-as-you-go API price (checked 29 Sep 2026; paid plans include
  hours). Only a 16 kHz mono copy of the part you choose is uploaded, and the skill refuses to transcribe the same audio twice.
- **Whisper:** free, and the audio never leaves your Mac. It can't tell speakers apart, often leaves "um"s out of the
  transcript (so they can't be cut), and its word timings are rougher. Best for one person to camera.
- Everything else runs on your Mac for free.

## Requirements
- macOS with [Homebrew](https://brew.sh), and [Claude Code](https://claude.com/claude-code).
- **FFmpeg:** `brew install ffmpeg`
- **Node.js 22 or newer** (for HyperFrames, which builds the captions and renders): `brew install node`
- **Swift** (for face detection), from Apple's command line tools: `xcode-select --install`
- **Python 3.9 or newer** (macOS has one) with two packages for ElevenLabs: see Install.
- **For Whisper:** `brew install whisper-cpp`. The first transcription downloads the model (about 470 MB for `small.en`).
- The first render downloads a headless Chrome for HyperFrames (a one-off, a few hundred MB).
- Disk space: several GB per hour of 4K footage for the working files.

## Install
```bash
git clone https://github.com/Ar1hur22/podcast-edit-skill ~/.claude/skills/podcast-edit-skill
```

Then make a workspace folder for your projects:

```bash
mkdir -p ~/video-work && cd ~/video-work
python3 -m venv .venv
.venv/bin/pip install -r ~/.claude/skills/podcast-edit-skill/requirements.txt
```

For ElevenLabs, create `~/video-work/.env` containing one line, `ELEVENLABS_API_KEY=<your key>`. Keep it private: never
paste the key into a chat, commit it, or share the folder with it inside.

## First run
Open Claude Code in your workspace (`cd ~/video-work && claude`) and say something like:

> Edit my podcast. The file is ~/Movies/episode-12.mp4, use 10:00 to 25:00, and make reels plus a 16:9 version.

Claude will then:
1. **Ask a few questions:** one or two people, which outputs, ElevenLabs or Whisper, which claims check, and whether you
   want to set up your own caption style and templates first.
2. **Check the file**, then **transcribe** (telling you how many minutes are sent to ElevenLabs).
3. Work out **who sits where** and **find the faces**.
4. 🛑 **Show you a brief:** proposed clips with their exact ranges, flagged claims, and caption spelling fixes.
5. 🛑 **Show the grade**, if you've set one: before and after stills.
6. 🛑 **Show the cut report:** every word removed, for you to check or restore.
7. Cut and grade the footage, build the caption pages and, 🛑 if you use templates, show you where each one goes.
8. 🛑 **Render one test video** for you to watch, then the rest.
9. Check every file and give you a summary. The videos are in `exports/<project>/`, each with an `.srt` beside it.

Each 🛑 is a stop: nothing expensive or hard to undo happens until you say yes.

## Make it yours
Out of the box the look is deliberately plain: white captions with a yellow highlight, no grade, no logo. See
[`references/make-it-yours.md`](references/make-it-yours.md) for your own grade (including making a look LUT for free in
DaVinci Resolve), caption style, branding and motion graphics, and [`references/templates.md`](references/templates.md)
for the template studio. When your look is settled, Claude can save it as a small skill of your own, so every session
uses it.

## Running the steps by hand
```bash
.venv/bin/python ~/.claude/skills/podcast-edit-skill/scripts/pipeline.py --help
```

Run it from your workspace with the workspace's `.venv/bin/python` (plain `python3` works too, except for ElevenLabs
transcription, which needs the two packages in the venv).

Each step is one command (`new`, `transcribe`, `speakers`, `faces`, `stills`, `edits`, `media`, `captions`, `render`,
`verify`), driven by `projects/<name>/project.json`. Every setting is described in
[`references/config.md`](references/config.md).

## What's been tested
- A two-person podcast from a Sony camera in 4K 25p S-Log3, with the camera maker's LUT and an ElevenLabs transcript: a 16:9
  edit with two template beats, and a 9:16 reel with stacked shots.
- The same footage converted to 1080p at 29.97 fps in normal Rec.709 (no LUT), transcribed with Whisper in
  "both on screen" mode.
- Whisper on one person to camera.

The ElevenLabs request itself wasn't re-run during testing (an existing transcript was reused, to avoid paying twice).
Other cameras, frame rates and rooms should work but haven't been tried. The self-checks run with
`python3 scripts/edits.py`, `python3 scripts/captions.py` and `python3 scripts/grade.py`.

## Licence
MIT. HyperFrames (Apache-2.0), FFmpeg, whisper.cpp and the ElevenLabs SDK are installed separately under their own licences.
