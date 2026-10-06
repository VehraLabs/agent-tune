# Demo

`docs/demo.gif` shows a full session: find the dongle, log live data, analyze a KTuner CSV with
three full-throttle pulls, look up the tune, write a small reviewed change, and compare before
and after.

The data is synthetic and the dongle is simulated; every command shown is the real `agent-tune`
command and its real output (long JSON is trimmed).

* `make_data.py` writes the synthetic KTuner CSV logs (`before.csv`, `after.csv`) and the replies
  of a simulated dongle (`frames.bin`).
* `sim_cli.py` runs the normal `agent-tune` CLI with the dongle replaced by a fake serial port.
* `record_demo.py` runs the scripted session and renders `docs/demo.gif` (and an MP4 next to it
  when `imageio-ffmpeg` is installed).

You need a supported `.kcl` for the tune steps; it is copied to a temporary folder and never
stored in the repository.

```bash
uv run --with pillow --with imageio --with imageio-ffmpeg --with numpy python demo/record_demo.py --kcl path/to/stock.kcl
```

Fonts default to Consolas on Windows; set `DEMO_FONT` and `DEMO_FONT_BOLD` to other monospace
TTF files elsewhere.
