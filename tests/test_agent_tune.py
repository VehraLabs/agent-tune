import asyncio
import json
import math
import os
from pathlib import Path
import threading

import pytest

from agent_tune import analyze, cli, logs, suggest, telemetry, tune

HEADER = 'Time(s),RPM,MAP(mBar),MAF.Hz,MAF,TPS,AIGN,STFT,LTFT,LAM,LAM.CMD,FUEL.STAT,KNK.C,KNK.CTRL,ECT(F),IAT(F),VSS(MPH)\n'


def group(size, dids):
    raw = bytearray(size)
    raw[0] = 0x62
    for i, did in enumerate(dids):
        raw[1 + 56 * i:3 + 56 * i] = did.to_bytes(2, 'big')
    return raw


def frame(rpm=800.0, lam=1.0, cmd=1.0, maf_hz=2500, stft=0.0, status=2, tps=0.0):
    a = group(169, (0x2610, 0x2611, 0x2612))
    a[9:11] = int(rpm * 4).to_bytes(2, 'big')
    a[14], a[16] = 40 + 88, 40 + 30
    a[67:69] = min(65535, int(lam * 32768)).to_bytes(2, 'big')
    a[71:73] = min(65535, int(cmd * 32768)).to_bytes(2, 'big')
    a[69], a[70], a[73] = round((100 + stft) / 0.78125), 128, status
    a[123:125] = int(tps / 0.005).to_bytes(2, 'big')
    a[24] = int((15 + 64) / 0.5)
    b = group(113, (0x2613, 0x2660))
    b[101] = maf_hz // 50
    c = group(169, (0x2662, 0x2663, 0x266C))
    return bytes(3) + bytes(a) + bytes(b) + bytes(56) + bytes(c) + bytes(24)


def write_usb_log(path, frames):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'format': 'agent-tune.log.v1', 'platform': telemetry.DEFAULT_PLATFORM}) + '\n')
        for i, f in enumerate(frames):
            groups = telemetry.split_groups(f)
            fh.write(json.dumps({'t': round(i * 0.07, 3), 'ch': {}, 'raw': {k: v.hex() for k, v in groups.items()}}) + '\n')


def test_frame_decoding_and_stream():
    f = frame(rpm=2500, lam=0.95, cmd=0.9, maf_hz=3000, stft=3.125, tps=42.5)
    body = f[3:]
    wire = b'\x00\xff' + b'\xb0' + (531).to_bytes(2, 'little') + body
    stream = telemetry.B0Stream()
    frames = stream.feed(wire[:100]) + stream.feed(wire[100:])
    assert len(frames) == 1 and stream.discarded == 2
    groups = telemetry.split_groups(f)
    values = telemetry.decode_groups(groups)
    assert values['rpm'] == 2500 and abs(values['lambda_measured'] - 0.95) < 1e-4
    assert values['maf_hz'] == 3000 and abs(values['stft_pct'] - 3.125) < 1e-6 and abs(values['tps_pct'] - 42.5) < 1e-6
    assert values['ign_deg'] == 15 and values['ect_c'] == 88 and values['fuel_status'] == 2
    assert telemetry.split_groups(f[:-1]) is None


class FakePort:
    def __init__(self, replies):
        self.replies, self.writes = list(replies), []

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def read(self, n):
        return self.replies.pop(0) if self.replies else b''


def test_record_sends_only_b0(tmp_path):
    reply = b'\xb0' + (531).to_bytes(2, 'little') + frame(rpm=1500)[3:]
    port = FakePort([reply] * 5)
    out = tmp_path / 'x.jsonl'
    summary = telemetry.record(port, 0.3, out, interval=0.02)
    assert set(port.writes) == {b'\xb0'} and summary.telemetry_frames == 5
    log = logs.load(out)
    assert log.source == 'agent-tune-usb' and log.rows[0]['ch']['rpm'] == 1500
    with pytest.raises(FileExistsError):
        telemetry.record(FakePort([]), 0.1, out)


def test_ceiling_and_units(tmp_path):
    p = tmp_path / 'u.jsonl'
    write_usb_log(p, [frame(lam=2.0, cmd=2.0), frame(lam=1.02)])
    log = logs.load(p)
    assert log.rows[0]['ch'].get('afr_ceiling') == 1 and 'afr' not in log.rows[0]['ch']
    assert abs(log.rows[1]['ch']['afr'] - 1.02 * 14.7) < 1e-3
    csv = tmp_path / 'k.csv'
    csv.write_text(HEADER + '0,800,350,2500,3,0,5,0,0,29.4,29.4,4,0,0.8,194,100,60\n'
                            '0.1,800,350,2500,3,0,5,0,0,14.5,14.7,2,0,0.8,194,100,60\n', encoding='utf-8')
    k = logs.load(csv)
    assert k.rows[0]['ch']['afr_ceiling'] == 1
    ch = k.rows[1]['ch']
    assert abs(ch['ect_c'] - 90) < 1e-9 and abs(ch['map_kpa'] - 35) < 1e-9 and abs(ch['speed_kph'] - 96.56) < 0.01


