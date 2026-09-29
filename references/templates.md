# The template studio

A one-off session (about an hour) where Claude helps the host design **3-4 animated templates of their own**, builds them,
tests them on their footage, and records how to use them. Run it before the first real edit, or whenever they want a
fresh look. Every template is theirs: invented around their audience and brand, not copied from another creator.

## Step 1: the interview (one question at a time)
1. **Who watches, and where?** Reels, YouTube, a course platform? Who is the viewer, and what do they come for?
2. **Three words for the feel.** e.g. "calm, credible, warm" or "bold, fast, cheeky".
3. **What they already own:** brand colours (hex codes), fonts, a logo, a caption style they like.
4. **What they explain most.** Numbers and statistics? Steps and routines? Myths people believe? Comparisons? Definitions of
   terms? Stories? Questions from their audience?
5. **What they never want to see.** e.g. emojis, anything cheesy, busy screens, sound effects.
6. **Creators whose videos they like, and why.** Take the *feeling* ("clean", "playful"), never the design itself.

Summarise the answers back in three lines and get a yes before designing.

## Step 2: ideas
Propose about six ideas that fit their answers (a name, one line on what it does, and when to use it), then let them pick
3-4 or invent their own. Draw a quick still of each shortlisted idea (a HyperFrames snapshot of a rough version) so they
choose from pictures, not descriptions. A starting menu:

| Idea | What happens | Best for |
|---|---|---|
| **Stat counter** (built, `templates/stat-counter.html`) | a number counts up to the figure being said, with a short label | statistics, results, "3 in 4 people" |
| **Highlighter swipe** | the key phrase appears and a marker sweeps across one word | the one line they want remembered |
| **Myth to fact** | a claim appears, is struck through, and flips to the truth | debunking common beliefs |
| **Sticky note** | a paper note slaps onto a corner with a one-line tip | quick tips, reminders, homework |
| **Step tracker** | a horizontal 1-2-3 track fills as they move through steps | routines, processes, "three things" |
| **Comment bubble** | a social-comment sticker with the audience question being answered | Q&A videos, replies |
| **Rubber stamp** | one word (MYTH, KEY, DON'T) thuds on with a small shake | punchy emphasis, sparingly |
| **Chapter bar** | a thin strip at the top with a progress line ("Part 2 of 3: Sleep") | longer 16:9 videos |
| **Definition card** | a dictionary-style entry for a term: word, how to say it, a plain meaning | jargon, anatomy, technical terms |
| **Before / after** | two short phrases with a line that wipes from one to the other | changes, results, reframes |

Shape the ideas to the brand, not the other way round: rounded or sharp corners, flat or paper or glass texture, snappy
(0.2 s, overshoot) or gentle (0.5 s, ease-out) motion, one accent colour or two.

## Step 3: build each template
Each template is one HyperFrames sub-composition file, `<name>.html`, in their look folder's `templates/`. Use
`templates/stat-counter.html` as the pattern, and load the HyperFrames skills (`/hyperframes-core`, `/hyperframes-animation`)
before writing one. The contract:
- **Variables** go on the `<html>` element (`data-composition-variables`), each with a useful default: the text, numbers
  and colours. Brand colours are defaults, so a beat only sets what changes.
- **`duration` is always passed in** (seconds on screen): use it to fade out just before the end.
- **Everything inside `<template>`**, including `<style>` and `<script>`. The root is `<div id="root" data-composition-id="<name>">`,
  styled by `#root`, and the timeline is registered as `window.__timelines['<name>']`.
- **Classes, not ids:** HyperFrames scopes `document.querySelector` and `getVariables()` to each copy, so the same template
  can appear several times on a page.
- **One size for both formats:** `captions` gives each edit's copy of a template that edit's size, so leave
  `data-width`/`data-height` off the template's root. Size with `vmin`, position with percentages, and use
  `@media (orientation: portrait)` for a different reel layout (the stat counter sits top left in 16:9 and under the face in 9:16).
  Keep it clear of faces and of the caption band, or set `"captions": false` on its beats.
- **Seekable and repeatable:** `gsap.fromTo` for entrances, no `Math.random`, no clocks, no network calls, no infinite repeats.
- **Fonts:** HyperFrames bundles common open fonts; anything else needs an `@font-face` to a font file in the template's folder.

Check each one before showing it: put two copies with different values on a small test page, run
`npx --yes hyperframes@0.8.91 check <folder>`, then `snapshot --at <mid-points>`, and confirm each copy shows its own
values. Show the host a still and a 3-second clip; adjust until they're happy.

## Step 4: test on real footage
Pick 20-30 s of one of their recordings, make a short edit, and add one beat of each template to its `design`. Run
`captions` and `render`, and watch it with the host at full speed (on a phone for reels). Check that nothing covers a face,
nothing fights the captions, and it still feels like them.

## Step 5: save it
- Keep the templates in their look folder and set `templates_dir` in each project (or in their own project template).
- Record each template in their look skill (see `make-it-yours.md`): its name, what it's for, when to use and not use it,
  its settings, and an example beat.

## The `design` format
Per edit, a list of beats in the order they happen. Each beat is anchored to words as spoken in the edit (the cut report
shows the remaining text), searched in order, so a repeated phrase picks the next occurrence after the previous beat.

```json
"design": {
  "reel-1-sleep": [
    {"template": "stat-counter", "at": "three in four", "until": "sleep badly", "hold": 0.6,
     "values": {"value": 75, "suffix": "%", "label": "sleep badly"}},
    {"template": "sticky-note", "at": "try this tonight", "seconds": 3, "values": {"text": "Screens off at 9"}, "captions": false}
  ]
}
```

(`sticky-note` stands for a template you'd build in the studio; only `stat-counter` ships with the skill.)

- `at`: the words where it appears. `until`: the words it stays up through, plus `hold` seconds (default 0.6). Without
  `until`, it lasts `seconds` (default 3).
- `values`: the template's settings for this beat. A setting the template doesn't have prints a note (usually a typo).
- `"captions": false`: hide captions that start during the beat (for full-screen templates).
- **Planning rules:** a few beats per minute at most, never over the opening face, not in stacked 9:16 shots, and not two
  at once unless they're designed to share the screen.
