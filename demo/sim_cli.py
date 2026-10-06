"""Run the real agent-tune CLI against a simulated KTuner dongle (demo only).

The dongle is replaced by a fake serial port that answers each B0 poll with the
next synthetic reply from frames.bin. Everything else is the normal code path.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_tune import cli, telemetry  # noqa: E402


class SimulatedDongle:
    def __init__(self, data):
        self.frames = [data[i:i + 534] for i in range(0, len(data), 534)]
        self.pending = b''
        self.index = 0

    def write(self, data):
        if data == b'\xb0' and self.frames:
            self.pending += self.frames[self.index % len(self.frames)]
            self.index += 1
        return len(data)

    def read(self, n):
        chunk, self.pending = self.pending[:n], self.pending[n:]
        return chunk

    def close(self):
        pass


def main():
    frames = Path(sys.argv[1]).read_bytes()
    telemetry.find_ports = lambda ports=None: [{'port': 'COM4', 'description': 'KTuner (simulated)'}]
    telemetry.open_port = lambda name: SimulatedDongle(frames)
    return cli.main(sys.argv[2:])


if __name__ == '__main__':
    sys.exit(main())
