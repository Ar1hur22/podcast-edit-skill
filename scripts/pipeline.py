#!/usr/bin/env python3
"""Podcast edit pipeline: one command per stage, driven by <project>/project.json. Run from your workspace root (the folder
that holds projects/, exports/ and .env):   python3 <skill>/scripts/pipeline.py <stage> projects/<name> [...]

  new        check the camera file and set up the project + audio for the chosen window                       (free)
  transcribe ElevenLabs Scribe (PAID, speaker labels) or local Whisper (free, one speaker label) -> transcript
  find       source times of a phrase in the transcript, for exact range edges                               (free)
  speakers   frame strips per speaker label, to decide who sits left / right                                (free)
  faces      face positions every 2 s (macOS Vision) for face-centred crops                                 (free)
  stills     graded vs ungraded stills, for the grade checkpoint                                             (free)
  laptop     hand-at-the-laptop moments inside project.json cutting.laptop (optional)                        (free)
  edits      edit lists, cut report and SRT subtitles from the transcript and project.json                   (free)
  media      graded, cut footage + mastered dialogue into <project>/<edit>/assets/speaker.mp4                (free, slow)
  captions   the HyperFrames caption page (+ your templates) for each edit                                   (free)
  render     check, render, colour tags, loudness to target, verify -> exports/<name>/<edit>.mp4 + .srt      (free, slow)
  verify     final-file checks for exports/<name>/                                                            (free)
Main outputs (transcript, faces, edits, footage, renders, exports) are never overwritten; delete or version them deliberately
to redo a stage. Preview images (speakers.png, grade-check.png) are simply regenerated."""
import argparse, hashlib, json, os, re, shlex, shutil, subprocess, sys
from fractions import Fraction
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edits as E, grade as G, captions as C

HERE = Path(__file__).resolve().parent
FF = G.FF
FFPROBE = str(Path(FF).with_name('ffprobe')) if Path(FF).is_absolute() else 'ffprobe'
# one pinned HyperFrames version (the tested one); set PODCAST_HYPERFRAMES to use another, e.g. "npx --yes hyperframes@latest"
HF = shlex.split(os.environ.get('PODCAST_HYPERFRAMES', 'npx --yes hyperframes@0.8.91'))
MASTER = ('pan=mono|c0=0.5*c0+0.5*c1,highpass=f=70,'
          'acompressor=threshold=0.125:ratio=2:attack=15:release=180:makeup=1.4,'
          'loudnorm=I={I}:TP=-1.5:LRA=9,aresample=48000')
TAGS = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']
BSF = ['-bsf:v', 'h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1']   # x264 drops VUI tags otherwise

# ---------------- helpers ----------------
def load(proj):
    f = Path(proj)/'project.json'
    if not f.exists(): raise SystemExit(f'No {f}. Run: pipeline.py new {proj} --source ... --start ... --end ...')
    return json.loads(f.read_text())

def save(proj, cfg):
    (Path(proj)/'project.json').write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + '\n')

def paths(proj, cfg):
    """Project file locations; project.json "paths" can point elsewhere (e.g. to reuse another project's transcript)."""
    d, p = Path(proj), cfg.get('paths', {})
    at = lambda k, rel: Path(p[k]).expanduser() if k in p else d/rel
    return {'transcript': at('transcript', 'transcript/words.json'), 'audio': at('audio', 'work/audio-window.wav'),
            'speech': at('speech', 'work/speech-16k.wav'), 'faces': at('faces', 'work/faces.json'), 'laptop': at('laptop', 'work/laptop.json'),
            'edits': d/'edits.json', 'work': d/'work', 'exports': Path(p['exports']) if 'exports' in p else Path('exports')/cfg['name']}

def rate(cfg):
    """The camera's frame rate as FFmpeg writes it ('25/1', '30000/1001'): exact, unlike the float in cfg['fps']."""
    return cfg.get('camera', {}).get('fps') or str(cfg['fps'])

def ff(args, log=None, quiet=False):
    cmd = [FF, '-hide_banner', '-nostdin', '-n', *map(str, args)]
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        with open(log, 'w') as f: subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)
    else:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL if quiet else None, stderr=subprocess.DEVNULL if quiet else None)

def probe(f):
    return json.loads(subprocess.run([FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(f)],
                                     capture_output=True, text=True, check=True).stdout)

def loudness(f):
    t = subprocess.run([FF, '-hide_banner', '-nostats', '-i', str(f), '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', t)[-1]), float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', t)[-1])

def fmt_t(t): return f'{int(t//60)}:{t%60:04.1f}'

