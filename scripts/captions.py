"""The HyperFrames caption page for one edit: the cut footage, word-by-word captions in your caption style, an optional corner
logo, and your templates placed at the spoken words you choose (project.json "design"). Written from scratch for this
skill; every look decision is a setting in project.json "captions.style" or lives in your own templates."""
import html, json, re, shutil
from pathlib import Path

import edits as E

SKILL = Path(__file__).resolve().parents[1]
GSAP = 'https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js'
STYLE = {'font': 'Inter', 'font_file': None, 'weight': 800, 'size_wide': 64, 'size_reel': 70, 'colour': '#FFFFFF',
         'highlight': '#FFD84D', 'outline': '#000000', 'uppercase': False, 'max_words': 4, 'max_chars': 26,
         'position_wide': 0.86, 'position_reel': 0.72}
bare = lambda t: re.sub(r"[^a-z0-9']", '', t.lower())

def frames(segs, fps):
    """Length of the cut footage: media renders each shot as a whole number of frames."""
    return sum(round((s['out']-s['in'])*fps) for s in segs) / fps

def find(words, phrase, start=0):
    """Index range (i, j) of the first match of `phrase` in the timeline words at or after index `start`."""
    toks = [bare(t) for t in phrase.split() if bare(t)]
    for i in range(start, len(words) - len(toks) + 1):
        if all(bare(words[i+k]['text']) == t for k, t in enumerate(toks)):
            return i, i + len(toks) - 1
    raise SystemExit(f'phrase not found in the edit (after word {start}): "{phrase}". Use the words as spoken in the cut report; '
                     'a longer phrase helps when a short one appears more than once.')

def template_file(name, cfg, proj):
    """Your templates first (the project's templates/ folder, then "templates_dir"), then the skill's example."""
    dirs = [Path(proj)/'templates'] + ([Path(cfg['templates_dir']).expanduser()] if cfg.get('templates_dir') else []) + [SKILL/'templates']
    for d in dirs:
        if (d/f'{name}.html').exists(): return d/f'{name}.html'
    raise SystemExit(f'template "{name}" not found in: ' + ', '.join(map(str, dirs)))

def declared(tpl):
    m = re.search(r"data-composition-variables='(.*?)'", tpl.read_text(), re.S)
    return {v['id'] for v in json.loads(m.group(1))} if m else set()

def beats(edit, design, cfg, proj, dur):
    """design: [{"template", "at", "until"?, "hold"?, "seconds"?, "values"?, "captions"?}] -> placed beats."""
    W, out, pos = edit['words'], [], 0
    for b in design:
        i, j = find(W, b['at'], pos)
        a = W[i]['s']
        z = W[find(W, b['until'], i)[1]]['e'] + b.get('hold', 0.6) if b.get('until') else a + b.get('seconds', 3.0)
        z = min(z, dur)
        tpl = template_file(b['template'], cfg, proj)
        extra = set(b.get('values', {})) - declared(tpl)
        if extra: print(f"  note: {b['template']} has no setting called {', '.join(sorted(extra))} (typo?)")
        out.append({'name': b['template'], 'file': tpl, 'start': round(a, 3), 'end': round(z, 3),
                    'values': {**b.get('values', {}), 'duration': round(z - a, 3)}, 'captions': b.get('captions', True)})
        pos = i + 1
    return out

def stacked_windows(edit):
    """Timeline windows of 9:16 half-and-half shots: captions sit on the seam there."""
    out, t = [], 0.0
    for s in edit['segments']:
        d = s['out'] - s['in']
        if edit['vertical'] and s['shot'] == 'halves':
            if out and abs(out[-1][1] - t) < 1e-6: out[-1][1] = t + d
            else: out.append([t, t + d])
        t += d
    return out

