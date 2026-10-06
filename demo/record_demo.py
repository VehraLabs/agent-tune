"""Record the short agent-tune demo (docs/demo.gif, plus an MP4 when imageio-ffmpeg is available).

Each step runs the real agent-tune command; the lines on screen are drawn from
its actual JSON output. The datalog comes from demo/make_data.py. The tune file
is supplied with --kcl and is never written to the repository.

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

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 720
BG, FG, DIM, ACCENT, OK, USER = '#111113', '#F4F2EE', '#8A8A90', '#E0661B', '#7FB685', '#9CC3E6'
FONT_PATH = os.environ.get('DEMO_FONT', r'C:\Windows\Fonts\consola.ttf')
BOLD_PATH = os.environ.get('DEMO_FONT_BOLD', r'C:\Windows\Fonts\consolab.ttf')
FONT, BOLD = ImageFont.truetype(FONT_PATH, 24), ImageFont.truetype(BOLD_PATH, 24)
LINE, TOP, LEFT, COLS = 34, 72, 48, 84


class Screen:
    def __init__(self):
        self.lines, self.frames = [], []

    def render(self, ms, cursor=False):
        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 44], fill='#1C1C1F')
        for i, c in enumerate((ACCENT, '#55555A', '#55555A')):
            d.ellipse([20 + i * 24, 15, 34 + i * 24, 29], fill=c)
        d.text((104, 9), 'agent-tune', font=BOLD, fill=FG)
        for row, (text, color, bold) in enumerate(self.lines[-17:]):
            d.text((LEFT, TOP + row * LINE), text, font=BOLD if bold else FONT, fill=color)
        if cursor and self.lines:
            row = min(len(self.lines), 17) - 1
            x = LEFT + d.textlength(self.lines[-1][0], font=FONT)
            d.rectangle([x + 3, TOP + row * LINE + 3, x + 15, TOP + row * LINE + 27], fill=FG)
        self.frames.append((img, ms))

    def blank(self):
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
        self.render(350)

    def result(self, rows, hold):
        for text, color in rows:
            self.lines.append(('  ' + text, color, False))
            self.render(160)
        self.render(int(hold * 1000))

    def card(self, title, lines, hold):
        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        big = ImageFont.truetype(BOLD_PATH, 56)
        y = 250
        tw = d.textlength(title, font=big)
        d.text(((W - tw) / 2, y), title, font=big, fill=FG)
        y += 90
        for text, color in lines:
            tw = d.textlength(text, font=FONT)
            d.text(((W - tw) / 2, y), text, font=FONT, fill=color)
            y += 40
        self.frames.append((img, int(hold * 1000)))
        self.lines = []


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    if r.returncode != 0:
        raise SystemExit(f'command failed: {cmd}\n{r.stdout}\n{r.stderr}')
    return json.loads(r.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kcl', default=os.environ.get('DEMO_KCL'), required=os.environ.get('DEMO_KCL') is None)
    p.add_argument('--out', default=str(ROOT / 'docs' / 'demo.gif'))
    a = p.parse_args()
    work = Path(tempfile.mkdtemp(prefix='agent-tune-demo-'))
    subprocess.run([sys.executable, str(ROOT / 'demo' / 'make_data.py'), str(work)], check=True, capture_output=True)
    (work / 'before.csv').rename(work / 'drive.csv')
    shutil.copy(a.kcl, work / 'stock.kcl')
    at = [sys.executable, '-m', 'agent_tune']

    s = Screen()
    s.card('agent-tune', [('Tune your car with KTuner and an AI agent', FG)], 2.4)

    s.say('You', 'I want more power. How do I get a datalog?', 1.2)
    guide = run(at + ['guide', 'power'], work)
    s.command('agent-tune guide power')
    s.result([('Record:  KTuner -> Connect -> Record', FG),
              ('Drive:   warm up 10 min, then 3 pulls in 2nd gear,', FG),
              ('         2,000 rpm to near redline (only where legal and safe)', FG),
              ('Export:  Record again to stop -> Export Datalog To CSV', FG)], 2.6)
    assert any('3 pulls' in step for step in guide['drive'])

    s.lines = []
    s.say('You', 'Done. Here is drive.csv and my tune.', 1.0)
    check = run(at + ['check-log', 'drive.csv', '--goal', 'power'], work)
    s.command('agent-tune check-log drive.csv --goal power')
    ok = {c['check']: c for c in check['checks']}
    s.result([(('Ready. ' if check['ready'] else 'Not ready. ') + ok['full-throttle pulls']['detail'].split(' (')[0]
                + ', engine warm, knock data present', OK if check['ready'] else ACCENT)], 1.4)
    analysis = run(at + ['analyze', 'drive.csv'], work)
    s.command('agent-tune analyze drive.csv')
    pulls = analysis['pulls']
    afr = sum(p['afr']['median'] for p in pulls) / len(pulls)
    knock = sum(1 for e in analysis['knock_events'] if e['kind'] == 'knock_count')
    s.result([(f'{len(pulls)} full-throttle pulls found', FG),
              (f'Fuel at full throttle: AFR {afr:.1f}  (rich; power band is 12.5-13.2)', FG),
              (f'Knock: {"none" if knock == 0 else knock}', FG)], 2.0)

    s.lines = s.lines[-6:]
    cells = [c for c in run(at + ['tune', 'cells', 'stock.kcl', '--match', 'wot-h-[56][05]00-*'], work)
             if c['id'].rsplit('-', 1)[1] in ('530', '550', '600')]
    s.say('Agent', 'Your tune asks for extra fuel near redline. I suggest one small step: '
                   '+0.3 AFR from 5,000 to 6,500 rpm at full load. Timing stays the same.', 0.6)
    by_rpm = {}
    for c in cells:
        by_rpm.setdefault(c['axis']['RPM'], []).append(c['value'])
    s.result([(f'{rpm} rpm   AFR {min(v):.1f} -> {min(v) + 0.3:.1f}', DIM) for rpm, v in sorted(by_rpm.items())], 3.4)

    s.say('You', 'Do it.', 0.8)
    adds = []
    for col in ('530', '550', '600'):
        adds += ['--add', f'wot-h-[56][05]00-{col}=0.3']
    written = run(at + ['tune', 'set', 'stock.kcl'] + adds + ['-o', 'step-1.kcl'], work)
    s.command('agent-tune tune set stock.kcl --add ... -o step-1.kcl')
    s.result([(f'{written["kcl"]} written, {len(written["changes"])} values changed', FG),
              ('stock.kcl left unchanged', FG)], 1.2)
    s.say('Agent', 'Done. Open step-1.kcl in KTuner, check the changes, and flash it. '
                   'Then log a few pulls and I will compare.', 3.6)

    s.card('agent-tune', [('uv tool install "vehra-agent-tune[mcp]"', ACCENT),
                          ('github.com/VehraLabs/agent-tune', DIM)], 3.2)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # One shared palette so colours do not shift between frames.
    sample = Image.new('RGB', (W, H * 4))
    for k, (f, _) in enumerate(s.frames[1::max(1, len(s.frames) // 4)][:4]):
        sample.paste(f, (0, H * k))
    palette = sample.quantize(colors=48, method=Image.Quantize.MEDIANCUT)
    frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f, _ in s.frames]
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=[d for _, d in s.frames],
                   loop=0, optimize=True, disposal=1)
    total = sum(d for _, d in s.frames) / 1000
    print(f'GIF {out} {out.stat().st_size / 1e6:.1f} MB, {total:.1f} s')
    try:
        import imageio.v2 as imageio
        import numpy as np
        mp4 = out.with_suffix('.mp4')
        with imageio.get_writer(mp4, fps=25, codec='libx264', quality=8, macro_block_size=8) as writer:
            for frame, ms in s.frames:
                arr = np.asarray(frame)
                for _ in range(max(1, round(ms / 40))):
                    writer.append_data(arr)
        print(f'MP4 {mp4} {mp4.stat().st_size / 1e6:.1f} MB')
    except ImportError:
        print('MP4 skipped (install imageio and imageio-ffmpeg)')
    shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
