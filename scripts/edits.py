"""Edit lists from word timings: pause removal, automatic cuts (fillers, swears, cut-off fragments, stutters), face-centred
crops with alternating framing, caption words on the edited timeline, SRT subtitles and a readable cut report.
All times are source seconds unless a name says timeline. Crops are in "4K units" (as if the frame were 3840x2160);
grade.to_source() scales them to the real frame size."""
import math, re

PRE, POST, MAX_GAP = 0.10, 0.18, 0.45            # pad before/after words, cut gaps longer than this
# Laptop clicks and reaches: a click or a hand reaching for the laptop after a word ends the shot on that word.
# Clicks sooner than CLICK_AFTER are the word's own consonant; the trimmed end (word end + TRIM, rounded up to a frame)
# stays before anything later. A reach counts if the hand reaches the laptop zone up to REACH_LEAD after the shot's end:
# the arm leaves the body about 0.2 s before it gets there.
CLICK_AFTER, TRIM, REACH_LEAD = 0.08, 0.04, 0.2
FILLERS = {'um', 'uh', 'umm', 'uhm', 'mm', 'mm-hmm', 'er', 'erm'}
SWEARS = ['fuck', 'fucking', 'shit', 'bullshit']   # default; project.json cutting.swears replaces it ([] keeps every word)
SRC_W, SRC_H = 3840, 2160                          # "4K units": crops and face positions are always in this frame
bare = lambda t: re.sub(r"[^a-z'-]", '', t.lower())

def load_words(cfg, tr):
    """Transcript words -> [{text, s, e, spk}] in source seconds, speaker ids mapped to L/R/both, caption fixes applied."""
    t0, spk_map = cfg['window'][0], cfg['speakers']
    # A transcriber can stretch a word over the silence after it, sometimes to the end of the file. No spoken word lasts
    # 1.5 s, so a word longer than that is stretched: give it an ordinary 0.5 s.
    out = [{'text': w['text'].strip(), 's': w['start'] + t0, 'e': (w['end'] if w['end'] - w['start'] <= 1.5 else w['start'] + .5) + t0,
            'spk': spk_map[w['speaker_id']]}
           for w in tr['words'] if w['type'] == 'word' and w['text'].strip() not in ('...', '…', '')]
    fixes = cfg.get('captions', {}).get('fixes', {})   # e.g. local spelling, names the transcriber mishears
    def fix(word):   # exact key first; a capitalised word also matches its lower-case key ("Colors" -> "Colours")
        if word in fixes: return fixes[word]
        low = fixes.get(word.lower()) if word[:1].isupper() else None
        return low[:1].upper() + low[1:] if low else word
    for w in out:
        w['text'] = re.sub(r'^(\w+)', lambda m: fix(m.group(1)), w['text'])
    for first, second, repl in cfg.get('captions', {}).get('merge', []):   # "physio-" + "therapy": caption the real term
        for i, w in enumerate(out[:-1]):
            if w['text'] == first and out[i+1]['text'].startswith(second):
                out[i+1] = {**out[i+1], 'text': repl, 's': w['s']}
                del out[i]; break
    return out

