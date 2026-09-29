# Framing

Every shot is a crop of the original frame, centred on a face, so the video looks multi-camera from one camera. The
framing changes at every cut, which makes pause removal read as deliberate rather than as jump cuts.

All sizes are 4K units (as if the frame were 3840x2160). A 4K camera gives true 1:1 pixels in a 16:9 close-up; a 1080p
camera works, but the close-up is enlarged 2x and looks softer.

## 16:9 (`"format": "wide"`)
- The cycle is medium (1.33x, biased towards the speaker), close (2x, nudged away from the other person), wide, close.
- A speaker change restarts the cycle; a new speaker's shot under 1.5 s goes wide.
- Long unbroken speech is split at its widest word gap near the middle every 7 s at most, so the framing still changes.
- One person to camera: the close shot stays centred.

## 9:16 (`"format": "reel"`)
- Full-height (1216x2160) and punch-in (960x1708, 1.27x) alternate, centred on the talker's face.
- Long speech is split every 5 s at most.

## Half-and-half (two people)
During a quick back-and-forth (3 or more speaker changes, every turn under 5 s and every handover under 1.2 s), both people
are shown at once. Both halves are crops of the same frame, so they stay in sync.
- **16:9:** side by side, each half a 1152x1296 crop shown at 960x1080, alternating with the wide shot. The crop is tight
  enough that the other person's shoulder stays out of each half.
- **9:16:** stacked, each half a 1152x1024 crop shown at 1080x960, alternating with the talker's own shot. The `top`
  setting picks who sits on top. The top face sits lower (clear of the app's header) and the lower face higher (clear of
  the bottom text). Captions move onto the seam.
- **Seam:** `seam` sets the line's colour, or `"none"`.
- The detector reads the transcript, not where heads are turned. Check the moments by eye, and keep template beats out of
  stacked shots, where they would cover a face.

## Both on screen (two people, Whisper)
With `"speakers": {"speaker_0": "both"}` there's no talker to follow, so the whole edit is treated as back-and-forth:
16:9 alternates side by side and wide; reels are stacked throughout.

## Faces
`faces` runs macOS Vision on a frame every 2 s. People sitting left and right are split at the middle of the frame; faces
smaller than 200 (4K units) are ignored (photos or posters in the background). A solo speaker gets every face, but faces
more than 350 from their usual spot are dropped (standing up, reaching across the desk). When a moment has no detection
nearby, the median position (`face_fallback`) is used. Three or more people, or a moving camera, aren't supported.
