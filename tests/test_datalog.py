import pytest

from agent_tune import cli, datalog, logs

HEADER = 'Time(s),RPM,MAP(mBar),MAF.Hz,MAF,TPS,STFT,LTFT,LAM,LAM.CMD,FUEL.STAT,KNK.C,ECT(F),IAT(F),GEAR\n'


def write_csv(path, rows):
    path.write_text(HEADER + ''.join(','.join(map(str, r)) + '\n' for r in rows), encoding='utf-8')
    return logs.load(path)


def drive(pulls=3, ect_f=194, gears=(2, 2, 2), iat_f=(95, 97, 99), cruise_s=60):
    rows, t = [], 0.0
    for _ in range(int(20 / 0.05)):
        rows.append([round(t, 2), 800, 300, 2500, 3, 0, 1, 1, 14.7, 14.7, 2, 0, ect_f, 95, 1]); t += 0.05
    for n in range(pulls):
        rpm = 2000.0
        while rpm < 6600:
            rows.append([round(t, 2), int(rpm), 980, 6000, 60, 100, 0, 0, 12.4, 12.5, 1, 0, ect_f, iat_f[n], gears[n]])
            rpm += 50; t += 0.05
        for _ in range(int(cruise_s / 0.05)):
            rows.append([round(t, 2), 2000 + (t % 7) * 200, 300 + (t % 5) * 80, 3000, 6, 14, 1, 1, 14.7, 14.7, 2, 0,
                         ect_f, 95, 4]); t += 0.05
    return rows


def test_guide_covers_every_goal():
    for goal in datalog.GOALS:
        g = datalog.guide(goal)
        assert g['before_you_drive'] and g['on_the_road']['steps'] and g['after_the_drive']
        assert g['after_the_drive'][-1].endswith(f'--goal {goal}')
    assert '3 runs' in ' '.join(datalog.guide('power')['on_the_road']['steps'])
    with pytest.raises(ValueError):
        datalog.guide('drag-race')


def test_good_power_log_is_ready(tmp_path):
    result = datalog.check(write_csv(tmp_path / 'good.csv', drive()), 'power')
    assert result['ready'] and not result['fixes'], result


def test_idle_only_and_cold_logs_say_what_to_redo(tmp_path):
    idle = datalog.check(write_csv(tmp_path / 'idle.csv', drive(pulls=0)), 'power')
    assert not idle['ready'] and any('3 full-throttle runs' in f for f in idle['fixes'])
    cold = datalog.check(write_csv(tmp_path / 'cold.csv', drive(ect_f=120)), 'power')
    assert not cold['ready'] and any('warm the engine' in f for f in cold['fixes'])


def test_optional_items_warn_without_blocking(tmp_path):
    mixed = datalog.check(write_csv(tmp_path / 'mixed.csv', drive(gears=(2, 3, 2), iat_f=(80, 100, 120))), 'power')
    assert mixed['ready']
    failed = {c['check'] for c in mixed['checks'] if not c['ok']}
    assert {'same gear', 'similar intake temperature'} <= failed and 'optional' in mixed['summary']


def test_missing_knock_data_is_flagged(tmp_path):
    path = tmp_path / 'noknock.csv'
    write_csv(path, drive())
    path.write_text(path.read_text(encoding='utf-8').replace(',KNK.C,', ',OTHER,', 1), encoding='utf-8')
    result = datalog.check(logs.load(path), 'power')
    knock = [c for c in result['checks'] if c['check'] == 'knock data'][0]
    assert result['ready'] and not knock['ok'] and 'KTuner' in knock['fix']


def test_cruise_and_baseline(tmp_path):
    long_drive = write_csv(tmp_path / 'cruise.csv', drive(pulls=3, cruise_s=120))
    assert datalog.check(long_drive, 'cruise')['ready']
    short = write_csv(tmp_path / 'short.csv', drive(pulls=0))
    base = datalog.check(short, 'baseline')
    assert not base['ready'] and any('5 minutes' in f for f in base['fixes'])


def test_cli(tmp_path, capsys):
    write_csv(tmp_path / 'good.csv', drive())
    assert cli.main(['guide', 'cruise']) == 0
    assert '"goal": "cruise"' in capsys.readouterr().out
    assert cli.main(['check-log', str(tmp_path / 'good.csv'), '--goal', 'power']) == 0
    assert '"ready": true' in capsys.readouterr().out
