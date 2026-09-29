"""The grade: crop on the original frame, lanczos scale, then optional LUTs and an optional vignette.

- grade.camera_lut: the camera maker's log -> Rec.709 LUT (e.g. Sony's official S-Log3 LUT). Leave null for footage
  that is already Rec.709 (most phones and cameras in their standard picture profile).
- grade.look_lut: your own creative look, applied after the camera LUT. Optional.
- grade.vignette: 0 (off) to about 0.3, a gentle 16-bit darkening towards the corners.
Crops are written in "4K units" (as if the frame were 3840x2160) and scaled here to the real frame size, so every
camera size goes through one place. Never apply a camera LUT to footage that is already graded."""
from pathlib import Path
import os, re, shutil, subprocess

FF = os.environ.get('PODCAST_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg'

def lut(name, proj=None):
    p = Path(name).expanduser()
    if not p.is_absolute() and proj: p = Path(proj)/p
    if not p.exists(): raise SystemExit(f'LUT not found: {p}')
    return p

def to_source(crop, cfg):
    """'crop=w:h:x:y' in 4K units -> source pixels, even numbers, kept inside the frame."""
    if crop == 'null' or not crop.startswith('crop='): return crop
    sw, sh = cfg['camera']['size']
    k = sw / 3840
    w, h, x, y = (int(v) for v in crop[5:].split(':'))
    ev = lambda v: int(round(v*k/2))*2
    w, h = min(ev(w), sw - sw % 2), min(ev(h), sh - sh % 2)
    x, y = min(ev(x), sw - w), min(ev(y), sh - h)
    return f'crop={w}:{h}:{x}:{y}'

def chain(cfg, crop, size, proj=None):
    w, h = size
    g = cfg.get('grade', {})
    luts = ''.join(f",lut3d=file={lut(g[k], proj)}:interp=tetrahedral" for k in ('camera_lut', 'look_lut') if g.get(k))
    return f"{to_source(crop, cfg)},scale={w}:{h}:flags=lanczos,format=gbrp16le{luts}"

def mask(cfg, size, workdir):
    """16-bit radial darkening mask (ffmpeg's vignette filter is 8-bit and bands), or None when grade.vignette is 0."""
    w, h = size
    strength = float(cfg.get('grade', {}).get('vignette') or 0)
    if strength <= 0: return None
    out = Path(workdir)/f'vignette-{w}x{h}-{strength}.png'
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        expr = f"65535*(1-{strength}*pow(min(1,hypot((X-W/2)/(W/2),(Y-H/2)/(H/2))/1.25),2.2))"
        subprocess.run([FF, '-v', 'error', '-n', '-f', 'lavfi', '-i', f'color=white:s={w}x{h},format=gray16le',
                        '-frames:v', '1', '-vf', f"geq=lum='{expr}',format=gray16le", str(out)], check=True)
    return out

def seam(cfg):
    """The line between the two halves of a half-and-half shot: a colour like "#FFFFFF", or "none"."""
    c = cfg.get('seam', '#FFFFFF')
    return None if not c or str(c).lower() == 'none' else '0x' + re.sub(r'[^0-9A-Fa-f]', '', c)[:6]

def graph(cfg, crop, size, proj=None, vignette=True):
    """filter_complex for inputs [0]=source and, when there is a vignette, [1]=mask; output label [v].
    A 'halves:<crop>|<crop>' shot is the half-and-half: both crops of the same frame side by side (16:9) or stacked, first on
    top (9:16), with an optional thin seam."""
    has_mask = vignette and float(cfg.get('grade', {}).get('vignette') or 0) > 0
    tail = ";[1:v]format=gbrp16le[m];[g][m]blend=all_mode=multiply" if has_mask else ';[g]null'
    if crop.startswith('halves:'):
        (l, r), (w, h) = crop[7:].split('|'), size
        part, stack, box = ((w, h//2), 'vstack', f'x=0:y={h//2-1}:w={w}:h=2') if h > w else ((w//2, h), 'hstack', f'x={w//2-1}:y=0:w=2:h={h}')
        line = f",format=yuv444p10le,drawbox={box}:color={seam(cfg)}@0.85:t=fill" if seam(cfg) else ''
        return (f"[0:v]split[a][b];[a]{chain(cfg, l, part, proj)}[l];[b]{chain(cfg, r, part, proj)}[r];[l][r]{stack}[g]"
                f"{tail}{line}[v]")
    return f"[0:v]{chain(cfg, crop, size, proj)}[g]{tail}[v]"

if __name__ == '__main__':   # self-check: crop scaling and the filter graph shapes
    c4 = {'camera': {'size': [3840, 2160]}, 'grade': {}}
    c1 = {'camera': {'size': [1920, 1080]}, 'grade': {'vignette': 0.2}, 'seam': 'none'}
    assert to_source('crop=1920:1080:960:540', c4) == 'crop=1920:1080:960:540'
    assert to_source('crop=1920:1080:960:540', c1) == 'crop=960:540:480:270'
    assert to_source('crop=1216:2160:2624:0', c1) == 'crop=608:1080:1312:0'          # kept inside the frame
    assert to_source('crop=3840:2160:0:0', {'camera': {'size': [1280, 720]}}) == 'crop=1280:720:0:0'
    assert 'lut3d' not in graph(c4, 'crop=1920:1080:0:0', (1920, 1080)) and '[1:v]' not in graph(c4, 'null', (1920, 1080))
    assert '[1:v]' in graph(c1, 'null', (1920, 1080)) and 'drawbox' not in graph(c1, 'halves:crop=1152:1296:0:0|crop=1152:1296:2000:0', (1920, 1080))
    assert 'drawbox=x=959:y=0:w=2:h=1080:color=0xFFFFFF@0.85' in graph(c4, 'halves:crop=1152:1296:0:0|crop=1152:1296:2000:0', (1920, 1080))
    assert seam({'seam': '#12ab34'}) == '0x12ab34'
    print('grade.py self-check OK')
