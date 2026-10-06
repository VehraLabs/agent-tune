"""Record the agent-tune demo as an animated GIF (and MP4 when imageio-ffmpeg is available).

Every command shown is really run and its real output is shown (long JSON is
trimmed with an ellipsis). Data is synthetic: demo/make_data.py writes the
KTuner CSV logs and the replies of a simulated dongle. The tune file is
supplied by you (DEMO_KCL) and is never written to the repository.

  uv run --with pillow --with imageio --with imageio-ffmpeg python demo/record_demo.py --kcl PATH
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
FONT = ImageFont.truetype(os.environ.get('DEMO_FONT', r'C:\Windows\Fonts\consola.ttf'), 17)
BOLD = ImageFont.truetype(os.environ.get('DEMO_FONT_BOLD', r'C:\Windows\Fonts\consolab.ttf'), 17)
LINE, TOP, LEFT, COLS = 22, 58, 28, 112
ROWS = (H - TOP - 20) // LINE


class Screen:
    def __init__(self):
        self.lines = []          # list of (text, color, bold)
        self.frames = []         # (image, duration_ms)

    def render(self, duration, cursor=False):
        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 40], fill='#1C1C1F')
        for i, c in enumerate(('#E0661B', '#55555A', '#55555A')):
            d.ellipse([18 + i * 22, 14, 30 + i * 22, 26], fill=c)
        d.text((96, 11), 'agent-tune demo', font=BOLD, fill=FG)
        d.text((W - 470, 11), 'synthetic data · simulated dongle · real output', font=FONT, fill=ACCENT)
        visible = self.lines[-ROWS:]
        for row, (text, color, bold) in enumerate(visible):
            d.text((LEFT, TOP + row * LINE), text, font=BOLD if bold else FONT, fill=color)
        if cursor and visible:
            text = visible[-1][0]
            x = LEFT + d.textlength(text, font=FONT)
            y = TOP + (len(visible) - 1) * LINE
            d.rectangle([x + 2, y + 2, x + 11, y + 19], fill=FG)
        self.frames.append((img, duration))

    def add(self, text='', color=FG, bold=False):
        for part in (textwrap.wrap(text, COLS, subsequent_indent='  ') or ['']) if text else ['']:
            self.lines.append((part, color, bold))

    def pause(self, seconds):
        self.render(int(seconds * 1000))

    def say(self, who, text, pause=2.2):
        color = USER if who == 'You' else ACCENT
        self.add()
        wrapped = textwrap.wrap(text, COLS - 9)
        for i, part in enumerate(wrapped):
            self.lines.append(((f'{who:>5} › ' if i == 0 else ' ' * 8) + part, color if i == 0 else FG, i == 0))
            self.render(140)
        self.pause(pause)

    def type_command(self, shown, note=None):
        """Type a command; a list is shown as continuation lines joined by backslashes."""
        self.add()
        parts = shown if isinstance(shown, list) else [shown]
        for n, part in enumerate(parts):
            prompt = '$ ' if n == 0 else '    '
            text = part + (' \\' if n < len(parts) - 1 else '')
            self.lines.append((prompt, OK, True))
            for i in range(0, len(text), 3):
                self.lines[-1] = (prompt + text[:i + 3], OK, True)
                self.render(40, cursor=True)
        if note:
            self.lines[-1] = (self.lines[-1][0] + '   ' + note, OK, True)
        self.pause(0.5)

    def output(self, text, limit=14, per_line=55):
        lines = text.rstrip('\n').splitlines()
        shown = lines[:limit]
        for line in shown:
            indent = len(line) - len(line.lstrip())
            for k, part in enumerate(textwrap.wrap(line.strip(), COLS - indent) or ['']):
                self.lines.append((' ' * (indent + (2 if k else 0)) + part, DIM, False))
            self.render(per_line)
        if len(lines) > limit:
            self.add(f'… ({len(lines) - limit} more lines of JSON)', DIM)
        self.pause(1.4)

    def clear(self):
        self.lines = []


def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300,
                            env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    if result.returncode != 0:
        raise SystemExit(f'command failed: {cmd}\n{result.stdout}\n{result.stderr}')
    return result.stdout, result.stderr


def title(screen, lines, seconds):
    screen.clear()
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(r'C:\Windows\Fonts\consolab.ttf', 44)
    y = H // 2 - 30 * len(lines)
    for i, (text, color) in enumerate(lines):
        font = big if i == 0 else FONT
        w = d.textlength(text, font=font)
        d.text(((W - w) / 2, y), text, font=font, fill=color)
        y += 64 if i == 0 else 30
    screen.frames.append((img, int(seconds * 1000)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kcl', default=os.environ.get('DEMO_KCL'), required=os.environ.get('DEMO_KCL') is None,
                   help='a supported .kcl to use as stock.kcl (not stored in the repo)')
    p.add_argument('--out', default=str(ROOT / 'docs' / 'demo.gif'))
    a = p.parse_args()
    work = Path(tempfile.mkdtemp(prefix='agent-tune-demo-'))
    run([sys.executable, str(ROOT / 'demo' / 'make_data.py'), str(work)], ROOT)
    shutil.copy(a.kcl, work / 'stock.kcl')
    at = [sys.executable, '-m', 'agent_tune']
    sim = [sys.executable, str(ROOT / 'demo' / 'sim_cli.py'), str(work / 'frames.bin')]

    s = Screen()
    title(s, [('agent-tune', FG),
              ('Tune your car with the KTuner you already own,', FG),
              ('with an AI agent doing the analysis.', FG),
              ('', FG),
              ('Demo with synthetic logs and a simulated dongle. Every command and its output is real.', DIM)], 4.0)

    s.clear()
    s.say('You', 'I want more power from my Civic. The KTuner is plugged in and my tune is stock.kcl.')
    s.say('Agent', 'First I will find the dongle and read live data. The KTuner app needs to be closed.', 1.6)
    out, _ = run(sim + ['devices'], work)
    s.type_command('agent-tune devices', '(simulated dongle)')
    s.output(out, limit=10)
    out, err = run(sim + ['log', '--seconds', '5', '-o', 'drive.jsonl'], work)
    s.type_command('agent-tune log --seconds 5 -o drive.jsonl', '(simulated dongle)')
    for line in err.strip().splitlines():
        s.add(line.strip(), FG)
        s.render(1000)
    s.output(out, limit=12, per_line=40)
    s.say('Agent', 'Live data looks healthy: idle about 790 rpm, lambda near 1.0, coolant 89 C. Power decisions need '
                   'full-throttle pulls, so I will use the KTuner CSV you recorded with three 2nd-gear pulls.', 3.0)

    s.clear()
    out, _ = run(at + ['analyze', 'before.csv', '--findings'], work)
    s.type_command('agent-tune analyze before.csv --findings')
    s.output(out, limit=40, per_line=35)
    s.say('Agent', 'All three pulls run rich: median AFR about 12.1 at full throttle, below the 12.5-13.2 band where '
                   'naturally aspirated engines usually make best power. Knock count never rose. Let me look at your tune.', 3.2)

    s.clear()
    out, _ = run(at + ['tune', 'check', 'stock.kcl'], work)
    s.type_command('agent-tune tune check stock.kcl')
    s.output(out, limit=10)
    out, _ = run(at + ['tune', 'cells', 'stock.kcl', '--match', 'wot-h-[56][05]00-*'], work)
    cells = [c for c in json.loads(out) if c['id'].rsplit('-', 1)[1] in ('530', '550', '600')]
    s.type_command('agent-tune tune cells stock.kcl --match "wot-h-[56][05]00-*"')
    s.output(out, limit=8)
    s.say('Agent', 'Your full-throttle fuel targets get richer toward redline. My proposal, fueling only and one small step:', 0.8)
    rows = {}
    for c in cells:
        rows.setdefault(c['axis']['RPM'], []).append(c['value'])
    s.add('        RPM    WOT target now (load 530/550/600)    proposed', FG, True)
    for rpm in sorted(rows):
        now = '  '.join(f'{v:5.2f}' for v in rows[rpm])
        new = '  '.join(f'{v + 0.3:5.2f}' for v in rows[rpm])
        s.add(f'       {rpm:>5}    {now:<33}  {new}', FG)
        s.render(220)
    s.say('Agent', '+0.3 AFR on these 12 high-load WOT cells from 5,000 to 6,500 rpm. Timing stays '
                   'unchanged. If knock appears afterwards, we go back.', 2.8)
    s.say('You', 'Sounds good, do it.', 1.2)

    s.clear()
    change = ['--add', 'wot-h-[56][05]00-530=0.3', '--add', 'wot-h-[56][05]00-550=0.3', '--add', 'wot-h-[56][05]00-600=0.3']
    shown = ['agent-tune tune set stock.kcl', '--add "wot-h-[56][05]00-530=0.3"', '--add "wot-h-[56][05]00-550=0.3"',
             '--add "wot-h-[56][05]00-600=0.3"', '-o leaner-top.kcl']
    out, _ = run(at + ['tune', 'set', 'stock.kcl'] + change + ['-o', 'leaner-top.kcl', '--dry-run'], work)
    s.type_command(shown[:-1] + [shown[-1] + ' --dry-run'])
    s.output(out, limit=12, per_line=40)
    out, _ = run(at + ['tune', 'set', 'stock.kcl'] + change + ['-o', 'leaner-top.kcl', '--note', 'WOT +0.3 AFR above 5000 rpm'], work)
    s.type_command(shown[:-1] + [shown[-1] + ' --note "WOT +0.3 AFR above 5000 rpm"'])
    s.output(out, limit=12, per_line=40)
    s.say('Agent', 'Written leaner-top.kcl plus leaner-top.manifest.json with every old, requested and stored value. '
                   'stock.kcl is untouched. Open the new file in KTuner, check the 12 cells, and flash it yourself with stable '
                   'power. Then repeat the same pulls.', 3.4)

    s.clear()
    s.say('You', 'Flashed it and did the same three pulls. Recorded after.csv.', 1.2)
    out, _ = run(at + ['compare', 'before.csv', 'after.csv'], work)
    s.type_command('agent-tune compare before.csv after.csv')
    s.output(out, limit=10, per_line=35)
    result = json.loads(out)
    s.say('Agent', 'Same gear, same conditions, before vs after:', 0.6)
    s.add('        RPM     accel rpm/s before -> after      AFR before -> after', FG, True)
    for row in result['by_rpm']:
        if row['rpm_bin'] < 4000 or 'rpm_rate' not in row:
            continue
        r, f = row['rpm_rate'], row.get('afr', {})
        s.add(f"       {row['rpm_bin']:>5}     {r['before']:6.0f} -> {r['after']:6.0f}  ({r['change'] / r['before'] * 100:+.1f}%)"
              f"        {f.get('before', 0):5.2f} -> {f.get('after', 0):5.2f}", FG)
        s.render(220)
    k = result['knock_count_events']
    s.say('Agent', f"From 5,000 rpm it accelerates up to about 2% faster in the same gear, AFR moved about 0.3 toward the band, and knock events stayed at "
                   f"{k['before']} -> {k['after']}. Next: one more small step, or log knock count before touching timing.", 4.0)

    title(s, [('agent-tune', FG),
              ('uv tool install "agent-tune[mcp] @ git+https://github.com/VehraLabs/agent-tune"', ACCENT),
              ('claude mcp add agent-tune -- agent-tune mcp', ACCENT),
              ('', FG),
              ('You review and flash in KTuner. agent-tune never flashes and never writes to the car.', DIM)], 5.0)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    gif_frames = [f.quantize(colors=16, method=Image.Quantize.MEDIANCUT) for f, _ in s.frames]
    gif_frames[0].save(out, save_all=True, append_images=gif_frames[1:], duration=[d for _, d in s.frames],
                       loop=0, optimize=True, disposal=1)
    print(f'GIF {out} {out.stat().st_size / 1e6:.1f} MB, {len(s.frames)} frames, '
          f'{sum(d for _, d in s.frames) / 1000:.0f} s')
    try:
        import imageio.v2 as imageio
        import numpy as np
        mp4 = out.with_suffix('.mp4')
        with imageio.get_writer(mp4, fps=25, codec='libx264', quality=8, macro_block_size=8) as writer:
            for frame, duration in s.frames:
                arr = np.asarray(frame)
                for _ in range(max(1, round(duration / 40))):
                    writer.append_data(arr)
        print(f'MP4 {mp4} {mp4.stat().st_size / 1e6:.1f} MB')
    except ImportError:
        print('MP4 skipped (install imageio and imageio-ffmpeg)')
    shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