def page(edit, cfg, proj, design=()):
    """-> (index.html text, placed beats)."""
    st = {**STYLE, **cfg.get('captions', {}).get('style', {})}
    W, H = edit['size']; vert = edit['vertical']
    fps = cfg['fps']; dur = frames(edit['segments'], fps)
    placed = beats(edit, design, cfg, proj, dur)
    quiet = [(b['start'], b['end']) for b in placed if not b['captions']]
    seam = stacked_windows(edit)
    size = st['size_reel' if vert else 'size_wide']
    gs = [g for g in E.groups(edit['words'], st['max_words'], st['max_chars']) if not any(a <= g[0]['s'] < z for a, z in quiet)]
    font_face = ''
    if st.get('font_file'):
        f = Path(st['font_file']).expanduser()
        font_face = f"@font-face{{font-family:'{st['font']}';src:url('assets/{f.name}');font-weight:100 900}}"
    cap_html, tl = [], []
    for gi, g in enumerate(gs):
        a = g[0]['s']
        z = min(g[-1]['e'] + .4, gs[gi+1][0]['s'] - .02) if gi + 1 < len(gs) else min(g[-1]['e'] + .4, dur)
        z = max(z, g[-1]['e'])
        top = 0.5 if any(x <= a < y for x, y in seam) else st['position_reel' if vert else 'position_wide']
        spans = ''.join(f'<span class="w" id="w{gi}-{k}">{html.escape(w["text"])}</span> ' for k, w in enumerate(g))
        cap_html.append(f'<div class="cg" style="top:{top*100:.1f}%"><div class="cgi" id="g{gi}">{spans.strip()}</div></div>')
        tl.append(f"tl.fromTo('#g{gi}',{{opacity:0,scale:.94}},{{opacity:1,scale:1,duration:.12,ease:'power2.out'}},{a:.3f});")
        for k, w in enumerate(g):
            tl.append(f"tl.set('#w{gi}-{k}',{{color:HL}},{w['s']:.3f});")
            if k + 1 < len(g): tl.append(f"tl.set('#w{gi}-{k}',{{color:BASE}},{g[k+1]['s']:.3f});")
        tl.append(f"tl.set('#g{gi}',{{opacity:0,visibility:'hidden'}},{z:.3f});")
    beat_html = [f'<div id="beat{i}" data-composition-id="{b["name"]}" data-composition-src="templates/{b["name"]}.html" '
                 f"data-variable-values='{html.escape(json.dumps(b['values']), quote=True)}' data-start=\"{b['start']:.3f}\" "
                 f'data-duration="{b["end"]-b["start"]:.3f}" data-track-index="{3+i}" data-width="{W}" data-height="{H}"></div>'
                 for i, b in enumerate(placed)]
    logo, lg = '', cfg.get('logo') or {}
    if lg.get('file'):
        v, h = lg.get('corner', 'top-right').split('-')
        logo = (f'<img id="logo" class="clip" src="assets/{Path(lg["file"]).name}" data-start="0" data-duration="{dur:.3f}" data-track-index="2" '
                f'style="position:absolute;{v}:{lg.get("margin", 0.04)*H:.0f}px;{h}:{lg.get("margin", 0.04)*H:.0f}px;'
                f'width:{lg.get("width", 0.12)*W:.0f}px;opacity:{lg.get("opacity", 0.9)}">')
    fps_attr = f' data-fps="{fps:g}"' if float(fps).is_integer() else ''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><script src="{GSAP}"></script><style>
{font_face}
body{{margin:0;background:#000}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;background:#000;font-family:'{st['font']}',sans-serif}}
#speaker{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.cg{{position:absolute;left:0;right:0;transform:translateY(-50%);display:flex;justify-content:center}}
.cgi{{max-width:{0.86*W:.0f}px;text-align:center;font-size:{size}px;font-weight:{st['weight']};line-height:1.12;opacity:0;
color:{st['colour']};{'text-transform:uppercase;' if st['uppercase'] else ''}-webkit-text-stroke:{size*0.12:.1f}px {st['outline']};
paint-order:stroke fill;text-shadow:0 {size*0.05:.1f}px {size*0.3:.1f}px rgba(0,0,0,.45);text-wrap:balance}}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" data-duration="{dur:.3f}"{fps_attr}>
<video id="speaker" class="clip" src="assets/speaker.mp4" data-start="0" data-duration="{dur:.3f}" data-track-index="0" muted playsinline></video>
<audio id="dialogue" src="assets/speaker.mp4" data-start="0" data-duration="{dur:.3f}" data-track-index="1" data-volume="1"></audio>
{logo}
{chr(10).join(beat_html)}
{chr(10).join(cap_html)}
</div>
<script>
const HL={json.dumps(st['highlight'])},BASE={json.dumps(st['colour'])};
const tl=gsap.timeline({{paused:true}});
{chr(10).join(tl)}
window.__timelines['main']=tl;
</script></body></html>
''', placed

def sized(tpl, name, W, H):
    """Each edit's copy of a template gets that edit's size on its root, so a template written at a fixed size (say
    1920x1080) isn't laid out 1920 wide inside a 1080-wide reel, which pushed it off the side of the frame."""
    def fix(m):
        return re.sub(r'\s+data-(?:width|height)="[^"]*"', '', m.group(0))[:-1] + f' data-width="{W}" data-height="{H}">'
    return re.sub(r'<div\b[^>]*\bdata-composition-id="%s"[^>]*>' % re.escape(name), fix, tpl, count=1)

def write(edit, cfg, proj):
    """Write <project>/<edit>/index.html, copying the templates (sized to this edit), logo and font it uses."""
    d = Path(proj)/edit['name']
    (d/'assets').mkdir(parents=True, exist_ok=True)
    text, placed = page(edit, cfg, proj, cfg.get('design', {}).get(edit['name'], []))
    if placed: (d/'templates').mkdir(exist_ok=True)
    for b in placed: (d/'templates'/b['file'].name).write_text(sized(b['file'].read_text(), b['name'], *edit['size']))
    st = cfg.get('captions', {}).get('style', {})
    for f in [(cfg.get('logo') or {}).get('file'), st.get('font_file')]:
        if f: shutil.copy(Path(f).expanduser(), d/'assets'/Path(f).name)
    (d/'index.html').write_text(text)
    return d, placed

if __name__ == '__main__':   # self-check on a made-up edit
    words = [{'text': t, 's': s, 'e': s+.3, 'spk': 'L'} for t, s in
             [('Three', 0), ('in', .4), ('four', .8), ('people', 1.2), ('sleep', 1.6), ('badly.', 2.0), ('Here', 3.0), ('is', 3.4), ('why.', 3.8)]]
    seg = lambda a, b, shot: {'in': a, 'out': b, 'spk': 'L', 'shot': shot, 'crop': 'crop=3840:2160:0:0'}
    cfg = {'fps': 25, 'captions': {'style': {'highlight': '#00FF00'}}}
    edit = {'name': 't', 'vertical': True, 'size': [1080, 1920], 'segments': [seg(0, 2.6, 'vfull'), seg(10, 12, 'halves')], 'words': words}
    assert find(words, 'three in four') == (0, 2) and find(words, 'is why', 1) == (7, 8)
    try: find(words, 'not said'); raise AssertionError
    except SystemExit: pass
    assert abs(frames([{'in': 0, 'out': 1.0333}], 30) - 1.0333) < 1e-3 and stacked_windows(edit) == [[2.6, 4.6]]
    h, placed = page(edit, cfg, '.', [{'template': 'stat-counter', 'at': 'three in four', 'until': 'people', 'values': {'value': 75}}])
    assert placed[0]['start'] == 0 and placed[0]['end'] == 2.1 and placed[0]['values'] == {'value': 75, 'duration': 2.1}, placed
    assert 'data-composition-src="templates/stat-counter.html"' in h and '&quot;value&quot;: 75' in h
    assert h.count('class="cg"') == 3 and 'top:50.0%' in h and 'top:72.0%' in h   # the group after 2.6 s sits on the seam
    assert "const HL=\"#00FF00\"" in h and "tl.set('#g0',{opacity:0,visibility:'hidden'}" in h
    h2, _ = page(edit, cfg, '.', [{'template': 'stat-counter', 'at': 'three', 'until': 'badly', 'captions': False}])
    assert h2.count('class="cg"') == 1                                  # captions step aside for a beat that asks for it
    t = (SKILL/'templates/stat-counter.html').read_text()
    assert '<div id="root" data-composition-id="stat-counter" data-width="1080" data-height="1920">' in sized(t, 'stat-counter', 1080, 1920)
    assert sized('<div id="root" data-composition-id="x" data-width="1920" data-height="1080">', 'x', 1080, 1920).count('data-width') == 1
    print('captions.py self-check OK')
