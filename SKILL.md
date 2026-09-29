---
name: podcast-edit-skill
description: "Turns a camera recording of one or two people talking (a podcast, an interview, a course lesson, a YouTube video to camera) into finished 9:16 reels and 16:9 videos, end to end, with approval checkpoints: camera check, transcription (ElevenLabs Scribe or free local Whisper), speaker mapping, optional colour grade from your own LUTs, automatic cutting of pauses, fillers, stutters and swears, face-centred 9:16 and 16:9 framing with half-and-half shots for back-and-forth, word-by-word HyperFrames captions in your own style, your own animated templates, loudness at -14 LUFS, and final file checks. Also runs a one-off 'template studio' that helps the host design 3-4 animated templates and a caption style of their own. Use it whenever someone wants to edit, cut or caption a podcast or talking-head recording, make reels or clips from one, or design their own caption style, templates or look for those videos."
---

# Podcast edit skill

From a camera file to finished reels and 16:9 videos. The scripts do the heavy lifting; you (Claude) run them, read their
output, and stop at the 🛑 checkpoints so the host can approve before anything expensive or hard to undo happens.

## Before you start
- **Where to work:** a workspace folder the host chooses, holding `projects/`, `exports/` and `.env`. Run every command from
  its root:

  ```bash
  python3 <this skill>/scripts/pipeline.py <stage> projects/<name> [...]
  ```

  Use the workspace's own virtual environment's Python if it has one (see README: it needs `elevenlabs` and `python-dotenv`
  for ElevenLabs). `pipeline.py --help` lists the stages.
- **Source footage is read-only.** Nothing is written next to it. Outputs go to `projects/<name>/` and `exports/<name>/`.
- **Main outputs are never overwritten** (transcript, faces, edits, footage, renders, exports), so re-running is safe. To
  redo one, delete or rename the file deliberately. Preview images are regenerated.
- **Tools:** FFmpeg, HyperFrames (run through `npx`, pinned in `pipeline.py`), `swift` for macOS Vision face detection,
  and `whisper-cpp` if using Whisper. The README covers installing them.
- **The host:** explain in plain language, show a plan before big steps, and use their spelling conventions in captions.
- **One project, one session.** Two sessions writing to the same project overwrite each other's files.

## The stages

🛑 = checkpoint: stop, show the host the named file or plan, and wait for their OK. A wrong grade or a bad cut would
otherwise be baked into every video.

| # | Stage | Command | The host sees |
|---|---|---|---|
| 0 | Questions | (none) | the questions below |
| 1 | Intake | `new projects/<name> --source <file> --start <s> --end <e>` | only if it stops or warns |
| 2 | Transcribe | `transcribe projects/<name>` | minutes sent (ElevenLabs) or the Whisper trade-offs |
| 3 | Who's who | `speakers projects/<name>` | nothing, unless it's unclear |
| 4 | Face positions (about 2 min per minute of 4K footage) | `faces projects/<name>` | nothing |
| 5 | 🛑 Brief | read `transcript/transcript.md`; `find` gives exact edges | clip topics, ranges, claims flags, caption fixes |
| 6 | 🛑 Grade (skip if no grade is set) | `stills projects/<name>` | `work/grade-check.png` |
| 6b | Laptop reaches (optional) | `laptop projects/<name>` | nothing |
| 7 | 🛑 Cuts | `edits projects/<name>` | `cut-report.md` |
| 8 | Footage (slow) | `media projects/<name> [edit…]` | nothing |
| 9 | Captions (+ 🛑 beat plan if using templates) | `captions projects/<name> [edit…]` | the beat plan |
| 10 | 🛑 One test render, then the rest | `render projects/<name> <edit>` | the test file, then the finals |
| 11 | Wrap-up | `verify projects/<name>` | final files and a short summary |

**0. Ask first, one question at a time where you can:**
- **What is it?** Two people (podcast, interview) or one person to camera (course, YouTube)?
- **What should come out?** 9:16 reels (40–80 s, one idea each), 16:9 videos, or both?
- **Transcription:** ElevenLabs Scribe (paid, about US$0.22 per hour of audio as of Sep 2026, labels who is speaking) or local
  Whisper (free, private, but no speaker labels, it often misses fillers, and word edges are rougher). Set
  `transcription.engine` to `elevenlabs` or `whisper`. For non-English audio with Whisper, use `"whisper_model": "small"`
  and set `"language"` (the `.en` models translate everything into English).
