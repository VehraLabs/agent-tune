import asyncio
import json
import math
import os
from pathlib import Path
import threading

import pytest

from agent_tune import analyze, cli, logs, suggest, telemetry, tune
from agent_tune.kcl import decode, patch

HEADER = 'Time(s),RPM,MAP(mBar),MAF.Hz,MAF,TPS,AIGN,STFT,LTFT,LAM,LAM.CMD,FUEL.STAT,KNK.C,KNK.CTRL,ECT(F),IAT(F),VSS(MPH)\n'


def group(size, dids):
    raw = bytearray(size)
    raw[0] = 0x62
    for i, did in enumerate(dids):
        raw[1 + 56 * i:3 + 56 * i] = did.to_bytes(2, 'big')
    return raw


def frame(rpm=800.0, lam=1.0, cmd=1.0, maf_hz=2500, stft=0.0, status=2, tps=0.0, gear=0, tps_cmd=0.0,
          cam=0.0, cam_cmd=0.0, excam=0.0, excam_cmd=0.0, fp1=0.0):
    a = group(169, (0x2610, 0x2611, 0x2612))
    a[9:11] = int(rpm * 4).to_bytes(2, 'big')
    a[14], a[16] = 40 + 88, 40 + 30
    a[27:29] = round(fp1 / 0.004).to_bytes(2, 'big')
    a[67:69] = min(65535, int(lam * 32768)).to_bytes(2, 'big')
    a[71:73] = min(65535, int(cmd * 32768)).to_bytes(2, 'big')
    a[69], a[70], a[73] = round((100 + stft) / 0.78125), 128, status
    a[123:125] = int(tps / 0.005).to_bytes(2, 'big')
    a[129:131] = round(tps_cmd / 0.006).to_bytes(2, 'big')
    a[159] = gear
    a[24] = int((15 + 64) / 0.5)
    b = group(113, (0x2613, 0x2660))
    b[101] = maf_hz // 50
    c = group(169, (0x2662, 0x2663, 0x266C))
    c[35:37] = round(cam * 10).to_bytes(2, 'big')
    c[55:57] = round(cam_cmd * 10).to_bytes(2, 'big')
    c[156], c[157] = round(excam * 5), round(excam_cmd * 5)
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


def test_gear_throttle_command_cams_and_fp1_decode():
    f = frame(rpm=3000, gear=3, tps_cmd=63.5, cam=38.7, cam_cmd=55.0, excam=12.4, excam_cmd=44.8, fp1=11.28)
    values = telemetry.decode_groups(telemetry.split_groups(f))
    assert values['gear'] == 3 and abs(values['tps_cmd_pct'] - 63.498) < 1e-6
    assert abs(values['cam_deg'] - 38.7) < 1e-6 and abs(values['cam_cmd_deg'] - 55.0) < 1e-6
    assert abs(values['excam_deg'] - 12.4) < 1e-6 and abs(values['excam_cmd_deg'] - 44.8) < 1e-6
    assert abs(values['fuel_pressure'] - 11.28) < 1e-6
    assert {'gear', 'cam_deg', 'tps_cmd_pct'} <= set(logs.UNITS)
    not_decoded = telemetry.platform()['not_decoded']
    assert 'gear' not in not_decoded and 'knock count' in not_decoded and 'VTEC state' in not_decoded


def test_usb_pull_reports_gear_and_cam(tmp_path):
    idle = [frame(rpm=800, gear=1) for _ in range(20)]
    pull = [frame(rpm=2000 + 40 * i, tps=100, gear=2, cam=30 + i * 0.05, tps_cmd=100) for i in range(100)]
    p = tmp_path / 'pull.jsonl'
    write_usb_log(p, idle + pull)
    result = analyze.analyze(logs.load(p))
    assert len(result['pulls']) == 1 and result['pulls'][0]['gear'] == 2
    assert all('cam_deg' in b for b in result['pulls'][0]['by_rpm'])


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
    assert set(port.writes) == {b'\xb0'} and summary.telemetry_frames == 5 and summary.unknown_frames == 0
    log = logs.load(out)
    assert log.source == 'agent-tune-usb' and log.rows[0]['ch']['rpm'] == 1500
    with pytest.raises(FileExistsError):
        telemetry.record(FakePort([]), 0.1, out)


def test_unknown_frames_are_logged_raw(tmp_path):
    body = bytes(531)  # right length, but not the platform layout
    reply = b'\xb0' + (531).to_bytes(2, 'little') + body
    out = tmp_path / 'u.jsonl'
    summary = telemetry.record(FakePort([reply] * 3), 0.3, out, interval=0.02)
    assert summary.frames == 3 and summary.telemetry_frames == 0 and summary.unknown_frames == 3
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    assert lines[1]['frame'] == reply.hex()
    with pytest.raises(ValueError, match='no decoded frames'):
        logs.load(out)


