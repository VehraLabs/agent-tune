# Demo

`docs/demo.gif` shows a short session: how to record a datalog (`guide`), checking it
(`check-log`), analyzing it, looking up the tune, and writing a small reviewed change to a new
`.kcl` file. Each step runs the real `agent-tune` command and
the lines on screen come from its output.

* `make_data.py` generates the example KTuner CSV datalogs used in the demo.
* `record_demo.py` runs the session and renders `docs/demo.gif` (and an MP4 next to it when
  `imageio-ffmpeg` is installed).

You need a supported `.kcl` for the tune steps; it is copied to a temporary folder and never
stored in the repository.

```bash
uv run --with pillow --with imageio --with imageio-ffmpeg --with numpy python demo/record_demo.py --kcl path/to/stock.kcl
```

Fonts default to Consolas on Windows; set `DEMO_FONT` and `DEMO_FONT_BOLD` to other monospace
TTF files elsewhere.