def synthetic_pull_csv(path, afr=12.2, knock=False, rate=1.0):
    rows, t, knocks = [], 0.0, 0
    for i in range(40):  # idle
        rows.append([t, 800, 300, 2500, 3, 0, 10, 0, 0, 14.7, 14.7, 2, 0, 0.8, 194, 95, 0]); t += 0.05
    rpm = 2000.0
    while rpm < 6500:  # full-throttle pull
        if knock and 4500 <= rpm < 4600:
            knocks += 1
        rows.append([round(t, 3), int(rpm), 980, 6000, 80, 100, 30, 0, 0, afr, 12.5, 1, knocks, 0.8, 194, 95, 60])
        rpm += 40 * rate; t += 0.05
    path.write_text(HEADER + ''.join(','.join(map(str, r)) + '\n' for r in rows), encoding='utf-8')


def test_analysis_finds_pulls_rich_afr_and_knock(tmp_path):
    synthetic_pull_csv(tmp_path / 'p.csv', afr=12.0, knock=True)
    result = analyze.analyze(logs.load(tmp_path / 'p.csv'))
    assert len(result['pulls']) == 1 and result['pulls'][0]['knock_count_increase'] > 0
    topics = {f['topic'] for f in result['findings']}
    assert {'wot_fueling', 'knock'} <= topics
    assert any('richer' in f['text'] for f in result['findings'])
    synthetic_pull_csv(tmp_path / 'lean.csv', afr=13.6)
    lean = analyze.analyze(logs.load(tmp_path / 'lean.csv'))
    assert any(f['level'] == 'warn' and 'leaner' in f['text'] for f in lean['findings'])


def test_compare_detects_faster_pull(tmp_path):
    synthetic_pull_csv(tmp_path / 'a.csv', rate=1.0)
    synthetic_pull_csv(tmp_path / 'b.csv', rate=1.1)
    result = analyze.compare(logs.load(tmp_path / 'a.csv'), logs.load(tmp_path / 'b.csv'))
    changes = [r['rpm_rate']['change'] for r in result['by_rpm'] if 'rpm_rate' in r]
    assert changes and all(c > 0 for c in changes)


def test_afm_suggestions_need_agreeing_sessions(tmp_path):
    curve = [1.0 + 0.1 * i for i in range(103)]

    def session(name, stft):
        p = tmp_path / name
        write_usb_log(p, [frame(rpm=1800, maf_hz=2500, stft=stft, status=2) for _ in range(150)])
        return logs.load(p)
    a, b, drift = session('a.jsonl', 3.9), session('b.jsonl', 3.1), session('c.jsonl', -7.0)
    alone = suggest.afm([a], curve)
    assert not alone['changes'] and 'needs_more_sessions' in alone['points'][0]['reasons']
    agree = suggest.afm([a, b], curve)
    assert len(agree['changes']) == 1
    conflict = suggest.afm([a, drift], curve)
    assert not conflict['changes'] and 'sessions_disagree' in conflict['points'][0]['reasons']


def test_cli_analyze_and_errors(tmp_path, capsys):
    synthetic_pull_csv(tmp_path / 'p.csv')
    assert cli.main(['analyze', str(tmp_path / 'p.csv'), '--findings']) == 0
    assert isinstance(json.loads(capsys.readouterr().out), list)
    assert cli.main(['analyze', str(tmp_path / 'missing.csv')]) == 1
    assert 'error' in json.loads(capsys.readouterr().out)


def test_mcp_server_lists_tools():
    pytest.importorskip('mcp')
    from agent_tune import mcp_server
    tools = asyncio.run(mcp_server.server.list_tools())
    names = {t.name for t in tools}
    assert {'list_devices', 'record_log', 'analyze_log', 'compare_logs', 'tune_check', 'tune_cells',
            'tune_write', 'suggest_afm', 'platforms'} <= names


KCL = os.environ.get('AGENT_TUNE_TEST_KCL')


@pytest.mark.skipif(not KCL, reason='set AGENT_TUNE_TEST_KCL to a supported .kcl to run')
def test_kcl_roundtrip(tmp_path):
    assert tune.check(KCL)['supported']
    changes = tune.plan(KCL, scale={'wot-h-6500-*': 0.98}, add={'ign-max-h-6000-*': -0.5})
    result = tune.write(KCL, changes, tmp_path / 'new.kcl', note='test')
    assert tune.check(result['kcl'])['supported'] and len(result['changes']) == len(changes)
    stored = {c['id']: c['value'] for c in tune.cells(result['kcl'])}
    for change in result['changes']:
        assert stored[change['id']] == change['stored']
    with pytest.raises(ValueError):
        tune.write(KCL, changes, result['kcl'])
    with pytest.raises(ValueError):
        tune.write(KCL, changes, KCL)


def test_unsupported_kcl_is_refused(tmp_path):
    bad = tmp_path / 'bad.kcl'
    bad.write_bytes(b'not a tune')
    assert tune.check(bad)['supported'] is False
