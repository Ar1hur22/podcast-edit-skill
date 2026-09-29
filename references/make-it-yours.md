# Make it yours

The skill ships deliberately plain: no grade, white captions with a yellow highlight, no logo, and one example template.
This guide shows how to give your videos your own look. You can do all of it by asking Claude, for example: "use the
make-it-yours guide to set up my grade" or "run the template studio".

Keep everything that makes up your look (LUTs, fonts, logo, templates, notes) in **one folder of your own**, e.g.
`~/my-look/`. Point `templates_dir` at its `templates/` folder, and your LUT and font settings at its files.

## 1. Your grade

**First, know your footage.**
- **Standard picture profile** (most phones, and cameras not set to log): the footage is already Rec.709. Leave
  `grade.camera_lut` as null. A look LUT is optional.
- **Log profile** (S-Log, C-Log, V-Log, LogC, N-Log, F-Log): the footage looks flat and grey until it's converted. Download
  your camera maker's official log-to-Rec.709 LUT from their support site, and set `grade.camera_lut` to its `.cube` file.
  Download it yourself rather than taking a copy from someone else, so you have the right version for your camera settings.
- **HDR (HLG/PQ):** not supported. Record in SDR, or convert first.

**Then, optionally, a look.** A look LUT is applied after the camera LUT. It's your colour signature: warmer or cooler,
deeper blacks, softer highlights, how skin sits. The free way to make one is DaVinci Resolve:
1. Import a representative clip, the same room, lights and camera settings you usually use.
2. On the Color page, apply your camera LUT in the first node (skip this for standard footage). Grade in the nodes after it:
   balance, contrast, then skin. Check skin on more than one person if you have guests.
3. Turn **off** the camera LUT node, then right-click the clip's thumbnail and choose **Generate LUT** (33 or 65 point cube).
   The pipeline applies the camera LUT itself, so the look LUT must contain only your grade.
4. Set `grade.look_lut` to that file, run `pipeline.py stills`, and compare before and after. Adjust in Resolve and repeat.

A bought LUT pack works the same way, as long as its looks expect Rec.709 input.

**Rules that save grief:** never apply a camera LUT to footage that's already converted; re-check your stills whenever the
room, lights or camera settings change; and keep one look per set rather than tweaking per video. `grade.vignette` (0 to
about 0.3) adds a gentle, band-free darkening towards the corners.

## 2. Your caption style

Every caption setting is in `captions.style` (the full list is in `config.md`). Some starting points:

| Feel | font | weight | colours | words |
|---|---|---|---|---|
| Calm and credible | a clean sans (e.g. Inter) | 600 | white, highlight = white (no highlight) | 5 |
| Energetic | a condensed or heavy sans | 800-900, `uppercase` | white, one bright highlight | 2-3 |
| Warm and personal | a rounded sans | 700 | cream, a soft brand colour | 3-4 |
| Editorial | a serif | 500 | off-white, no highlight | 4-6 |

- **Fonts:** HyperFrames bundles common open fonts (Inter, Roboto, Montserrat and others). For anything else, set
  `font_file` to a font you're licensed to use in video. Never put commercial fonts in a public repository.
- **Legibility:** keep the outline on, keep reels' captions above the app's bottom text (`position_reel` 0.80 or less), and
  check one frame over the brightest background in your footage.
- **Try it fast:** change the style, run `pipeline.py captions`, then preview the page with
  `npx --yes hyperframes@0.8.91 preview projects/<name>/<edit>`. No render needed.
- **Want something more animated?** HyperFrames has ready-made caption styles (`npx --yes hyperframes@0.8.91 catalog --tag caption-style`).
  Using one replaces this skill's caption layer, so ask Claude to adapt `scripts/captions.py`.

## 3. Your branding

Branding works best in the style, not as stickers on top:
- **Colours:** pick one or two brand colours and use them in the caption `highlight` and your templates' accent. Write the
  hex codes down in your look folder.
- **Fonts:** one for captions, at most one more for templates.
- **Logo:** optional. `"logo": {"file": "~/my-look/logo.png", "corner": "top-right", "width": 0.1, "opacity": 0.85}`. Use
  a transparent PNG. A small, quiet corner mark reads as confident; a big one reads as an ad. Check it doesn't sit under the
  app's buttons on reels.
- **Intro or end card:** make it a template (next section) and place it on the first or last words with
  `"captions": false`. Keep the opening shot a face: it's what stops people scrolling.

## 4. Your motion graphics

Motion graphics here are **templates**: small animated pieces (a statistic, a highlighted phrase, a checklist) that
appear at the words you choose. `references/templates.md` is the template studio: a guided process where Claude helps you
design 3-4 templates of your own, builds them, tests them on your footage, and records how to use them.

The process that works:
1. **Decide your look before you build anything:** the audience, three words for the feel, your colours and fonts.
2. **Design a few templates, not many.** 3-4 that fit what you actually explain beat 15 you never use.
3. **Test on 20-30 s of real footage** before using them in a whole video. Watch at full speed, on a phone for reels.
4. **Use them sparingly:** a few per minute, on the moments that matter. Captions carry the rest.

## 5. Save your look as your own skill

When your look is settled, ask Claude to save it as a small skill of your own, e.g. `~/.claude/skills/<your-name>-look/`:
a `SKILL.md` that records your caption style values, colours, fonts, LUT paths, logo, the templates you have (with what
each one is for and its settings), and your rules ("never more than three beats a minute", "no logo on reels"), with the
templates folder beside it. From then on, every editing session loads your look automatically, and this editing skill
stays generic. Keep that skill private if it includes paid fonts or anything you don't want copied.
