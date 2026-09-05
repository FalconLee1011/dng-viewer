# DRViewer · DNG / RAW Viewer
![GenAI Context](https://img.shields.io/badge/GenAI-Context-purple?style=for-the-badge&logo=data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyBpZD0iTGF5ZXJfMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB2ZXJzaW9uPSIxLjEiIHZpZXdCb3g9IjAgMCA1MDAgNTAwIj4KICA8IS0tIEdlbmVyYXRvcjogQWRvYmUgSWxsdXN0cmF0b3IgMzAuNy4wLCBTVkcgRXhwb3J0IFBsdWctSW4gLiBTVkcgVmVyc2lvbjogMi4xLjQgQnVpbGQgMTE0KSAgLS0+CiAgPGRlZnM+CiAgICA8c3R5bGU+CiAgICAgIC5zdDAsIC5zdDEgewogICAgICAgIGZpbGw6ICMyMzFmMjA7CiAgICAgIH0KCiAgICAgIC5zdDIsIC5zdDEgewogICAgICAgIGlzb2xhdGlvbjogaXNvbGF0ZTsKICAgICAgfQoKICAgICAgLnN0MSB7CiAgICAgICAgZm9udC1mYW1pbHk6IE1vbmFjbywgTW9uYWNvOwogICAgICAgIGZvbnQtc2l6ZTogMjk2LjhweDsKICAgICAgfQoKICAgICAgLnN0MyB7CiAgICAgICAgZmlsbDogbm9uZTsKICAgICAgICBzdHJva2U6ICMwMDA7CiAgICAgICAgc3Ryb2tlLW1pdGVybGltaXQ6IDEwOwogICAgICAgIHN0cm9rZS13aWR0aDogNXB4OwogICAgICB9CiAgICA8L3N0eWxlPgogIDwvZGVmcz4KICA8ZyBjbGFzcz0ic3QyIj4KICAgIDx0ZXh0IGNsYXNzPSJzdDEiIHRyYW5zZm9ybT0idHJhbnNsYXRlKDIyLjggMzQyLjYpIj48dHNwYW4geD0iMCIgeT0iMCI+Jmd0OzwvdHNwYW4+PC90ZXh0PgogIDwvZz4KICA8Y2lyY2xlIGNsYXNzPSJzdDAiIGN4PSIyNDAiIGN5PSIxNjcuNSIgcj0iMjEuMiIvPgogIDxjaXJjbGUgY2xhc3M9InN0MCIgY3g9IjM0OC4xIiBjeT0iMTY3LjUiIHI9IjIxLjIiLz4KICA8Y2lyY2xlIGNsYXNzPSJzdDAiIGN4PSI0NTYuMSIgY3k9IjE2Ny41IiByPSIyMS4yIi8+CiAgPGNpcmNsZSBjbGFzcz0ic3QwIiBjeD0iMjQwIiBjeT0iMjc0LjUiIHI9IjIxLjIiLz4KICA8Y2lyY2xlIGNsYXNzPSJzdDAiIGN4PSIzNDguMSIgY3k9IjI3NC41IiByPSIyMS4yIi8+CiAgPGNpcmNsZSBjbGFzcz0ic3QwIiBjeD0iNDU2LjEiIGN5PSIyNzQuNSIgcj0iMjEuMiIvPgogIDxjaXJjbGUgY2xhc3M9InN0MCIgY3g9IjI0MCIgY3k9IjM4MS42IiByPSIyMS4yIi8+CiAgPGNpcmNsZSBjbGFzcz0ic3QwIiBjeD0iMzQ4LjEiIGN5PSIzODEuNiIgcj0iMjEuMiIvPgogIDxjaXJjbGUgY2xhc3M9InN0MCIgY3g9IjQ1Ni4xIiBjeT0iMzgxLjYiIHI9IjIxLjIiLz4KICA8bGluZSBjbGFzcz0ic3QzIiB4MT0iMjQwIiB5MT0iMTY3LjUiIHgyPSIzNDguMSIgeTI9IjE2Ny41Ii8+CiAgPGxpbmUgY2xhc3M9InN0MyIgeDE9IjM0OC4xIiB5MT0iMTY3LjUiIHgyPSI0NTYuMSIgeTI9IjE2Ny41Ii8+CiAgPGxpbmUgY2xhc3M9InN0MyIgeDE9IjI0NS4yIiB5MT0iMzc2LjQiIHgyPSI0NTEuOCIgeTI9IjE2OS44Ii8+CiAgPGxpbmUgY2xhc3M9InN0MyIgeDE9IjIzNy43IiB5MT0iMzgxLjYiIHgyPSIzNDUuNyIgeTI9IjM4MS42Ii8+CiAgPGxpbmUgY2xhc3M9InN0MyIgeDE9IjM1OSIgeTE9IjM3NC41IiB4Mj0iNDUwIiB5Mj0iMjgzLjYiLz4KPC9zdmc+)

A local Python desktop photo browser with a dark Lightroom-inspired grid.

## Run with Pipenv

```sh
pipenv sync
pipenv run start
```

To open a folder directly: `pipenv run python main.py /path/to/photos`.
Python 3.11 is required. The decoder is pinned to rawpy 0.25.1 for Intel macOS compatibility. For dependency changes, use `pipenv install` to update the lockfile.

## Build a Linux executable

Run the build on Linux using Python 3.11 and Pipenv, from the project directory. A Linux machine, VM, container, or CI runner can build it; PyInstaller does not cross-compile a Linux executable from macOS. See the [PyInstaller documentation](https://pyinstaller.org/en/stable/).

```sh
pipenv sync --dev
pipenv install --dev pyinstaller

pipenv run pyinstaller \
  --name DRViewer \
  --onedir \
  --collect-all rawpy \
  --clean \
  main.py
```

Launch the application from a Linux desktop session:

```sh
./dist/DRViewer/DRViewer
```

Distribute the entire `dist/DRViewer` folder, including its bundled dependencies. To produce a single executable instead, replace `--onedir` with `--onefile`; the output will be `dist/DRViewer`.

Build for the intended CPU architecture and on the oldest Linux distribution you want to support, with compatible Python and dependency versions. PyInstaller does not bundle every system library, so builds made on newer distributions may not run on older ones. Test the packaged app on your target desktop distribution. See [Linux compatibility guidance](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible).

## Controls

- Open a folder (including subfolders), or drag folders/files into the window. Each import replaces the current collection.
- DNG files appear in the DNG tab; other supported camera formats appear in RAW.
- Move the size slider from 10 small columns to 1 large column. The default is 4.
- Click a photo to open it. Scroll to zoom, drag to pan, double-click to fit.
- When the imported collection has a matching DNG / RAW pair (same folder and filename stem), use **Switch to RAW** / **Switch to DNG** beside the photo title. The button appears when there is exactly one matching alternative; switching also selects that format's browsing tab.
- Use the top-left × or Escape to close; the top-right ⓘ shows details.
- Left/right arrows browse the current tab; I toggles details; Ctrl/Cmd+O opens a folder.
- Details include filename, original image resolution, DPI, file size, camera device, date taken, lens, aperture, shutter speed, ISO, focal length (and 35mm equivalent), exposure compensation/program, metering mode, flash, white balance, color space, bits per sample, and color encoding. Scroll the details panel to see all fields. Missing fields show `N/A`.
- Color details reflect embedded metadata, not the viewer's RGB conversion. RAW color space may be uncalibrated or absent; bits per sample describe the tagged image, which may be an embedded preview in some camera formats.

Previews load in background workers with a bounded in-memory thumbnail cache. Originals are never modified, uploaded, or copied. Full photo display is limited to 6,000 pixels on its longest edge to control memory usage. Embedded previews may differ in color from the developed photo. RAW support depends on LibRaw (via rawpy); unsupported or damaged files show an error. DPI and date taken are read from embedded metadata, not inferred from screen resolution or filesystem timestamps.

## Verify

The viewer keeps the 20 most recently viewed photo pairs in memory, including their developed images and details. DNG and RAW versions with the same folder and filename stem share one slot, so 20 pairs can retain 40 developed images. Each version is developed when first opened; reopening it skips development. Viewing either version refreshes the pair's recency. The least recently viewed pair is evicted together when the cache fills; importing a new collection clears it. A photo with only one format also uses one slot.

Headerless `.RAW` pixel dumps are supported when a matching `.DNG` (same filename stem) is in the same folder. The dump must contain little-endian uint16 pixels in the companion DNG's LibRaw buffer layout, with exactly the same byte size. The viewer renders the RAW pixels using the DNG's dimensions, calibration, and metadata. Keep these files together; arbitrary headerless layouts cannot be identified from a `.RAW` extension alone.

```sh
QT_QPA_PLATFORM=offscreen pipenv run test
```

The tests render both previews and full photos for every supported file in `tests/pictures`, including the supplied DNG / RAW pairs. This integration check is skipped if no pictures are present; synthetic decoding and UI tests still run.
