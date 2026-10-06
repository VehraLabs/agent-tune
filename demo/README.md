# Demo

`docs/demo.mp4` (about 55 seconds) follows a KTuner owner who wants more power. The agent explains
how to drive to record a datalog (`guide`), checks the log (`check-log`), explains the analysis,
proposes one small change, writes it to a new `.kcl` file, and lists the next steps. Each step
runs the real `agent-tune` command and the lines on screen come from its output.

* `make_data.py` generates the example KTuner CSV datalogs used in the demo.
* `record_demo.py` runs the session and renders `docs/demo.mp4`, plus `docs/demo-poster.png`, the
  still frame the README links to the video.

You need a supported `.kcl` for the tune steps; it is copied to a temporary folder and never
stored in the repository.

```bash
uv run --with pillow --with imageio --with imageio-ffmpeg --with numpy python demo/record_demo.py --kcl path/to/stock.kcl
```

Fonts default to Consolas on Windows; set `DEMO_FONT` and `DEMO_FONT_BOLD` to other monospace
TTF files elsewhere.
