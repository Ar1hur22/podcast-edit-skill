# Cutting

`edits` builds each edit from the word timings. Everything is in `scripts/edits.py`; the numbers below are its constants.

## What is cut automatically
- **Pauses** longer than 0.45 s, everywhere. Each kept word gets 0.10 s of padding before and 0.18 s after.
- **Fillers:** um, uh, umm, uhm, mm, mm-hmm, er, erm. They are also never captioned.
- **Swears:** the `cutting.swears` list (a default of four common ones; `[]` keeps everything).
- **Cut-off fragments** of three letters or fewer ending in a hyphen ("li-"). Longer restarts ("the--") need a hand `exclude`.
- **Stutters:** the first of an immediate repeat ("the, the"), when the second follows within 1 s. Emphasis ("very, very,
  very") gets caught too: restore it with `keep`.
- Set `cutting.auto` to false to keep swears, fragments and stutters in the audio and captions, and fillers in the audio (fillers are never captioned).

## Tails and cut words
A kept word's padding never reaches into a cut word or an excluded stretch, so a removed "the" never plays on in the
tail of the word before it.

## 16:9 only: no flash shots
In 16:9, a pause cut that would leave a shot under 1 s keeps the pause instead (up to 1.2 s). A shot that is still under
1 s takes the framing of the neighbouring shot nearer in time, so you get a small jump instead of a flip-flop. Reels keep
every pause cut; their pace is faster.

## Clicks and laptop reaches
People who work from notes on a laptop click it at the end of sentences. The click, and the arm reaching for it, should
not be heard or seen. The transcriber doesn't mark clicks, and a click in the 0.18 s tail after a word, or in a short
kept gap, would survive the pause cutter, so `edits` checks both places:
- **Sound:** a sharp 1–3 ms click, 18 dB over the surrounding second, above 3 kHz, quiet either side. The shot then ends
  just before the click, keeping the word's own tail; in a kept gap, the shot is split there.
- **Picture (optional):** set `cutting.laptop` to a box (4K units) over the desk beside the laptop, clear of gesturing hands,
  then run `laptop` once. It records when a hand is there. A shot whose tail runs into a reach (the hand arriving up to
  0.2 s after the shot's end) ends on its last word.
- **Why both:** laptop clicks and mouth clicks sound the same (both 1–3 ms long, 15–33 dB over the background). The picture
  is what finds the reaches. Trimming a mouth click too costs nothing.
- The cut report lists every trimmed shot end with its reason and its time in the finished video. Listen at each one: a
  "click" inside a word's fading tail can clip the word.
- In 16:9 wide shots the laptop may be in frame: check the frames around each reach.

## keep and exclude
Both are source-second ranges inside an edit:
- `"exclude": [[612.4, 614.0]]` cuts a retake, a tangent or a restart. It shows in the cut report as [by hand].
- `"keep": [[312.0, 312.6]]` restores automatic cuts there (emphasis, a deliberate "um"), and skips the click trim.
Rebuild with `edits --rebuild` after changing them.

## Range edges
A range must end at or after its last word's end, or that word is dropped. Transcribers sometimes stretch the last word of
a clip over the silence after it; any word longer than 1.5 s is given an ordinary 0.5 s. End a range just after the speech,
before the speaker moves.

## Whisper
Whisper stretches each word over the pause after it, which would hide every pause. The pipeline measures the audio in 50 ms
steps, finds quiet stretches (the recording's own background level + 14 dB, at least 0.3 s long), and pulls word edges back
to them. It works well on clean recordings; on noisy ones some pauses will survive. Whisper also tends to drop fillers from
the transcript, and a filler that isn't in the transcript can't be cut, so watch Whisper edits in full.