def tighten(words, levels, step=0.05, over=14, min_gap=0.3):
    """Whisper stretches each word over the silence after it, which hides every pause from the pause cutter.
    levels: dB per `step` s of the same audio. Quiet runs (under the recording's own background level + `over` dB, at
    least min_gap long) trim the words that overlap them back to where the speech starts and stops."""
    real = sorted(x for x in levels if x > -120) or [-60.0]
    floor = real[len(real)//10]
    q = [x < floor + over for x in levels]
    quiet, i = [], 0
    while i < len(q):
        if q[i]:
            j = i
            while j+1 < len(q) and q[j+1]: j += 1
            if (j-i+1)*step >= min_gap: quiet.append((i*step, (j+1)*step))
            i = j+1
        else: i += 1
    for w in words:
        for a, b in quiet:
            if w['start'] + .05 < a < w['end']: w['end'] = round(a, 3)                       # speech stops inside the word
            if a <= w['start'] < b < w['end'] - .05: w['start'] = round(b, 3)              # ...or starts late in it
    return words

def auto_exclude(W, cfg):
    """Fillers, swear words, cut-off fragments ('li-') and the first of an immediate repeat ('the, the')."""
    c = cfg.get('cutting', {})
    if not c.get('auto', True):
        return []
    swears = {bare(s) for s in c.get('swears', SWEARS)}
    frag = lambda w: w['text'].endswith('-') and len(bare(w['text'])) <= 3
    ex = []
    for i, w in enumerate(W):
        b = bare(w['text'])
        # the repeat check looks past fillers and fragments, so a restart ("is cr- is", "the, um, the") is caught too
        nxt = next((W[k] for k in range(i+1, len(W)) if not (bare(W[k]['text']) in FILLERS or frag(W[k]))), None)
        if (b in FILLERS or b in swears or frag(w)
                or (nxt and b and b == bare(nxt['text']) and nxt['s']-w['e'] < 1.0)):
            ex.append((w['s'], w['e'], w['text']))
    return ex

def clicks(env, t0, a, b, over=18):
    """Sharp clicks in [a, b] (source s). env: 1 ms peaks of the audio above 3 kHz, from t0. A click stands `over` dB
    above the median 1 ms peak of the surrounding second, is the loudest point within 20 ms, and is under 30% of its
    peak 6-20 ms after and 2-20 ms before (a consonant or rustle isn't). Laptop and mouth clicks look the same here
    (1-3 ms long, 15-33 dB over the background); the picture tells them apart (reach_times), and trimming either costs nothing."""
    i0, i1 = max(20, int((a-t0)*1000)), min(len(env)-21, int((b-t0)*1000))
    if i1 <= i0: return []
    ctx = sorted(env[max(0, i0-500):i1+500])
    thr = ctx[len(ctx)//2] * 10**(over/20)
    return [round(t0 + k/1000, 3) for k in range(i0, i1) if env[k] >= thr and env[k] == max(env[k-20:k+21])
            and max(env[k+6:k+21]) < env[k]*.3 and max(env[k-20:k-2]) < env[k]*.3]

def reach_times(diffs, t0, fps=10):
    """Mean frame-to-frame change inside the laptop zone (pipeline.py laptop) -> [(start, end)] source seconds when a hand is there."""
    base = sorted(diffs)[len(diffs)//2]
    out, i = [], 0
    while i < len(diffs):
        if diffs[i] > max(2, 4*base):
            j = i
            while j+1 < len(diffs) and diffs[j+1] > 2*base: j += 1
            out.append((round(t0 + i/fps, 2), round(t0 + (j+1)/fps, 2))); i = j+1
        else: i += 1
    return out

def keep_ranges(W, fps, ranges, exclude, noisy=lambda a, b: None, min_shot=0.0):
    """noisy(a, b): (why, limit) if [a, b] (after a word) holds a click or a laptop reach, else None. The shot ends there:
    before a click it keeps the word's natural tail up to just before the click (limit, rounded down a frame; cutting on
    the word's end can clip a fading vowel); for a reach (limit None) it ends on the word.
    The pads around kept words never reach into a cut word or excluded stretch, so a cut word never plays on in a tail.
    min_shot: a pause cut that would leave a shot shorter than this keeps the pause instead (up to 1.2 s), so no shot
    flashes by. Shot edges sit on the source frame grid (kept to 4 decimals, so 30 and 29.97 fps stay exact)."""
    fl = lambda t: math.floor(t*fps+1e-6)/fps
    ce = lambda t: math.ceil(t*fps-1e-6)/fps
    segs = []
    for a, b in ranges:
        ws = [w for w in W if w['s'] >= a-.01 and w['e'] <= b+.01 and not any(x <= w['s'] < y for x, y in exclude)]
        cur = None
        for i, w in enumerate(ws):
            if cur is None:
                edge = max([y for x, y in exclude if w['s']-PRE < y <= w['s']], default=None)   # a cut word just before
                cur = [max(a, w['s']-PRE, edge or 0), None, [w], None, False, edge is not None and edge > max(a, w['s']-PRE)]
            else:
                cur[2].append(w)
            nxt = ws[i+1] if i+1 < len(ws) else None
            got = nxt and nxt['s']-w['e'] <= MAX_GAP and noisy(w['e']+CLICK_AFTER, nxt['s']-PRE)   # in a gap the pause cutter keeps
            cut_between = nxt and any(w['e'] <= x < nxt['s'] for x, y in exclude)
            pause = nxt is not None and nxt['s']-w['e'] > MAX_GAP
            if pause and not got and not cut_between and nxt['s']-w['e'] <= 1.2 and w['e']-cur[0] < min_shot:
                pause = False                                                                      # keep it: too short a shot
            if nxt is None or pause or got or cut_between:
                edge = min([x for x, y in exclude if w['e'] <= x < w['e']+POST], default=None)     # a cut word just after
                cur[1] = min(b, w['e']+POST, nxt['s']-PRE if nxt else 1e9)
                if edge is not None and edge < cur[1]: cur[1], cur[4] = edge, True
                got = got or noisy(w['e']+CLICK_AFTER, cur[1])                                        # in the tail
                if got:
                    why, limit = got
                    cur[1] = w['e']+TRIM if limit is None else min(cur[1], limit)
                    cur[3], cur[4] = f"{w['text']} ({w['e']:.2f}s): {why}", cur[4] or limit is not None
                segs.append(cur); cur = None
    out = []
    for a, b, ws, why, down, up in segs:   # ends pulled in by a cut word or a click round inwards, so no frame reaches it
        a, b = (ce(a) if up else fl(a)), (fl(b) if down else ce(b))
        if out and a <= out[-1]['out']:
            a = out[-1]['out']
        if b-a < 1/fps - 1e-6:
            continue
        spk = max('LR', key=lambda s: sum(w['e']-w['s'] for w in ws if w['spk'] == s))
        out.append({'in': round(a, 4), 'out': round(b, 4), 'spk': spk, 'words': ws, **({'trim': why} if why else {})})
    return out

def split_long(segs, fps, limit):
    """Break long unbroken speech at its widest word gap near the middle, so the framing can change."""
    fl = lambda t: math.floor(t*fps+1e-6)/fps
    out = []
    for s in segs:
        todo = [s]
        while todo:
            x = todo.pop(0); ws = x['words']
            if x['out']-x['in'] <= limit or len(ws) < 6:
                out.append(x); continue
            mid = (x['in']+x['out'])/2
            k = max(range(2, len(ws)-2), key=lambda i: (ws[i]['s']-ws[i-1]['e']) - abs(ws[i]['s']-mid)*.05)
            cut = round(fl((ws[k-1]['e']+ws[k]['s'])/2), 4)
            first = {k: v for k, v in x.items() if k != 'trim'}   # a trimmed end belongs to the second half
            todo[:0] = [{**first, 'out': cut, 'words': ws[:k]}, {**x, 'in': cut, 'words': ws[k:]}]
    return out

def solo_side(cfg):
    """'L' or 'R' when every speaker maps to one side (one person to camera), else None ("both" is two people)."""
    sides = set(cfg.get('speakers', {}).values())
    return sides.pop() if len(sides) == 1 and sides <= {'L', 'R'} else None

def both_mode(cfg):
    """Two people but no speaker labels (Whisper): "speakers": {"speaker_0": "both"}. Both stay on screen throughout."""
    return 'both' in cfg.get('speakers', {}).values()

def face_tracks(faces, t0, step=2, scale=4, solo=None):
    """faces.swift output on 960x540 frames every `step` s from t0 -> {'L': [(t, cx, cy)], 'R': [...]} in 4K units.
    Two people are split at the midline; a solo speaker gets every face, so leaning past the middle never loses the track."""
    tracks = {'L': [], 'R': []}
    for name, boxes in faces.items():
        t = t0 + step*int(name.split('.')[0])
        for x, y, w, h in boxes:
            cx, cy = (x+w/2)*scale, (y+h/2)*scale
            if w*scale >= 200:   # smaller faces are photos or posters in the background
                tracks[solo or ('L' if cx < SRC_W/2 else 'R')].append((t, cx, cy))
    if solo and tracks[solo]:   # standing up or reaching across the desk isn't a lean: drop faces far from the usual spot
        med = sorted(p[1] for p in tracks[solo])[len(tracks[solo])//2]
        tracks[solo] = [p for p in tracks[solo] if abs(p[1] - med) <= 350]   # a fixed 350 (4K units): raise it if a real lean gets dropped
    return tracks

def face_at(tracks, fallback, spk, a, b):
    tr = tracks[spk]
    pts = [p for p in tr if a-1 <= p[0] <= b+1] or sorted(tr, key=lambda p: abs(p[0]-(a+b)/2))[:1]
    if not pts or abs(pts[0][0]-(a+b)/2) > 6:
        return tuple(fallback[spk])
    med = lambda v: sorted(v)[len(v)//2]
    return med([p[1] for p in pts]), med([p[2] for p in pts])

def crop(shot, spk, face, solo=False):
    fx, fy = face
    away = 0 if solo else -1 if spk == 'L' else 1  # nudge framing away from the other person (a solo speaker stays centred)
    if shot == 'wide':     w, h, x, y = SRC_W, SRC_H, 0, 0
    elif shot == 'medium': w, h = 2880, 1620; x, y = (fx+SRC_W/2)/2-w/2, fy-0.38*h        # 1.33x, biased to speaker
    elif shot == 'close':  w, h = 1920, 1080; x, y = fx-(0.5-0.04*away)*w, fy-0.40*h      # 2x
    elif shot == 'vfull':  w, h = 1216, 2160; x, y = fx-w/2, 0                            # 9:16 full height
    elif shot == 'vclose': w, h = 960, 1708;  x, y = fx-w/2, fy-0.33*h                    # 9:16 punch-in (1.27x)
    x = int(min(max(x, 0), SRC_W-w)); y = int(min(max(y, 0), SRC_H-h))
    return f'crop={w}:{h}:{x - x % 2}:{y - y % 2}'

def back_and_forth(W, changes=3, max_turn=5.0, max_gap=1.2):
    """Quick back-and-forth between two people: runs of at least `changes` speaker changes where every turn is under
    max_turn and each handover under max_gap -> [(start, end)] source seconds."""
    turns = []
    for w in W:
        if turns and turns[-1][0] == w['spk'] and w['s'] - turns[-1][2] < 1.5: turns[-1][2] = w['e']
        else: turns.append([w['spk'], w['s'], w['e']])
    out, i = [], 0
    while i < len(turns):
        j = i
        while (j+1 < len(turns) and turns[j+1][1] - turns[j][2] < max_gap
               and turns[j][2] - turns[j][1] < max_turn and turns[j+1][2] - turns[j+1][1] < max_turn): j += 1
        if j - i >= changes: out.append((turns[i][1], turns[j][2]))
        i = j + 1
    return out

def halves(tracks, fallback, a, b, vertical=False, top='L'):
    """The half-and-half: each person's face-centred crop of the same frame; grade.graph joins them. 16:9: 1152x1296 crops
    side by side at 960x1080, the face a little lower for headroom (tight enough that the other person's shoulder stays out
    of each half). 9:16: 1152x1024 crops stacked at 1080x960, `top` above; the top face sits lower (clear of the app's
    header), the lower one higher (clear of the bottom text)."""
    w, h, ups = (1152, 1024, (.55, .45)) if vertical else (1152, 1296, (.42, .42))
    parts = []
    for side, up in zip((top, 'L' if top == 'R' else 'R') if vertical else 'LR', ups):
        fx, fy = face_at(tracks, fallback, side, a, b)
        x = int(min(max(fx - w/2, 0), SRC_W - w)); y = int(min(max(fy - up*h, 0), SRC_H - h))
        parts.append(f'crop={w}:{h}:{x - x % 2}:{y - y % 2}')
    return 'halves:' + '|'.join(parts)

def assign_shots(segs, vertical, tracks, fallback, solo=False, talk=(), top='L', stacked=False):
    """Change framing at every cut so pause removal reads as deliberate; a speaker change restarts the cycle.
    talk: back-and-forth windows, where shots alternate the half-and-half with the wide shot (16:9) or with the talker's
    own shot (9:16). stacked: every talk shot in 9:16 is the half-and-half (both on screen, no speaker labels)."""
    cycle = ['vfull', 'vclose'] if vertical else ['medium', 'close', 'wide', 'close']
    k, prev, h = 0, None, 0
    for s in segs:
        if any(x <= (s['in'] + s['out'])/2 < y for x, y in talk):
            h += 1
            if h % 2 or not vertical or stacked:
                two = h % 2 or (stacked and vertical)
                s['shot'] = 'halves' if two else 'wide'
                s['crop'] = halves(tracks, fallback, s['in'], s['out'], vertical, top) if two else crop('wide', s['spk'], (0, 0))
                prev = s; continue
        if not vertical and prev is not None and s['spk'] == prev['spk'] and s['out']-s['in'] < 1.0:
            s['shot'], s['crop'], s['short'] = prev['shot'], prev['crop'], True   # 16:9: a shot under 1 s shares a neighbour's framing (a jump cut), no flip-flop
            prev = s; continue
        elif prev is not None and s['spk'] != prev['spk']:
            s['shot'] = 'wide' if (not vertical and s['out']-s['in'] < 1.5) else cycle[0]; k = 0
        else:
            s['shot'] = cycle[k % len(cycle)]
            if prev is not None and s['shot'] == prev['shot']:
                k += 1; s['shot'] = cycle[k % len(cycle)]
            k += 1
        s['crop'] = crop(s['shot'], s['spk'], face_at(tracks, fallback, s['spk'], s['in'], s['out']), solo)
        prev = s
    for p, s, n in zip(segs, segs[1:], segs[2:]):   # ...the one nearer in time, so the head jumps across the smaller gap
        if s.get('short') and n['spk'] == s['spk'] and n['in'] - s['out'] < s['in'] - p['out']:
            s['shot'], s['crop'] = n['shot'], n['crop']
    for s in segs: s.pop('short', None)
    return segs

def timeline_words(segs):
    """Caption words on the edited timeline (fillers never captioned; dashes read as commas). A transcriber's cut-off
    marker ("it's-") becomes a hidden caption break (a comma the captions don't show), so a cut-off fragment never runs
    into the next speaker's words."""
    out, t = [], 0.0
    for s in segs:
        for w in s['words']:
            txt = re.sub(r'(?<=[A-Za-z])-+$', ',', re.sub(r'[—–]', ',', w['text']).strip())
            if txt and bare(txt) not in FILLERS:
                out.append({'text': txt, 's': round(t+max(0, w['s']-s['in']), 3),
                            'e': round(t+min(s['out'], w['e'])-s['in'], 3), 'spk': w['spk']})
        t += s['out']-s['in']
    return out

def build(name, spec, W, cfg, tracks, env=None, reaches=()):
    """env: 1 ms peaks above 3 kHz (clicks()); reaches: (start, end) of hands at the laptop (reach_times())."""
    if spec.get('format') not in ('reel', 'wide'):
        raise SystemExit(f'{name}: "format" must be "reel" (9:16) or "wide" (16:9), not {spec.get("format")!r}')
    vertical = spec['format'] == 'reel'
    def noisy(a, b):
        if b <= a: return None
        c = clicks(env, cfg['window'][0], a, b) if env else []
        if any(x <= a - CLICK_AFTER < y for x, y in spec.get('keep', [])): return None   # kept as spoken, tail and all
        if c: return f'click at {c[0]:.2f}s', c[0] - .005
        if any(ra < b + REACH_LEAD and rb > a - CLICK_AFTER for ra, rb in reaches): return 'laptop reach', None
    fps = cfg['fps']
    rs = spec['ranges']   # the edit plays the ranges in source order; an out-of-order range would silently vanish
    if any(rs[i][1] > rs[i+1][0] for i in range(len(rs)-1)) or any(a >= b for a, b in rs):
        raise SystemExit(f'{name}: ranges must be in time order, each [start, end] with start < end and no overlaps: {rs}. '
                         'Reordering sections is not supported.')
    # "keep" restores automatic cuts that were deliberate, e.g. the emphasis in "very, very, very good"
    auto = [x for x in auto_exclude(W, cfg) if not any(a <= x[0] < b for a, b in spec.get('keep', []))]
    ex = [tuple(x) for x in spec.get('exclude', [])] + [(a, b) for a, b, _ in auto]
    both = both_mode(cfg)
    talk = [(-1e9, 1e9)] if both else back_and_forth(W) if not solo_side(cfg) else ()
    segs = assign_shots(split_long(keep_ranges(W, fps, spec['ranges'], ex, noisy, 0.0 if vertical else 1.0), fps, 5.0 if vertical else 7.0),
                        vertical, tracks, cfg['face_fallback'], bool(solo_side(cfg)), talk, cfg.get('top', 'L'), both)
    edit = {'name': name, 'vertical': vertical, 'size': [1080, 1920] if vertical else [1920, 1080],
            'duration': round(sum(s['out']-s['in'] for s in segs), 4),
            'segments': [{k: s[k] for k in ('in', 'out', 'spk', 'shot', 'crop', 'trim') if k in s} for s in segs],
            'words': timeline_words(segs)}
    inside = lambda t: any(a-.01 <= t <= b+.01 for a, b in spec['ranges'])
    manual = [(w['s'], w['text'] + ' [by hand]') for w in W if inside(w['s'])
              and any(x <= w['s'] < y for x, y in spec.get('exclude', []))]
    by_hand = lambda t: any(x <= t < y for x, y in spec.get('exclude', []))   # listed once, as [by hand]
    removed = sorted([(a, txt) for a, b, txt in auto if inside(a) and not by_hand(a)] + manual)
    return edit, removed

def groups(words, max_words=6, max_chars=36):
    """Caption groups: break on a pause over 0.7 s, a speaker change, the word or character limit, and after a sentence
    (or a comma once a group has 3 words)."""
    blocks, q = [], []
    for w in words:
        if q and (w['s']-q[-1]['e'] > .7 or w['spk'] != q[-1]['spk'] or len(q) >= max_words
                  or len(' '.join(x['text'] for x in q+[w])) > max_chars):
            blocks.append(q); q = []
        q.append(w)
        if w['text'][-1] in '.?!' or (w['text'][-1] == ',' and len(q) >= 3):
            blocks.append(q); q = []
    return blocks + ([q] if q else [])

def srt(words):
    """SRT subtitles (for YouTube, accessibility, or a caption file) from timeline words."""
    blocks = groups(words, 7, 42)
    stamp = lambda v: f'{int(v//3600):02}:{int(v//60%60):02}:{int(v%60):02},{round(v%1*1000)%1000:03}'
    out = []
    for i, b in enumerate(blocks):
        end = min(b[-1]['e']+.5, blocks[i+1][0]['s']-.02) if i+1 < len(blocks) else b[-1]['e']+.5
        out.append(f"{i+1}\n{stamp(b[0]['s'])} --> {stamp(max(end, b[-1]['e']))}\n{' '.join(x['text'] for x in b)}\n")
    return '\n'.join(out)

def cut_report(edits_removed, cfg):
    """Markdown for the cuts checkpoint: what was taken out of each edit, and the words that remain."""
    out = [f"# Cut report: {cfg['name']}\n",
           'Automatic cuts: fillers, swear words, cut-off fragments and the first word of an immediate repeat. '
           f'Pauses longer than {MAX_GAP} s are removed everywhere. Listen at any repeat cut: it may have been deliberate emphasis.\n']
    for edit, removed in edits_removed:
        out.append(f"## {edit['name']} ({'9:16 reel' if edit['vertical'] else '16:9'}), {edit['duration']:.1f} s, "
                   f"{len(edit['segments'])} shots")
        out.append('Removed: ' + (', '.join(f'"{t}" ({a:.1f}s)' for a, t in removed) or 'nothing'))
        t, trims = 0, []
        for s in edit['segments']:
            t += s['out'] - s['in']
            if s.get('trim'): trims.append(f"{t:.1f}s after \"{s['trim']}\"")   # timeline time of the new shot end
        if trims: out.append('Shot ends trimmed to the last word (laptop click or reach): ' + '; '.join(trims))
        out.append('\n> ' + ' '.join(w['text'] for w in edit['words']) + '\n')
    return '\n'.join(out)

if __name__ == '__main__':   # self-check on tiny made-up transcripts
    cfg = {'name': 't', 'window': [100, 200], 'fps': 25, 'speakers': {'speaker_0': 'R'},
           'face_fallback': {'L': [1100, 700], 'R': [2600, 700]}, 'captions': {'fixes': {'colors': 'colours'}}}
    word = lambda t, s, e=None, spk='speaker_0': {'text': t, 'start': s, 'end': s+.3 if e is None else e, 'type': 'word', 'speaker_id': spk}
    W = load_words(cfg, {'words': [word(t, s) for t, s in [('um', 0), ('coffee', .4), ('the', .8), ('the', 1.2), ('colors', 1.6), ('matter.', 3.0)]]})
    assert W[4]['text'] == 'colours' and W[0]['s'] == 100
    assert load_words(cfg, {'words': [word('time.', 3, 50)]})[0]['e'] == 103.5
    e, removed = build('x', {'format': 'reel', 'ranges': [[100, 104]]}, W, cfg, {'L': [], 'R': []})
    assert [t for _, t in removed] == ['um', 'the'], removed
    assert [w['text'] for w in e['words']] == ['coffee', 'the', 'colours', 'matter.'], e['words']
    # cuts at the removed stutter and at the 1.1 s pause; framing alternates at every cut
    assert [s['shot'] for s in e['segments']] == ['vfull', 'vclose', 'vfull'], e['segments']
    assert e['segments'][0]['out'] == 100.8, e['segments'][0]            # the tail stops where the cut "the" begins
    W2 = load_words(cfg, {'words': [word(t, s) for t, s in [('Colors,', 0), ('year', .4), ('round-', .8), ('now.', 1.2)]]})
    assert W2[0]['text'] == 'Colours,', W2[0]                              # capitalised word matches the lower-case fix
    e2, rem2 = build('y', {'format': 'reel', 'ranges': [[100, 102]], 'exclude': [[101.2, 101.5]]}, W2, cfg, {'L': [], 'R': []})
    assert [w['text'] for w in e2['words']] == ['Colours,', 'year', 'round,'], e2['words']  # cut-off hyphen -> hidden break
    assert timeline_words([{'in': 0, 'out': 1, 'words': [{'text': 'on--', 's': 0, 'e': .3, 'spk': 'R'}]}])[0]['text'] == 'on,'
    assert rem2 == [(101.2, 'now. [by hand]')], rem2                     # hand removals reach the cut report
    try: build('z', {'format': 'reel', 'ranges': [[102, 104], [100, 101]]}, W2, cfg, {'L': [], 'R': []}); raise AssertionError
    except SystemExit: pass                                              # out-of-order ranges refused, not silently dropped
    e3, rem3 = build('k', {'format': 'reel', 'ranges': [[100, 104]], 'keep': [[100.8, 101.0]]}, W, cfg, {'L': [], 'R': []})
    assert [t for _, t in rem3] == ['um'] and [w['text'] for w in e3['words']][:3] == ['coffee', 'the', 'the'], rem3  # keep restores
    assert [t for _, t in build('s', {'format': 'reel', 'ranges': [[100, 104]]}, W, {**cfg, 'cutting': {'swears': ['coffee']}},
                                {'L': [], 'R': []})[1]] == ['um', 'coffee', 'the']   # the swear list is a setting
    lean = {'00000.jpg': [[520, 100, 100, 100]]}                          # one face just right of the midline (x 2280)
    away = {f'{i:05}.jpg': [[x, 100, 100, 100]] for i, x in enumerate([500, 420, 430, 425, 700])}   # a lean to 2200, then a walk-off to 3000
    assert [p[1] for p in face_tracks(away, 0, solo='L')['L']] == [2200.0, 1880.0, 1920.0, 1900.0]   # the lean stays, the walk-off goes
    assert face_tracks(lean, 0)['R'] and face_tracks(lean, 0, solo='L')['L'] == [(0, 2280.0, 600.0)]
    assert solo_side(cfg) == 'R' and solo_side({'speakers': {'speaker_0': 'L', 'speaker_1': 'R'}}) is None
    assert solo_side({'speakers': {'speaker_0': 'both'}}) is None and both_mode({'speakers': {'speaker_0': 'both'}})
    # laptop clicks and reaches: "one" 100.0-100.3, "two." 100.7-101.0 (a kept 0.4 s gap), "three" at 102 after a pause
    W4 = load_words(cfg, {'words': [word(t, s) for t, s in [('one', 0), ('two.', .7), ('three', 2.0)]]})
    spec = {'format': 'reel', 'ranges': [[100, 103]]}
    flat = [.01]*4000
    tick = lambda at: [1.0 if k == at else .01 for k in range(4000)]   # a 1 ms click, `at` ms after 100 s
    ends = lambda e: [(s['in'], s['out']) for s in e['segments']]
    assert ends(build('c', spec, W4, cfg, {'L': [], 'R': []}, flat)[0]) == [(100.0, 101.2), (101.88, 102.48)]   # clean: untouched
    tail, _ = build('c', spec, W4, cfg, {'L': [], 'R': []}, tick(1120))                  # a click 0.12 s after "two."
    assert ends(tail)[0] == (100.0, 101.08) and 'click at 101.12s' in tail['segments'][0]['trim'], tail
    gap, _ = build('c', spec, W4, cfg, {'L': [], 'R': []}, tick(450))                    # a click in the kept gap
    assert ends(gap)[:2] == [(100.0, 100.44), (100.6, 101.2)], ends(gap)                 # split there, click cut out
    near = build('c', spec, W4, cfg, {'L': [], 'R': []}, tick(1050))[0]                  # 0.05 s after the word: its consonant
    assert ends(near)[0] == (100.0, 101.2), ends(near)
    hand = build('c', spec, W4, cfg, {'L': [], 'R': []}, flat, [(101.3, 101.9)])[0]      # the hand reaches the laptop
    assert ends(hand)[0] == (100.0, 101.04) and hand['segments'][0]['trim'].endswith('laptop reach'), hand
    assert ends(build('c', spec, W4, cfg, {'L': [], 'R': []}, flat, [(101.5, 101.9)])[0])[0] == (100.0, 101.2)   # too late to show
    assert 'trimmed to the last word' in cut_report([(tail, [])], cfg)
    assert reach_times([.1]*20 + [5, 3, .5, .1] + [.1]*10, 100) == [(102.0, 102.3)]
    assert clicks([.01]*1000 + [1.0]*30 + [.01]*1000, 0, .5, 1.5) == []                # a 30 ms burst is speech, not a click
    # pads never reach a cut word: "that" 100.0-100.3, a hand-cut "the" 100.32-100.4, "first" at 101.0
    W5 = load_words(cfg, {'words': [word(t, s, e) for t, s, e in [('that', 0, .3), ('the', .32, .4), ('first', 1.0, 1.3)]]})
    for f in ('wide', 'reel'):
        assert ends(build('p', {'format': f, 'ranges': [[100, 102]], 'exclude': [[100.32, 100.5]]}, W5, cfg, {'L': [], 'R': []})[0])[0] == (100.0, 100.32)
    # 16:9: a pause cut that would leave a sub-second shot keeps the pause ("Then" [0.9 s] "add salt,")
    W6 = load_words(cfg, {'words': [word(t, s, s+.25) for t, s in [('Then', 0), ('add', 1.15), ('salt,', 1.45), ('the', 2.5), ('water', 2.8)]]})
    e6 = build('m', {'format': 'wide', 'ranges': [[100, 104]]}, W6, cfg, {'L': [], 'R': []})[0]
    assert ends(e6)[0][0] == 100.0 and ends(e6)[0][1] >= 101.7, ends(e6)   # "Then … add salt," is one shot
    assert len(build('m', {'format': 'reel', 'ranges': [[100, 104]]}, W6, cfg, {'L': [], 'R': []})[0]['segments']) == 3   # reels cut it
    # 30 fps: shot edges stay on the frame grid, so every shot is a whole number of frames
    e30 = build('f', {'format': 'wide', 'ranges': [[100, 104]]}, W6, {**cfg, 'fps': 30}, {'L': [], 'R': []})[0]
    assert all(abs(x*30 - round(x*30)) < .01 for s in e30['segments'] for x in (s['in'], s['out'])), e30['segments']
    js = assign_shots([{'in': 0, 'out': 3, 'spk': 'R'}, {'in': 3, 'out': 3.6, 'spk': 'R'}, {'in': 3.6, 'out': 7, 'spk': 'R'}],
                      False, {'L': [], 'R': []}, cfg['face_fallback'])
    assert [x['shot'] for x in js] == ['medium', 'medium', 'close'] and js[0]['crop'] == js[1]['crop'], js   # jump cut, then on
    jn = assign_shots([{'in': 0, 'out': 3, 'spk': 'R'}, {'in': 8, 'out': 8.6, 'spk': 'R'}, {'in': 8.9, 'out': 12, 'spk': 'R'}],
                      False, {'L': [], 'R': []}, cfg['face_fallback'])
    assert [x['shot'] for x in jn] == ['medium', 'close', 'close'] and jn[1]['crop'] == jn[2]['crop'] and 'short' not in jn[1], jn   # nearer the next shot
    # 9:16: in a back-and-forth the stacked half-and-half (`top` above) alternates with the talker's own shot
    three = lambda: [{'in': 0, 'out': 2, 'spk': 'R'}, {'in': 2, 'out': 4, 'spk': 'L'}, {'in': 4, 'out': 6, 'spk': 'R'}]
    tv = assign_shots(three(), True, {'L': [], 'R': []}, cfg['face_fallback'], talk=[(0, 6)], top='R')
    assert [x['shot'] for x in tv] == ['halves', 'vfull', 'halves'], tv
    top_crop, low_crop = tv[0]['crop'][7:].split('|')
    assert top_crop.startswith('crop=1152:1024:') and abs(int(top_crop.split(':')[2]) + 576 - cfg['face_fallback']['R'][0]) <= 2, tv[0]
    assert abs(int(low_crop.split(':')[2]) + 576 - cfg['face_fallback']['L'][0]) <= 2, tv[0]
    # both on screen (no speaker labels): stacked all the way in 9:16; half-and-half and wide alternate in 16:9
    assert [x['shot'] for x in assign_shots(three(), True, {'L': [], 'R': []}, cfg['face_fallback'], talk=[(-1e9, 1e9)], stacked=True)] == ['halves']*3
    assert [x['shot'] for x in assign_shots(three(), False, {'L': [], 'R': []}, cfg['face_fallback'], talk=[(-1e9, 1e9)], stacked=True)] == ['halves', 'wide', 'halves']
    cb = {**cfg, 'speakers': {'speaker_0': 'both'}}
    eb = build('b', {'format': 'reel', 'ranges': [[100, 104]]}, load_words(cb, {'words': [word(t, s) for t, s in [('one', 0), ('two', 1.5)]]}), cb, {'L': [], 'R': []})[0]
    assert {s['shot'] for s in eb['segments']} == {'halves'}, eb['segments']
    # keep: a click inside a kept range is left alone
    kept = build('c', {**spec, 'keep': [[100.9, 101.3]]}, W4, cfg, {'L': [], 'R': []}, tick(1120))[0]
    assert ends(kept)[0] == (100.0, 101.2) and 'trim' not in kept['segments'][0], ends(kept)
    # Whisper word tightening: "no." stretched 2.79-4.0 over a pause that the audio shows starts at 3.0
    lv = [-20.0]*60 + [-45.0]*20 + [-20.0]*20                            # 50 ms levels: speech, 1 s quiet from 3.0 s, speech
    tw = tighten([{'text': 'no.', 'start': 2.79, 'end': 4.0}, {'text': 'Okay', 'start': 4.0, 'end': 4.4}], lv)
    assert tw[0]['end'] == 3.0 and tw[1]['start'] == 4.0, tw
    rs = build('r', {'format': 'reel', 'ranges': [[100, 104]]}, load_words(cfg, {'words': [word(t, s) for t, s in
               [('everything', 0), ('is', .5), ('cr-', .9), ('is', 1.2), ('seen.', 1.6)]]}), cfg, {'L': [], 'R': []})
    assert [t for _, t in rs[1]] == ['is', 'cr-'] and [w['text'] for w in rs[0]['words']] == ['everything', 'is', 'seen.'], rs[1]  # a restart
    assert srt([{'text': 'Hello', 's': 0, 'e': .4, 'spk': 'L'}, {'text': 'there.', 's': .5, 'e': .9, 'spk': 'L'}]).startswith('1\n00:00:00,000 --> 00:00:01,400\nHello there.')
    print('edits.py self-check OK')