def test_platform_from_json_path(tmp_path):
    custom = dict(telemetry.platform(), id='my-car')
    custom['channels'] = [c for c in custom['channels'] if c['name'] == 'rpm']
    path = tmp_path / 'my-car.json'
    path.write_text(json.dumps(custom), encoding='utf-8')
    assert set(telemetry.decode_groups(telemetry.split_groups(frame(rpm=3200), str(path)), str(path))) == {'rpm'}
    with pytest.raises(ValueError, match='Unknown platform'):
        telemetry.platform('nope')


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
    assert {'list_devices', 'record_log', 'analyze_log', 'compare_logs', 'tune_check', 'tune_tables', 'tune_cells',
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
    result = tune.check(bad)
    assert result['supported'] is False and 'KTUNERK' in result['reason']
    with pytest.raises(ValueError):
        tune.cells(bad, allow_unverified=True)


def test_cell_definitions_are_consistent():
    width = {'float32-le': 4, 'u8-reciprocal': 1}
    assert len(patch.CELLS) == 1502
    masked = set()
    for first, last in decode.MASKED:
        masked.update(range(first, last))
    owner = {}
    for cell_id, cell in patch.CELLS.items():
        for offset in cell.get('linked_offsets') or [cell['offset']]:
            for b in range(offset, offset + width.get(cell['encoding'], 2)):
                assert decode.START <= b < decode.END, cell_id
                assert b in masked, f'{cell_id} byte {b} is not excluded from the family fingerprint'
                assert owner.setdefault(b, cell_id) == cell_id, f'{cell_id} overlaps {owner[b]}'
        assert cell['label'] and cell['table'] and isinstance(cell['axis'], dict), cell_id


def test_plan_changes_byte_deltas():
    values = {k: 20.0 if v['encoding'] == 'i16-le-scale10' else 14.7 if v['encoding'] == 'u8-reciprocal'
              else 1.0 if v['encoding'] == 'float32-le' else 0.0 if v['encoding'] == 'u16-le-trim'
              else 100.0 if v['encoding'] == 'u16-le-mbar' else 3000 for k, v in patch.CELLS.items()}
    values.update({'rev-high-limit': 6800, 'rev-high-restart': 6600, 'rev-low-limit': 4800, 'rev-low-restart': 4200,
                   'vtec-lower-engage': 5400, 'vtec-lower-disengage': 5100, 'ect-high-104': 1.5})
    decoded = {'values': values,
               'rev_linked': {o: values[n] for n, offs in patch.rev_limits.GROUPS.items() for o in offs},
               'vtec_linked': {o: values[n] for n, offs in patch.vtec.GROUPS.items() for o in offs},
               'map_counts': {k: 760 for k, v in patch.CELLS.items() if v['encoding'] == 'u16-le-mbar'},
               'trim_counts': {k: 32768 for k, v in patch.CELLS.items() if v['encoding'] == 'u16-le-trim'}}
    changes, edits = patch.plan_changes({'ign-base-l-500-131': 20.5, 'wot-h-6500-600': 12.5, 'rev-high-limit': 7000,
                                         'cylinder-trim-1': 1.0, 'fuel-map-low-cut-rpm-1500': 150}, decoded)
    assert changes[410515] == 5                       # 200 -> 205 counts, low byte only
    wot = patch.CELLS['wot-h-6500-600']
    assert wot['offset'] == 426834 + 18 + 9 * 20 and wot['offset'] in changes  # row 18 (6500 rpm), column 9 (600)
    assert abs({e['cell']: e['encoded_value'] for e in edits}['wot-h-6500-600'] - 12.5) < 0.05
    for o in patch.rev_limits.GROUPS['rev-high-limit']:  # 6800 (0x1A90) -> 7000 (0x1B58) in every linked copy
        assert (changes[o], changes[o + 1]) == (0x58 - 0x90, 1)
    assert {e['cell']: e['encoded_value'] for e in edits}['cylinder-trim-1'] == pytest.approx(1.0, abs=0.01)
    assert {e['cell']: e['encoded_storage_count'] for e in edits}['fuel-map-low-cut-rpm-1500'] == 1140
    with pytest.raises(ValueError, match='accepts only'):
        patch.plan_changes({'ect-high-104': 0.7}, decoded)
    with pytest.raises(ValueError, match='below High Limit'):
        patch.plan_changes({'rev-high-restart': 6900}, decoded)
