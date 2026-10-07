"""Record the agent-tune demo as docs/demo.gif (shown in the README) and docs/demo.mp4.

A KTuner owner who wants more power asks what to do. The agent explains how to
drive for a datalog, checks the log, explains the analysis, proposes one small
change and writes it. Each step runs the real agent-tune command and the lines
on screen come from its JSON output. The datalog comes from demo/make_data.py;
the tune file is passed with --kcl and is never written to the repository.

  uv run --with pillow --with imageio --with imageio-ffmpeg --with numpy python demo/record_demo.py --kcl PATH
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MAC = sys.platform == 'darwin'
W, H = 1280, 720
BG, TITLE_BG, FG, DIM, ACCENT, OK, USER = '#111113', '#2A2A2E', '#F4F2EE', '#9A9AA0', '#E0661B', '#7FB685', '#9CC3E6'
LIGHTS = ('#FF5F57', '#FEBC2E', '#28C840')
# Menlo ships with macOS in one .ttc file: index 0 is regular, index 1 is bold.
FONT_PATH = os.environ.get('DEMO_FONT', '/System/Library/Fonts/Menlo.ttc' if MAC else r'C:\Windows\Fonts\consola.ttf')
BOLD_PATH = os.environ.get('DEMO_FONT_BOLD', '/System/Library/Fonts/Menlo.ttc' if MAC else r'C:\Windows\Fonts\consolab.ttf')
BOLD_INDEX = 1 if MAC and 'DEMO_FONT_BOLD' not in os.environ else 0
FONT, BOLD = ImageFont.truetype(FONT_PATH, 21), ImageFont.truetype(BOLD_PATH, 21, index=BOLD_INDEX)
TITLE = ImageFont.truetype(FONT_PATH, 16)
# The window sits on a gradient backdrop with a soft shadow, like a screenshot of a Mac window.
M, RADIUS, TB = 28, 12, 36
X0, Y0, X1, Y1 = M, M, W - M, H - M
LINE, COLS = 29, 92
LEFT, TOP = X0 + 24, Y0 + TB + 14
ROWS = (Y1 - 12 - TOP) // LINE


def make_gradient():
    top, bottom = (62, 64, 84), (18, 18, 26)
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def make_window_backdrop():
    img = make_gradient()
    shadow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle([X0, Y0 + 14, X1, Y1 + 14], radius=RADIUS, fill=170)
    img.paste((0, 0, 0), mask=shadow.filter(ImageFilter.GaussianBlur(20)))
    return img


GRADIENT = make_gradient()
WINDOW_BACKDROP = make_window_backdrop()


def draw_window(d):
    d.rounded_rectangle([X0, Y0, X1, Y1], radius=RADIUS, fill=BG)
    d.rounded_rectangle([X0, Y0, X1, Y0 + TB + 20], radius=RADIUS, fill=TITLE_BG)
    d.rectangle([X0, Y0 + TB, X1, Y0 + TB + 20], fill=BG)
    d.line([(X0, Y0 + TB), (X1, Y0 + TB)], fill='#000000')
    for i, c in enumerate(LIGHTS):
        cx, cy = X0 + 22 + i * 20, Y0 + TB // 2
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=c)
    tw = d.textlength('agent-tune', font=TITLE)
    d.text(((W - tw) / 2, Y0 + 9), 'agent-tune', font=TITLE, fill=DIM)


class Screen:
    def __init__(self):
        self.lines, self.frames = [], []

    def render(self, ms, cursor=False):
        img = WINDOW_BACKDROP.copy()
        d = ImageDraw.Draw(img)
        draw_window(d)
        visible = self.lines[-ROWS:]
        for row, (text, color, bold) in enumerate(visible):
            d.text((LEFT, TOP + row * LINE), text, font=BOLD if bold else FONT, fill=color)
        if cursor and visible:
            row = len(visible) - 1
            x = LEFT + d.textlength(visible[-1][0], font=BOLD)
            d.rectangle([x + 3, TOP + row * LINE + 3, x + 14, TOP + row * LINE + 24], fill=FG)
        self.frames.append((img, ms))

    def clear(self):
        self.lines = []

    def blank(self):
        if self.lines:
            self.lines.append(('', FG, False))

    def say(self, who, text, hold):
        self.blank()
        color = USER if who == 'You' else ACCENT
        for i, part in enumerate(textwrap.wrap(text, COLS - 8)):
            self.lines.append(((f'{who:>5}  ' if i == 0 else ' ' * 7) + part, color if i == 0 else FG, i == 0))
        self.render(int(hold * 1000))

    def command(self, text):
        self.blank()
        self.lines.append(('$ ', OK, True))
        for i in range(0, len(text), 4):
            self.lines[-1] = ('$ ' + text[:i + 4], OK, True)
            self.render(35, cursor=True)
        self.render(400)

    def heading(self, text, step_ms=250):
        self.lines.append(('  ' + text, FG, True))
        self.render(step_ms)

    def item(self, text, color=FG, indent=4, step_ms=260):
        hang = ' ' * (indent + 3)
        for i, part in enumerate(textwrap.wrap(text, COLS - indent - 3)):
            self.lines.append(((' ' * indent if i == 0 else hang) + part, color, False))
        self.render(step_ms)

    def hold(self, seconds):
        self.render(int(seconds * 1000))

    def card(self, title, lines, hold):
        img = GRADIENT.copy()
        d = ImageDraw.Draw(img)
        big = ImageFont.truetype(BOLD_PATH, 56, index=BOLD_INDEX)
        y = 250
        d.text(((W - d.textlength(title, font=big)) / 2, y), title, font=big, fill=FG)
        y += 90
        for text, color in lines:
            d.text(((W - d.textlength(text, font=FONT)) / 2, y), text, font=FONT, fill=color)
            y += 38
        self.frames.append((img, int(hold * 1000)))
        self.clear()


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    if r.returncode != 0:
        raise SystemExit(f'command failed: {cmd}\n{r.stdout}\n{r.stderr}')
    return json.loads(r.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kcl', default=os.environ.get('DEMO_KCL'), required=os.environ.get('DEMO_KCL') is None)
    p.add_argument('--out', default=str(ROOT / 'docs' / 'demo.mp4'))
    a = p.parse_args()
    work = Path(tempfile.mkdtemp(prefix='agent-tune-demo-'))
    subprocess.run([sys.executable, str(ROOT / 'demo' / 'make_data.py'), str(work)], check=True, capture_output=True)
    (work / 'before.csv').rename(work / 'drive.csv')
    shutil.copy(a.kcl, work / 'stock.kcl')
    at = [sys.executable, '-m', 'agent_tune']
    s = Screen()

    s.card('agent-tune', [('Your AI tuning assistant for KTuner', FG)], 2.6)

    # 1. What to do first: how to drive for a datalog.
    s.say('You', 'I have a KTuner on my Civic and I want more power. What should I do first?', 2.4)
    s.say('Agent', 'First we need a datalog: a recording of your engine during a few full-throttle runs. '
                   'It shows how much fuel and timing the engine gets, and whether it knocks. Here is how to record one.', 4.0)
    guide = run(at + ['guide', 'power'], work)
    s.clear()
    s.command('agent-tune guide power')
    n = 1
    s.heading('Before you drive')
    for step in guide['before_you_drive']:
        s.item(f'{n}. {step}'); n += 1
    s.heading('On the road  (only where it is legal and safe)')
    for step in guide['on_the_road']['steps']:
        s.item(f'{n}. {step}'); n += 1
    s.heading('After the drive')
    for step in guide['after_the_drive'][:-1]:
        s.item(f'{n}. {step}'); n += 1
    s.hold(7.0)

    # 2. Check the log, then explain the analysis.
    s.clear()
    s.say('You', 'Done. Here is my datalog, drive.csv, and my tune, stock.kcl.', 1.8)
    check = run(at + ['check-log', 'drive.csv', '--goal', 'power'], work)
    s.command('agent-tune check-log drive.csv --goal power')
    status = {c['check']: c for c in check['checks']}
    for name in ('engine warm', 'full-throttle runs', 'knock data'):
        c = status[name]
        s.item(f"{'OK ' if c['ok'] else 'NO '} {name}: {c['detail'].split(' (')[0]}", OK if c['ok'] else ACCENT, indent=2)
    s.item(check['summary'], OK if check['ready'] else ACCENT, indent=2)
    s.hold(1.6)
    analysis = run(at + ['analyze', 'drive.csv'], work)
    s.command('agent-tune analyze drive.csv')
    pulls = analysis['pulls']
    afr = sum(p['afr']['median'] for p in pulls) / len(pulls)
    knock = sum(1 for e in analysis['knock_events'] if e['kind'] == 'knock_count')
    s.item(f'{len(pulls)} full-throttle runs in 2nd gear', indent=2)
    s.item(f'Knock: {"none in any run" if knock == 0 else knock}', indent=2)
    s.item(f'Fuel at full throttle: AFR {afr:.1f}', indent=2)
    s.say('Agent', f'Good news: no knock. The fuel is on the rich side near redline: AFR {afr:.1f}, where engines '
                   'like yours usually make the most power around 12.5 to 13.2. Extra fuel is safe, but it costs '
                   'a little power.', 5.0)

    # 3. Propose one small change and write it.
    s.clear()
    cells = [c for c in run(at + ['tune', 'cells', 'stock.kcl', '--match', 'wot-h-[56][05]00-*'], work)
             if c['id'].rsplit('-', 1)[1] in ('530', '550', '600')]
    s.command('agent-tune tune cells stock.kcl --match "wot-h-*"')
    by_rpm = {}
    for c in cells:
        by_rpm.setdefault(c['axis']['RPM'], []).append(c['value'])
    s.heading('Full-throttle fuel target (AFR)     now  ->  suggested')
    for rpm, values in sorted(by_rpm.items()):
        s.item(f'at {rpm:>4} rpm{" " * 23}{min(values):4.1f}  ->  {min(values) + 0.3:4.1f}', indent=2)
    s.say('Agent', 'I suggest one small step: 0.3 leaner at full throttle from 5,000 to 6,500 rpm. Timing stays '
                   'the same. Shall I write it to a new file?', 3.6)
    s.say('You', 'Yes, do it.', 1.0)
    adds = []
    for col in ('530', '550', '600'):
        adds += ['--add', f'wot-h-[56][05]00-{col}=0.3']
    written = run(at + ['tune', 'set', 'stock.kcl'] + adds + ['-o', 'step-1.kcl'], work)
    s.command('agent-tune tune set stock.kcl --add ... -o step-1.kcl')
    s.item(f'{written["kcl"]} written: {len(written["changes"])} values changed', OK, indent=2)
    s.item('stock.kcl unchanged', OK, indent=2)
    s.hold(1.4)

    # 4. Hand-off.
    s.clear()
    s.say('Agent', 'Your new tune is ready. Next:', 0.8)
    for i, step in enumerate(['Open step-1.kcl in KTuner and check the 12 changed values.',
                              'Flash it in KTuner, with a healthy battery or a charger connected.',
                              'Do the same 3 runs, record a new datalog, and send it to me.',
                              'I will compare the two drives and check for knock before suggesting the next step.'], 1):
        s.item(f'{i}. {step}', indent=9, step_ms=900)
    s.hold(4.5)

    s.card('agent-tune', [('uv tool install "vehra-agent-tune[mcp]"', ACCENT),
                          ('github.com/VehraLabs/agent-tune', DIM)], 3.4)

    import imageio.v2 as imageio
    import numpy as np
    out = Path(a.out).with_suffix('.mp4')
    out.parent.mkdir(parents=True, exist_ok=True)
    with imageio.get_writer(out, fps=25, codec='libx264', quality=8, macro_block_size=8,
                            ffmpeg_params=['-movflags', '+faststart', '-pix_fmt', 'yuv420p']) as writer:
        for frame, ms in s.frames:
            arr = np.asarray(frame)
            for _ in range(max(1, round(ms / 40))):
                writer.append_data(arr)
    total = sum(ms for _, ms in s.frames) / 1000
    print(f'MP4 {out} {out.stat().st_size / 1e6:.1f} MB, {total:.0f} s')

    # GIF for the README (GitHub plays GIFs inline). One shared palette keeps colours stable.
    sample = Image.new('RGB', (W, H * 4))
    for k, (f, _) in enumerate(s.frames[1::max(1, len(s.frames) // 4)][:4]):
        sample.paste(f, (0, H * k))
    palette = sample.quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f, _ in s.frames]
    gif = out.with_suffix('.gif')
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=[ms for _, ms in s.frames],
                   loop=0, optimize=True, disposal=1)
    print(f'GIF {gif} {gif.stat().st_size / 1e6:.1f} MB')
    shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