def click_env(P):
    """1 ms peaks of the window audio above 3 kHz, for edits.clicks() (a few seconds per 10 minutes)."""
    from array import array
    raw = subprocess.run([FF, '-v', 'error', '-i', str(P['audio']), '-af', 'highpass=f=3000,highpass=f=3000', '-ac', '1',
                          '-ar', '48000', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    x = array('f'); x.frombytes(raw[:len(raw)//4*4])
    return [max(max(b), -min(b)) for b in (x[i:i+48] for i in range(0, len(x)-47, 48))]

def levels(f, step=0.05):
    """Loudness in dB of each `step` s of a 16 kHz file (for edits.tighten)."""
    out = subprocess.run([FF, '-v', 'error', '-i', str(f), '-af', f'asetnsamples=n={int(16000*step)}:p=0,astats=metadata=1:reset=1:'
                          'measure_perchannel=none:measure_overall=RMS_level,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-',
                          '-f', 'null', '-'], capture_output=True, text=True, check=True).stdout
    return [float(x.split('=')[1]) for x in out.splitlines() if 'RMS_level=' in x]

def tile(images, out, cols):
    """Contact sheet from (png/jpg path, label) pairs; the labels are printed as a legend, row by row (Homebrew's standard
    FFmpeg has no drawtext, and a legend keeps the install to plain `brew install ffmpeg`)."""
    n = len(images); cols = min(cols, n); rows = (n + cols - 1)//cols
    args = []
    for p, _ in images: args += ['-i', str(p)]
    lab = ';'.join(f"[{i}:v]scale=480:-2[t{i}]" for i in range(n))
    for i in range(n, cols*rows):   # xstack needs a full grid: pad with black tiles
        args += ['-i', str(images[0][0])]; lab += f";[{i}:v]scale=480:-2,drawbox=c=black:t=fill[t{i}]"
    ins = ''.join(f'[t{i}]' for i in range(cols*rows))
    subprocess.run([FF, '-v', 'error', '-y', *args, '-filter_complex', f'{lab};{ins}xstack=inputs={cols*rows}:grid={cols}x{rows}:fill=black[o]'
                    if cols*rows > 1 else lab.replace('[t0]', '[o]'), '-map', '[o]', '-frames:v', '1', str(out)], check=True)
    print(f'{out} ({cols} across), left to right:')
    for r in range(rows):
        print(f'  row {r+1}: ' + ' | '.join(l for _, l in images[r*cols:(r+1)*cols]))

# ---------------- stages ----------------
def cmd_new(a):
    proj = Path(a.project)
    if (proj/'project.json').exists(): raise SystemExit(f'{proj}/project.json exists; this project is already set up.')
    if (Path('exports')/(a.name or proj.name)).exists():
        raise SystemExit(f"exports/{a.name or proj.name} already exists (another project's exports); choose a different project name.")
    src = Path(a.source).expanduser().resolve()
    if not src.is_file(): raise SystemExit(f'Source not found: {src}')
    pr = probe(src)
    vids = [s for s in pr['streams'] if s['codec_type'] == 'video' and s.get('disposition', {}).get('attached_pic') != 1]
    auds = [s for s in pr['streams'] if s['codec_type'] == 'audio']
    dur = float(pr['format']['duration'])
    stops, warns = [], []
    if len(vids) != 1: stops.append(f'{len(vids)} video streams (the pipeline expects one camera, one stream)')
    v = vids[0] if vids else {}
    w, h = v.get('width') or 0, v.get('height') or 0
    turned = any(abs(int(float(d.get('rotation', 0)))) in (90, 270) for d in v.get('side_data_list', []))
    if turned or not h or h > w or abs(w/h - 16/9) > 0.02:
        stops.append(f'{w}x{h}{" (rotated)" if turned else ""} is not landscape 16:9; the framing needs a 16:9 landscape frame')
    elif w < 3840:
        warns.append(f'{w}x{h}: below 4K, so close-ups are enlarged from fewer pixels and will look softer')
    fr = v.get('r_frame_rate', '0/1')
    fps = float(Fraction(fr)) if fr != '0/0' else 0
    if not 10 <= fps <= 120: stops.append(f'frame rate {fr} not understood')
    elif fr != '25/1': warns.append(f'{fps:.3f} fps: supported, but the defaults were tuned on 25p footage')
    if not auds: stops.append('no audio stream')
    if v.get('color_transfer') in ('arib-std-b67', 'smpte2084'):
        warns.append('HDR footage (HLG/PQ): the grade expects SDR Rec.709 (or log with a LUT); colours will be wrong until it is converted')
    xml = next((p for p in [src.with_name(src.stem + 'M01.XML'), src.with_name(src.stem + 'M01.xml')] if p.exists()), None)
    gamma = prim = None
    if xml:   # Sony sidecar: says whether the clip was shot in a log profile
        t = xml.read_text(errors='ignore')
        gamma = (re.search(r'CaptureGammaEquation"\s+value="([^"]+)"', t) or [None, None])[1]
        prim = (re.search(r'CaptureColorPrimaries"\s+value="([^"]+)"', t) or [None, None])[1]
        if gamma and 'log' in gamma.lower():
            warns.append(f'shot in {gamma}/{prim} (log): set "grade": {{"camera_lut": ...}} to the camera maker\'s LUT before the grade check')
    start, end = a.start, min(a.end, dur)
    if not 0 <= start < end: stops.append(f'bad window {start}-{end} (file is {dur:.1f} s)')
    if stops and not a.accept_risk:
        raise SystemExit('STOP, check with the host before going on:\n  - ' + '\n  - '.join(stops + warns))
    proj.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((HERE.parent/'project.template.json').read_text())
    cfg.update(name=a.name or proj.name, source=str(src), window=[round(start, 2), round(end, 2)], fps=round(fps, 6))
    cfg['camera'] = {'size': [w, h], 'fps': fr, 'pix_fmt': v.get('pix_fmt'), 'transfer': v.get('color_transfer'),
                     'gamma': gamma, 'primaries': prim, 'audio_channels': auds[0].get('channels') if auds else None,
                     'warnings': warns, 'problems_accepted': stops}
    save(proj, cfg)
    P = paths(proj, cfg); P['work'].mkdir(parents=True, exist_ok=True)
    # mastering audio (48 kHz 24-bit stereo) and the transcription upload (16 kHz mono) for exactly the window
    ff(['-ss', start, '-t', end-start, '-i', src, '-map', '0:a:0', '-vn', '-ac', 2, '-ar', 48000, '-c:a', 'pcm_s24le', P['audio']], quiet=True)
    ff(['-i', P['audio'], '-ac', 1, '-ar', 16000, '-c:a', 'pcm_s16le', P['speech']], quiet=True)
    print(f"set up {proj}: window {fmt_t(start)}-{fmt_t(end)} ({end-start:.0f} s), {w}x{h} {fps:.3f} fps, audio {auds[0].get('channels')} ch")
    for x in warns: print('  warning:', x)
    print('  If this was shot in a log profile (S-Log, C-Log, V-Log, LogC, N-Log...), set grade.camera_lut before the grade check.')
    print('next: pipeline.py transcribe', proj)

def transcript_md(cfg, tr):
    t0, lines, cur = cfg['window'][0], [], None
    for w in tr['words']:
        if w['type'] != 'word': continue
        if cur is None or w['speaker_id'] != cur[0] or (cur[2] and cur[2][-1][-1] in '.?!' and len(cur[2]) > 12):
            cur = [w['speaker_id'], w['start'] + t0, []]; lines.append(cur)
        cur[2].append(w['text'].strip())
    return '\n'.join(f'[{fmt_t(t)} | src {t:.1f}s | {s}] {" ".join(x)}' for s, t, x in lines) + '\n'

def whisper(P, cfg):
    """Local Whisper through HyperFrames (free; nothing leaves the computer). It has no speaker labels, and it stretches words
    over pauses, so word edges are pulled back to where the audio actually goes quiet (edits.tighten)."""
    t = cfg.get('transcription', {})
    d = P['work']/'whisper'; d.mkdir(parents=True, exist_ok=True)
    cmd = [*HF, 'transcribe', str(P['speech']), '-d', str(d), '--model', t.get('whisper_model', 'small.en'), '--json']
    if t.get('language'): cmd += ['--language', t['language']]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = next((json.loads(x) for x in r.stdout.splitlines()[::-1] if x.startswith('{')), {})
    f = Path(out.get('transcriptPath') or d/'transcript.json')
    if r.returncode or not f.exists():
        raise SystemExit(f'Whisper failed (is whisper-cpp installed? brew install whisper-cpp):\n{(r.stdout + r.stderr)[-1500:]}')
    ws = E.tighten([{'text': w['text'], 'start': w['start'], 'end': w['end']} for w in json.loads(f.read_text())], levels(P['speech']))
    return {'engine': 'whisper', 'model': t.get('whisper_model', 'small.en'),
            'words': [{**w, 'type': 'word', 'speaker_id': 'speaker_0'} for w in ws]}

def cmd_transcribe(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    if P['transcript'].exists(): raise SystemExit(f"{P['transcript']} exists; not transcribing again (ElevenLabs would charge again).")
    engine = cfg.get('transcription', {}).get('engine', 'elevenlabs')
    s, e = cfg['window']
    for other in Path(a.project).resolve().parent.glob('*/project.json'):   # never pay twice for the same audio
        o = json.loads(other.read_text())
        if other.parent.resolve() != Path(a.project).resolve() and o.get('source') == cfg['source'] \
                and o['window'][0] < e and s < o['window'][1] and paths(other.parent, o)['transcript'].exists():
            raise SystemExit(f"{other.parent} already has a transcript of {fmt_t(o['window'][0])}-{fmt_t(o['window'][1])} of this clip. "
                             'Reuse it: set "paths": {"transcript": ...} and use the same "window" start, then skip this stage.')
    secs = float(probe(P['speech'])['format']['duration'])
    if engine == 'whisper':
        print(f'transcribing {secs/60:.1f} min locally with Whisper (free; about as long as the audio, or longer)...', flush=True)
        tr = whisper(P, cfg)
    elif engine == 'elevenlabs':
        from dotenv import load_dotenv
        load_dotenv(Path.cwd()/'.env')
        key = os.getenv('ELEVENLABS_API_KEY')
        if not key: raise SystemExit('ELEVENLABS_API_KEY is not set in .env. No request sent.')
        print(f"uploading {secs/60:.1f} min of 16 kHz mono audio to ElevenLabs Scribe v2 (billed to your ElevenLabs plan)...", flush=True)
        from elevenlabs.client import ElevenLabs
        try:
            with open(P['speech'], 'rb') as f:
                r = ElevenLabs(api_key=key, timeout=900).speech_to_text.convert(file=f, model_id='scribe_v2', diarize=True,
                                                                                 timestamps_granularity='word', tag_audio_events=False)
        except Exception as x:   # quota, auth, network: stop and say so; never switch to another service silently
            raise SystemExit(f'ElevenLabs request failed ({type(x).__name__}: {str(x)[:300]}). Nothing saved, nothing else tried.')
        tr = r.model_dump()
    else:
        raise SystemExit(f'transcription.engine is "{engine}": use "elevenlabs" or "whisper"')
    P['transcript'].parent.mkdir(parents=True, exist_ok=True)
    P['transcript'].write_text(json.dumps(tr, indent=2))
    (P['transcript'].parent/'transcript.md').write_text(transcript_md(cfg, tr))
    ids = sorted({w['speaker_id'] for w in tr['words'] if w['type'] == 'word'})
    print(f"saved {P['transcript']} and transcript.md; speaker labels: {ids}\nnext: pipeline.py speakers {a.project}")

def cmd_find(a):
    """Every occurrence of a phrase, with the source times of its first and last word, for exact edits ranges."""
    cfg = load(a.project); P = paths(a.project, cfg); t0 = cfg['window'][0]
    ws = [w for w in json.loads(P['transcript'].read_text())['words'] if w['type'] == 'word']
    b = lambda t: re.sub(r"[^a-z0-9']", '', t.lower())
    toks = [b(t) for t in a.phrase.split()]
    hits = [i for i in range(len(ws)-len(toks)+1) if all(b(ws[i+k]['text']) == t for k, t in enumerate(toks))]
    for i in hits:
        j = i + len(toks) - 1
        ctx = ' '.join(w['text'].strip() for w in ws[max(0, i-6):j+7])
        print(f"{ws[i]['start']+t0:9.2f} - {ws[j]['end']+t0:9.2f}  [{ws[i]['speaker_id']}]  ...{ctx}...")
    if not hits: print('not found (matching is word by word, ignoring case and punctuation)')

def cmd_speakers(a):
    """For each speaker label: 3 moments where they talk alone for 3+ s, 3 frames 0.4 s apart (look for the moving mouth)."""
    cfg = load(a.project); P = paths(a.project, cfg); t0 = cfg['window'][0]
    words = [w for w in json.loads(P['transcript'].read_text())['words'] if w['type'] == 'word']
    runs, cur = [], None
    for w in words:
        if cur and w['speaker_id'] == cur[0] and w['start'] - cur[2] < 0.6: cur[2] = w['end']
        else: cur = [w['speaker_id'], w['start'], w['end']]; runs.append(cur)
    out = P['work']/'speakers'; out.mkdir(parents=True, exist_ok=True)
    imgs = []
    for sid in sorted({r[0] for r in runs}):
        long = [r for r in runs if r[0] == sid and r[2]-r[1] >= 3]
        pick = [long[int(i*(len(long)-1)/2)] for i in range(3)] if len(long) >= 3 else long
        for r in pick:
            mid = t0 + (r[1]+r[2])/2
            for k in range(3):
                f = out/f'{sid}-{mid:.1f}-{k}.jpg'
                if not f.exists():
                    ff(['-ss', mid + .4*k, '-i', cfg['source'], '-frames:v', 1, '-vf', 'scale=960:540', '-q:v', 3, f], quiet=True)
                imgs.append((f, f'{sid} @ {fmt_t(mid)} +{.4*k:.1f}s'))
    tile(imgs, P['work']/'speakers.png', 3)
    print(f"{P['work']/'speakers.png'}: rows of 3 frames per moment. Decide who is left (L) / right (R) from whose mouth moves,")
    print('then set project.json "speakers" (e.g. {"speaker_0": "R", "speaker_1": "L"}). Labels change on every ElevenLabs run.')
    if len({r[0] for r in runs}) == 1:
        print('Only one speaker label (always the case with Whisper). One person to camera: map it to their side, e.g. '
              '{"speaker_0": "L"}. Two people: Whisper cannot tell who is talking; see SKILL.md "Whisper with two people".')

def cmd_faces(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    if P['faces'].exists(): raise SystemExit(f"{P['faces']} exists")
    fr = P['work']/'frames-2s'; fr.mkdir(parents=True, exist_ok=True)
    s, e = cfg['window']
    ff(['-ss', s, '-t', e-s, '-i', cfg['source'], '-vf', 'fps=0.5,scale=960:540', '-start_number', 0, '-q:v', 3, fr/'%05d.jpg'], quiet=True)
    js = subprocess.run(['swift', str(HERE/'faces.swift'), str(fr)], capture_output=True, text=True, check=True).stdout
    P['faces'].parent.mkdir(parents=True, exist_ok=True)
    P['faces'].write_text(js)
    tr = E.face_tracks(json.loads(js), s, solo=E.solo_side(cfg))
    med = lambda v: sorted(v)[len(v)//2]
    fb = {k: [int(med([p[1] for p in v])), int(med([p[2] for p in v]))] for k, v in tr.items() if v}
    cfg = load(a.project)   # re-read: this stage is slow, and project.json may have been edited meanwhile
    if not cfg.get('face_fallback'):
        cfg['face_fallback'] = fb; save(a.project, cfg)
    print(f"{P['faces']}: {sum(len(v) for v in tr.values())} face samples; median centres {fb} (4K units); "
          f"left/right split at the middle. Check both people were found; small background faces are ignored.")

def cmd_stills(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    s, e = cfg['window']
    times = [float(x) for x in a.at.split(',')] if a.at else [s + (e-s)*k/5 for k in range(1, 5)]
    out = P['work']/'stills'; out.mkdir(parents=True, exist_ok=True)
    g = cfg.get('grade', {})
    if not (g.get('camera_lut') or g.get('look_lut') or g.get('vignette')):
        print('No grade set (no LUTs, no vignette): the footage is used as shot. See references/make-it-yours.md to add one.')
    m = G.mask(cfg, (1920, 1080), P['work'])
    cam = f",lut3d=file={G.lut(g['camera_lut'], a.project)}:interp=tetrahedral" if g.get('camera_lut') else ''
    imgs = []
    for t in times:
        b, gr = out/f'{t:.1f}-before.png', out/f'{t:.1f}-graded.png'
        for f in (b, gr): f.unlink(missing_ok=True)   # previews: always regenerated, so a changed LUT shows
        ff(['-ss', t, '-i', cfg['source'], '-frames:v', 1, '-vf', f'scale=1920:1080:flags=lanczos,format=gbrp16le{cam},format=rgb24', b], quiet=True)
        ff(['-ss', t, '-i', cfg['source'], *(['-i', m] if m else []), '-frames:v', 1, '-filter_complex',
            G.graph(cfg, 'null', (1920, 1080), a.project) + ';[v]format=rgb24[o]', '-map', '[o]', gr], quiet=True)
        imgs += [(b, f'{fmt_t(t)} camera LUT only' if cam else f'{fmt_t(t)} as shot'), (gr, f'{fmt_t(t)} full grade')]
    tile(imgs, P['work']/'grade-check.png', 2)
    print(f"{P['work']/'grade-check.png'}: left = before your look, right = the full grade. Show the host before rendering.")

def cmd_laptop(a):
    """When a hand is at the laptop: mean frame-to-frame change at 10 fps inside cutting.laptop, a box in 4K units over the
    desk beside the laptop. Pick it on a still; keep gesturing hands out of it. edits then ends any shot whose tail runs
    into a reach on its last word."""
    cfg = load(a.project); P = paths(a.project, cfg)
    zone = cfg.get('cutting', {}).get('laptop')
    if not zone: raise SystemExit('Set project.json "cutting": {"laptop": [x0, y0, x1, y1]} first: a box in 4K units (the frame as if it '
                                  'were 3840x2160) over the desk beside the laptop, clear of gesturing hands.')
    if P['laptop'].exists(): raise SystemExit(f"{P['laptop']} exists")
    x0, y0, x1, y1 = zone; w, h = (x1-x0)//10, (y1-y0)//10   # analysis size stays the same for every camera size
    c = G.to_source(f'crop={x1-x0}:{y1-y0}:{x0}:{y0}', cfg)
    s, e = cfg['window']
    raw = subprocess.run([FF, '-v', 'error', '-ss', str(s), '-t', str(e-s), '-i', cfg['source'], '-vf',
                          f'{c},fps=10,scale={w}:{h},format=gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    n = w*h; fr = [raw[i:i+n] for i in range(0, len(raw)-n+1, n)]
    diffs = [sum(abs(p-q) for p, q in zip(f0, f1))/n for f0, f1 in zip(fr, fr[1:])]
    reaches = E.reach_times(diffs, s)
    P['laptop'].parent.mkdir(parents=True, exist_ok=True)
    P['laptop'].write_text(json.dumps({'zone': zone, 'fps': 10, 'reaches': reaches}))
    print(f"{P['laptop']}: {len(reaches)} moments with a hand at the laptop: " + ', '.join(f'{fmt_t(x)}-{fmt_t(y)}' for x, y in reaches))

def cmd_edits(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    if P['edits'].exists() and not a.rebuild: raise SystemExit(f"{P['edits']} exists; pass --rebuild to replace it (edits are cheap).")
    tr = json.loads(P['transcript'].read_text())
    ids = {w['speaker_id'] for w in tr['words'] if w['type'] == 'word'}
    if not ids <= set(cfg.get('speakers', {})): raise SystemExit(f'project.json "speakers" must map {sorted(ids)} to L, R or both (run pipeline.py speakers)')
    if not cfg.get('edits'): raise SystemExit('project.json "edits" is empty: add the approved ranges first')
    W = E.load_words(cfg, tr)
    two = not E.solo_side(cfg)
    tracks = (E.face_tracks(json.loads(P['faces'].read_text()), cfg['window'][0], solo=E.solo_side(cfg)) if P['faces'].exists()
              else {'L': [], 'R': []})
    if two and not all(cfg.get('face_fallback', {}).get(k) for k in 'LR'):
        raise SystemExit('Two people, but faces were not found on both sides (project.json face_fallback). Run faces, or set it by hand in 4K units.')
    reaches = json.loads(P['laptop'].read_text())['reaches'] if P['laptop'].exists() else []
    if cfg.get('cutting', {}).get('laptop') and not P['laptop'].exists():
        print(f'note: "cutting.laptop" is set but {P["laptop"]} is missing, so only clicks are checked (run pipeline.py laptop first)')
    env = click_env(P)
    built = [E.build(n, spec, W, cfg, tracks, env, reaches) for n, spec in cfg['edits'].items()]
    P['edits'].write_text(json.dumps([e for e, _ in built], indent=1))
    (Path(a.project)/'cut-report.md').write_text(E.cut_report(built, cfg))
    for e, _ in built:
        (Path(a.project)/f"{e['name']}.srt").write_text(E.srt(e['words']))
        print(f"{e['name']:32} {e['duration']:7.2f}s  {len(e['segments'])} shots")
    print(f"wrote {P['edits']}, {Path(a.project)/'cut-report.md'} and the .srt files (show the host the cut report)")

def cmd_media(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    t0, fps = cfg['window'][0], cfg['fps']
    for e in json.loads(P['edits'].read_text()):
        if a.edits and e['name'] not in a.edits: continue
        name, size, segs = e['name'], tuple(e['size']), e['segments']
        Wd = P['work']/'media'/name; Wd.mkdir(parents=True, exist_ok=True)
        logs = P['work']/'logs'
        m = G.mask(cfg, size, P['work'])
        dest = Path(a.project)/name/'assets/speaker.mp4'
        # Shots are named by what they contain, so a re-cut (edits --rebuild) re-encodes only the shots that changed. The
        # joined footage isn't: once made it is kept, so refuse to reuse it for a different edit list (it would ship stale).
        segname = lambda s: f"seg-{hashlib.sha1(json.dumps([s['in'], s['out'], s['crop'], size, cfg.get('grade'), cfg.get('seam')]).encode()).hexdigest()[:10]}.mp4"
        rec, now = Wd/'segments.json', json.dumps([[s['in'], s['out'], s['crop']] for s in segs])
        made = [f for f in (Wd/'video.mp4', Wd/'audio.wav', dest) if f.exists()]
        if made and rec.exists() and rec.read_text() != now:
            raise SystemExit(f"{name}: edits.json changed since {', '.join(map(str, made))} were made. Move them aside, "
                             'then run media again; unchanged shots are reused.')
        if not made: rec.write_text(now)
        n_of = lambda s: round((s['out']-s['in'])*fps)   # every shot is a whole number of frames; its audio matches exactly
        def seg(i_s):
            i, s = i_s
            out = Wd/segname(s)
            if out.exists(): return
            ff(['-ss', s['in'], '-i', cfg['source'], *(['-loop', 1, '-i', m] if m else []), '-frames:v', n_of(s),
                '-filter_complex', G.graph(cfg, s['crop'], size, a.project)+';[v]format=yuv420p10le[o]', '-map', '[o]',
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', 12, '-r', rate(cfg), *TAGS, out.with_suffix('.tmp.mp4')],
               logs/f'{name}-seg-{i:03}.log')
            out.with_suffix('.tmp.mp4').rename(out)
        with ThreadPoolExecutor(3) as pool:
            list(pool.map(seg, enumerate(segs)))
        # absolute paths: ffmpeg reads concat entries relative to the list's own folder
        (Wd/'concat.txt').write_text(''.join(f"file '{(Wd/segname(s)).resolve()}'\n" for s in segs))
        if not (Wd/'video.mp4').exists():
            ff(['-f', 'concat', '-safe', 0, '-i', Wd/'concat.txt', '-c', 'copy', Wd/'video.mp4'], logs/f'{name}-concat.log')
        target = cfg['loudness']['reel' if e['vertical'] else 'wide']
        parts = []
        for i, s in enumerate(segs):
            a0 = round((s['in']-t0)*48000); d = n_of(s)/fps
            parts.append(f"[0:a]atrim=start_sample={a0}:end_sample={a0 + round(d*48000)},"
                         f"asetpts=PTS-STARTPTS,afade=t=in:d=0.008,afade=t=out:st={d-0.008:.4f}:d=0.008[a{i}]")
        graph = ';'.join(parts)+';'+''.join(f'[a{i}]' for i in range(len(segs)))+f"concat=n={len(segs)}:v=0:a=1,{MASTER.format(I=target)}[out]"
        (Wd/'audio-graph.txt').write_text(graph)
        if not (Wd/'audio.wav').exists():
            ff(['-i', P['audio'], '-/filter_complex', Wd/'audio-graph.txt', '-map', '[out]', '-c:a', 'pcm_s24le', Wd/'audio.wav'], logs/f'{name}-audio.log')
            # single-pass loudnorm can land low on a long edit (and a true peak would stop plain gain), so: gain plus a limiter
            # at -1.8 dBFS, run at 4x the sample rate so it catches true peaks; the limiting costs ~0.4 LU, so aim once more.
            lufs = loudness(Wd/'audio.wav')[0]
            if abs(lufs - target) > .3:
                (Wd/'audio.wav').rename(Wd/'audio-pass1.wav')
                lim = lambda gain, out: ff(['-i', Wd/'audio-pass1.wav', '-af', f'volume={gain:.2f}dB,aresample=192000,'
                                            'alimiter=limit=0.8128:attack=1:release=40:level=false,aresample=48000',
                                            '-c:a', 'pcm_s24le', out], logs/f'{name}-audio-level.log')
                lim(target - lufs, Wd/'audio-try.wav')
                lim(2*target - lufs - loudness(Wd/'audio-try.wav')[0], Wd/'audio.wav'); (Wd/'audio-try.wav').unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():   # HyperFrames input: 8-bit H.264, 1 s keyframes for fast seeking, AAC dialogue
            ff(['-i', Wd/'video.mp4', '-i', Wd/'audio.wav', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'medium',
                '-crf', 14, '-pix_fmt', 'yuv420p', '-g', round(fps), *TAGS, *BSF, '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', dest],
               logs/f'{name}-speaker.log')
        print('ready', dest, flush=True)
    print(f'next: pipeline.py captions {a.project}')

def cmd_captions(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    for e in json.loads(P['edits'].read_text()):
        if a.edits and e['name'] not in a.edits: continue
        if not (Path(a.project)/e['name']/'assets/speaker.mp4').exists():
            print(f"{e['name']}: no footage yet (run pipeline.py media first)"); continue
        d, placed = C.write(e, cfg, a.project)
        print(f"{d/'index.html'}: captions" + (f", {len(placed)} template beat(s): " + ', '.join(f"{b['name']} {b['start']:.1f}-{b['end']:.1f}s" for b in placed) if placed else ''))
    print(f'preview: {" ".join(HF)} preview projects/<name>/<edit>   render: pipeline.py render {a.project}')

def finish(cfg, e, raw, out):
    """BT.709 tags, and loudness corrected on the final file (the renderer turns mono dialogue into stereo, ~3 LU louder)."""
    target = cfg['loudness']['reel' if e['vertical'] else 'wide']
    lufs, peak = loudness(raw)
    gain = target - lufs
    if peak + gain > -1.0:
        gain = -1.0 - peak
        print(f'  note: true peak limits the gain; final loudness {lufs+gain:.1f} LUFS instead of {target}')
    ff(['-i', raw, '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy', *BSF, '-af', f'volume={gain:.2f}dB',
        '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', out], quiet=True)

def cmd_render(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    edits = {e['name']: e for e in json.loads(P['edits'].read_text())}
    for name in a.edits or list(edits):
        e, d = edits[name], Path(a.project)/name
        if not (d/'index.html').exists(): raise SystemExit(f'{name}: no caption page yet (run pipeline.py captions first)')
        chk = subprocess.run([*HF, 'check', str(d)], capture_output=True, text=True)
        if chk.returncode or 'Check passed' not in chk.stdout + chk.stderr:
            raise SystemExit(f'{name}: hyperframes check failed:\n{(chk.stdout + chk.stderr)[-2500:]}')
        # named after everything it was rendered from (page, templates, footage, logo, font): after any change, an old render
        # is never reused. A page-only key missed a changed template or re-cut footage and shipped the old render.
        key = hashlib.sha256()
        for f in sorted([d/'index.html', *(d/'templates').glob('*'), *(d/'assets').glob('*')]):
            key.update(f.name.encode() + (f.read_bytes() if f.suffix == '.html' else f'{f.stat().st_size}:{f.stat().st_mtime_ns}'.encode()))
        raw = P['work']/'render'/f'{name}-{key.hexdigest()[:8]}.mp4'; raw.parent.mkdir(parents=True, exist_ok=True)
        if not raw.exists():   # the renderer logs a lot; show it only if the render fails
            rr = subprocess.run([*HF, 'render', str(d), '--fps', rate(cfg), '-o', str(raw), '--quiet'], capture_output=True, text=True)
            if rr.returncode or not raw.exists():
                raise SystemExit(f'{name}: hyperframes render failed:\n{(rr.stdout + rr.stderr)[-3000:]}')
        out = P['exports']/f'{name}{("-" + a.tag) if a.tag else ""}.mp4'; out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists(): raise SystemExit(f'{out} exists; pass --tag v2 (or similar) for a new version')
        finish(cfg, e, raw, out)
        srt = Path(a.project)/f'{name}.srt'
        if srt.exists(): shutil.copy(srt, out.with_suffix('.srt'))
        print('rendered', out)
        verify_file(cfg, e, out)

def verify_file(cfg, e, f):
    pr = probe(f)
    v = next(s for s in pr['streams'] if s['codec_type'] == 'video'); au = next(s for s in pr['streams'] if s['codec_type'] == 'audio')
    decode = subprocess.run([FF, '-v', 'error', '-i', str(f), '-f', 'null', '-'], capture_output=True, text=True).stderr.strip()
    lufs, peak = loudness(f)
    frames = int(subprocess.run([FFPROBE, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                                 '-of', 'csv=p=0', str(f)], capture_output=True, text=True).stdout.strip() or 0)
    want = round(C.frames(e['segments'], cfg['fps']) * cfg['fps'])
    target = cfg['loudness']['reel' if e['vertical'] else 'wide']
    checks = {'size': [v['width'], v['height']] == e['size'], f'fps {rate(cfg)}': Fraction(v['r_frame_rate']) == Fraction(rate(cfg)),
              f'frames {frames}/{want}': abs(frames - want) <= 1,
              'A/V length': abs(float(au['duration']) - float(v['duration'])) < .05,
              'BT.709 tags': [v.get('color_primaries'), v.get('color_transfer'), v.get('color_space')] == ['bt709']*3,
              'decodes clean': not decode, f'peak {peak} dBFS': peak <= -1.0, f'loudness {lufs} LUFS (target {target})': abs(lufs-target) <= .6}
    ok = all(checks.values())
    print(('PASS ' if ok else 'FAIL ') + f.name + ': ' + ', '.join(k + ('' if v_ else ' FAILED') for k, v_ in checks.items()))
    return ok

def cmd_verify(a):
    cfg = load(a.project); P = paths(a.project, cfg)
    ok, seen = True, 0
    for e in json.loads(P['edits'].read_text()):
        for f in sorted(P['exports'].glob(f"{e['name']}*.mp4")):
            if re.fullmatch(re.escape(e['name']) + r'(-[\w.]+)?', f.stem):
                ok &= verify_file(cfg, e, f); seen += 1
    if not seen: print(f"nothing to verify in {P['exports']}")
    raise SystemExit(0 if ok and seen else 1)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='stage', required=True)
    for s in ['new', 'transcribe', 'find', 'speakers', 'faces', 'stills', 'laptop', 'edits', 'media', 'captions', 'render', 'verify']:
        q = sub.add_parser(s); q.add_argument('project')
        if s == 'find': q.add_argument('phrase')
        if s == 'new':
            q.add_argument('--source', required=True); q.add_argument('--start', type=float, required=True)
            q.add_argument('--end', type=float, required=True); q.add_argument('--name')
            q.add_argument('--accept-risk', action='store_true', help='continue past intake problems (only after the host agrees)')
        if s == 'stills': q.add_argument('--at', help='comma-separated source seconds')
        if s == 'edits': q.add_argument('--rebuild', action='store_true')
        if s in ('media', 'captions', 'render'): q.add_argument('edits', nargs='*')
        if s == 'render': q.add_argument('--tag', help='version suffix for the export, e.g. v2')
    a = p.parse_args()
    globals()[f'cmd_{a.stage}'](a)