- **Whisper with two people:** Whisper can't tell who is talking, and the framing depends on that. Give the host both options:
  1. **Switch to ElevenLabs** (recommended): framing follows the talker, with half-and-half shots during quick back-and-forth.
  2. **Carry on with "both on screen":** set `"speakers": {"speaker_0": "both"}`. 16:9 alternates the side-by-side shot with
     the wide shot; reels use the stacked shot throughout. It never follows the talker.
- **Claims check** (`claims`): `ahpra` for Australian registered health practitioners, `general` for everyone else, or `off`.
- **Their look:** have they set up a caption style and templates? If not, offer the template studio
  (`references/templates.md`) before the first real edit, or use the plain defaults for now.
- Check for earlier work on the same file (other folders in `projects/`). If it was already transcribed, reuse that transcript
  (below) rather than paying again.

**1. Intake.** Ask which part of the recording to use; times are in source seconds.
- **It stops on:** more than one video stream, footage that isn't landscape 16:9 (including rotated phone footage), no audio, or
  a bad time window. Explain what's different in plain words; only re-run with `--accept-risk` if the host agrees.
- **It warns on:** footage below 4K (close-ups are enlarged, so softer), frame rates other than 25p (supported, tuned on 25p),
  HDR, and log footage detected from a Sony sidecar file. For any log profile (S-Log, C-Log, V-Log, LogC, N-Log), the host
  needs the camera maker's LUT before stage 6.
- **It writes:** `project.json`, a 48 kHz mastering WAV and a 16 kHz mono WAV for transcription.

**2. Transcribe.**
- **ElevenLabs:** only the 16 kHz mono window is uploaded. It won't re-send if a transcript exists, it stops if another
  project in the workspace already transcribed an overlapping part of the same file, and it stops (rather than switching to
  anything else) if the key is missing or credits run out. It never prints the key. Tell the host how many minutes are sent.
- **Whisper:** runs on the Mac through HyperFrames. Word edges are pulled back to where the audio actually goes quiet, so the
  pause cutter still works, but watch Whisper edits in full: its timings are rougher than Scribe's.
- **Reusing a transcript:** in project.json set `"paths": {"transcript": "<path to words.json>"}` and give `window` the same
  start as that transcript (its times count from the window start). Then skip this stage.

**3. Who's who.** `work/speakers.png` shows three frames per moment for each speaker label; the talker is the one whose mouth
moves. Set `"speakers": {"speaker_0": "R", "speaker_1": "L"}` and, for your own notes, `"people"`. ElevenLabs reshuffles
labels on every run, so never copy a mapping from another project. **One person to camera:** map every label to the side
their face is on; the face track then takes every face and ignores standing up or reaching across the desk. Three or more
people, or a moving camera, isn't supported: say so.

**4. Face positions.** Samples a frame every 2 s and writes the median face centre per side into `face_fallback` (4K units).
Check both people were found. Start it and carry on with the brief.

**5. 🛑 Brief.** Read `transcript/transcript.md` and propose:
- **Clips:** for reels, 40–80 s, one idea each, opening on a strong line with a face as the first shot. Give each its source
  ranges (`find` prints exact times for a phrase).
- **Claims** (per `claims`). **Flag, never trim:** the host decides, and this is a prompt to review, not legal advice.
  - `ahpra`: under AHPRA's advertising rules for regulated health services, flag testimonials or patient success stories used
    to promote; claims of cure, success rates or percentages; anything that creates an unreasonable expectation of benefit;
    treatment claims outside the profession's accepted evidence or scope; anything encouraging unnecessary or indiscriminate
    use of services; comparisons claiming superiority; offers or discounts without their terms; and anything misleading.
    Give each clip a low / medium / high risk level.
  - `general`: health, money and legal claims; guarantees and percentages; named people or businesses (endorsement or
    defamation risk); anything the host might not want public.
- **Caption fixes:** misheard names and local spelling as `captions.fixes` (global, so a fix changes every use of that
  word). Check any study or author they name. Split words ("physio-" + "therapy") go in `captions.merge`.
- **Retakes:** use the later take; cut the earlier one with `exclude`.
- **Course material:** a reel must stand alone. Trim references to other lessons with `exclude` where no claim is involved,
  and point out that reels give course material away.
- **After approval,** write the ranges into `project.json` `edits` (`"format": "reel"` or `"wide"`). Ranges in an edit must
  be in time order. All settings: `references/config.md`.

**6. 🛑 Grade.** `work/grade-check.png`: left is before the look (as shot, or the camera LUT only), right is the full grade.
Never apply a camera LUT to footage that is already graded, and never grade HDR as if it were SDR. With no grade set, say
so and move on. How to build a look: `references/make-it-yours.md`.

