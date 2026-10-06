"""Synthetic logs for the demo. Not real car data.

Writes, in KTuner's CSV export format:
  before.csv  idle, three 2nd-gear full-throttle pulls, coast-downs and cruise
  after.csv   the same drive after a +0.3 AFR change to the high-RPM WOT targets
and frames.bin, raw dongle replies for the simulated live-logging scene.
"""
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_tune import telemetry  # noqa: E402

HEADER = ('Time(s),RPM,MAP(mBar),MAP(Conv),MAF.Hz,MAF,PWMDC,TPS,TPS.CMD,CAM.CMD,CAMA,EXCAM.CMD,EXCAMA,AIGN,FDC,FP1,'
          'STFT,LTFT,LAM,LAM.ADJ,LAM.CMD,FUEL.STAT,KNK.C,KNK.CTRL,ECT(F),IAT(F),VSS(MPH),GEAR,BAT,VTEC\n')
DT = 0.04


def wot_target(rpm):
    """Shape of the stock high-load WOT targets: richer toward redline."""
    points = [(2000, 12.6), (3000, 12.5), (4500, 12.1), (5500, 11.8), (6500, 11.0)]
    for (r0, a0), (r1, a1) in zip(points, points[1:]):
        if rpm <= r1:
            return a0 + (a1 - a0) * max(0.0, rpm - r0) / (r1 - r0)
    return points[-1][1]


def torque(rpm):
    return 0.85 + 0.25 * math.exp(-((rpm - 4600) / 1700) ** 2)


def drive(after=False, seed=1):
    rng = random.Random(seed)
    rows, t, rpm, speed = [], 0.0, 800.0, 0.0

    def row(rpm, map_mbar, tps, afr, cmd, ign, status, vss, gear, knock_ctrl=0.88):
        maf_hz = 2400 + rpm * map_mbar / 1000 * 0.8
        maf = 2.4 + rpm * map_mbar / 1_000_000 * 14
        stft = rng.uniform(-2, 2) if status == 2 else 0.0
        rows.append([round(t, 3), int(rpm), int(map_mbar), round(map_mbar, 1), int(round(maf_hz / 50) * 50), round(maf, 2), 0,
                     round(tps, 1), round(tps, 1), 0.0, 0.0, 0.0, 0.0, round(ign, 1), 1.6, 2.8, round(stft, 2), 1.56,
                     round(afr, 2), round(afr, 2), round(cmd, 2), status, 0, knock_ctrl, 192, 95, round(vss), gear,
                     14.2, 1 if rpm > 5200 and tps > 80 else 0])

    def idle(seconds):
        nonlocal t
        for _ in range(int(seconds / DT)):
            row(800 + rng.uniform(-15, 15), 320, 0, 14.7 + rng.uniform(-0.15, 0.15), 14.7, 8, 2, 0, 1)
            t += DT

    def pull():
        nonlocal t, rpm
        rpm = 2200.0
        while rpm < 6600:
            cmd = wot_target(rpm) + (0.3 if after and rpm >= 5000 else 0)
            gain = 1.0 + (0.012 if after and rpm >= 5000 else 0)
            row(rpm, 985, 100, cmd + rng.uniform(-0.08, 0.08), cmd, 18 + rpm / 400, 1, rpm / 6600 * 62, 2)
            rpm += 1150 * torque(rpm) * gain * DT
            t += DT

    def coast():
        nonlocal t, rpm
        while rpm > 1400:
            row(rpm, 230, 0, 29.4, 29.4, 2, 4, rpm / 6600 * 62, 2)
            rpm -= 900 * DT
            t += DT

    def cruise(seconds, rpm_c=1900):
        nonlocal t
        for _ in range(int(seconds / DT)):
            row(rpm_c + rng.uniform(-20, 20), 420, 14, 14.7 + rng.uniform(-0.1, 0.1), 14.7, 28, 2, 38, 4)
            t += DT
    idle(8)
    for _ in range(3):
        pull()
        coast()
        cruise(12)
    idle(4)
    return rows


def frames(seconds=8):
    """Raw dongle replies (B0 framing) for the simulated live-log scene."""
    out = bytearray()
    for i in range(int(seconds / 0.07)):
        a = bytearray(169); a[0] = 0x62
        for k, did in enumerate((0x2610, 0x2611, 0x2612)):
            a[1 + 56 * k:3 + 56 * k] = did.to_bytes(2, 'big')
        rpm = 800 + 12 * math.sin(i / 3)
        a[9:11] = int(rpm * 4).to_bytes(2, 'big')
        a[14], a[16], a[25] = 40 + 89, 40 + 35, 142
        a[51:53] = int(32.0 / 0.0131572).to_bytes(2, 'big')
        a[67:69] = int((1.0 + 0.01 * math.sin(i / 2)) * 32768).to_bytes(2, 'big')
        a[71:73] = (32768).to_bytes(2, 'big')
        a[69], a[70], a[73] = 130, 130, 2
        a[24] = int((8 + 64) / 0.5)
        b = bytearray(113); b[0] = 0x62
        for k, did in enumerate((0x2613, 0x2660)):
            b[1 + 56 * k:3 + 56 * k] = did.to_bytes(2, 'big')
        b[101] = 52
        c = bytearray(169); c[0] = 0x62
        for k, did in enumerate((0x2662, 0x2663, 0x266C)):
            c[1 + 56 * k:3 + 56 * k] = did.to_bytes(2, 'big')
        c[13] = 113
        body = bytes(a) + bytes(b) + bytes(56) + bytes(c) + bytes(24)
        out += b'\xb0' + (len(body)).to_bytes(2, 'little') + body
    return bytes(out)


def main(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name, after in (('before.csv', False), ('after.csv', True)):
        rows = drive(after=after)
        (target / name).write_text(HEADER + ''.join(','.join(map(str, r)) + '\n' for r in rows), encoding='utf-8')
    (target / 'frames.bin').write_bytes(frames())
    first = telemetry.B0Stream().feed(frames()[:534])
    assert first and telemetry.split_groups(first[0]) is not None, 'synthetic frame layout'
    print(f'wrote {target}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'demo-data')