**6b. Laptop reaches (optional).** If the host clicks a laptop on the desk while talking, set `cutting.laptop` to a box (4K
units) over the desk beside it, clear of their gesturing hands, and run `laptop`. `edits` then ends any shot whose tail runs
into a reach. Clicks in the sound are caught either way. See `references/cutting.md`.

**7. 🛑 Cuts.** `cut-report.md` lists every removed word (automatic removals, and hand removals marked [by hand]), every shot
end trimmed for a click or reach (with its time in the finished video: listen there), and the text that remains.
- Pauses over 0.45 s, fillers, cut-off fragments, the first of a stutter and the swear list (`cutting.swears`) are cut.
- Flag "repeat" cuts that might have been deliberate emphasis; `keep` ranges restore them. `exclude` ranges cut more. Both
  are in source seconds. Rebuild with `edits --rebuild`.
- A range must end at or after its last word's end, or that word is dropped. End it just after the speech.
- Rules and reasons: `references/cutting.md`.

**8. Footage.** Graded, cut, face-centred footage per edit in `<project>/<edit>/assets/speaker.mp4`, framing changing at
every cut, dialogue mastered to the loudness target. It's slow (several minutes per minute of 4K); keep the camera drive
connected. Framing rules: `references/framing.md`.

**9. Captions and templates.** `captions` writes `<project>/<edit>/index.html`: the footage, word-by-word captions in the
host's `captions.style`, an optional corner `logo`, and any template beats in `design`.
- **🛑 Beat plan (only when using templates):** for each edit, list each beat: the template, the words it starts and ends on,
  and its text. Keep beats sparse (a few per minute), and keep them out of stacked 9:16 shots, where they would cover a face.
  After approval, write them into `design` (format in `references/templates.md`) and run `captions` again.
- **Before rendering, check every beat covers no face:** `npx --yes hyperframes@0.8.91 snapshot projects/<name>/<edit> --at <each
  beat's midpoint>` and look. No position is safe in every shot (top left is clear of a centred close-up but can touch the
  left person in a wide two-shot). Move a beat to other words, or set its template's position settings (the stat counter
  has `top` and `align`).
- Preview any page in the browser with `npx --yes hyperframes@0.8.91 preview projects/<name>/<edit>`.

**10. 🛑 Render one, check it, then the rest.** `render` runs HyperFrames' check, renders at the camera's frame rate, adds
BT.709 colour tags, corrects loudness on the final file, copies the SRT next to it and verifies the file. Watch the test
file with the host. Use `--tag v2` for a new version rather than overwriting. Don't run other heavy stages during a render.

**11. Wrap-up.** Run `verify`. Send the host the final files with a plain summary: what was made, lengths, claims flags,
anything to check by eye (Whisper timing, repeat cuts, trimmed shot ends). Never publish or upload anything; the host posts.

## Rules
- **Faces first:** every reel opens on a face.
- **Claims are flagged, never silently trimmed.**
- **Loudness:** -14 LUFS for both formats, measured on the final file (`loudness` changes it).
- **Nothing added on screen that the host didn't choose:** no logo, names, music or end card unless they set them up.

## Gotchas
- **Colour tags:** x264 drops them; the pipeline adds them back with a bitstream filter. Keep it.
- **Loudness:** the renderer turns mono dialogue into stereo, about 3 LU louder; `render` measures the final file and corrects it.
- **Speaker labels** differ on every ElevenLabs run, and so does which side each person sits.
- **Restart markers vary:** a transcriber may write "it's-" or "on--". Captions hide trailing hyphens and short fragments
  ("li-") are cut automatically; longer restarts ("the--") need a hand `exclude`.
- **Face detection:** Vision can't see eyes looking down with the head level, and a speaker's detected position can drift;
  check crops that look off-centre.
- **Re-cuts reuse unchanged shots:** after `edits --rebuild`, `media` asks you to move `video.mp4`, `audio.wav` and
  `speaker.mp4` aside; only changed shots re-encode.
- **FFmpeg `-t` binds to the next input:** put `-ss`/`-t` before the input they're for.
- **Template ids:** inside a template, HyperFrames scopes `document.querySelector` and `getVariables()` to that copy. Use
  classes, not ids, so the same template can appear several times on one page.
- More fixes: `references/troubleshooting.md`.

## References
- `references/config.md`: every project.json setting.
- `references/cutting.md`: pauses, fillers, clicks, laptop reaches, keep and exclude.
- `references/framing.md`: face-centred crops, the half-and-half, stacked shots, both-on-screen mode.
- `references/make-it-yours.md`: your own grade, caption style, branding and motion graphics.
- `references/templates.md`: the template studio (design 3-4 templates of your own) and the `design` format.
- `references/troubleshooting.md`: when something stops or looks wrong.
