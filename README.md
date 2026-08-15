# IHTX Custom FFmpeg+ (icf+)

Multi-export video loop renderer built on FFmpeg. Takes one input clip and produces
an output made of `exports` concatenated renders, each passing through your FFmpeg
filter chain. Uses a lossless intermediate (`0.mov`) so re-encodes stay clean.

Works on Windows (`icf+.exe`) and Linux (`icf+.sh`). Both share the same CLI and output
a simple `Done: <output> (<size>, took X seconds)` line when finished.

## Requirements

- FFmpeg + FFprobe in PATH (both scripts call `ffmpeg`/`ffprobe`)
- Linux: `curl` (only needed for Multipitch mode downloads)

## Usage

```
icf+.exe <input> <output> <exports> <dur_frac> <no_trim> <input_format> <output_format> [ffmpeg args...]
```

### Arguments

| Arg | Meaning |
|-----|---------|
| `input` | Source video file |
| `output` | Output file path (parent dir is created if missing) |
| `exports` | Number of renders to concatenate. Negative reverses the concat order |
| `dur_frac` | Loop length in seconds for the lossless intermediate and `-t` trimming |
| `no_trim` | `true` / `yes` / `+` = no trimming, `false` / `no` / `-` = trim to `dur_frac` |
| `input_format` | Intermediate file extension (or `default` to use the input's extension) |
| `output_format` | Container of the final file (mp4 / mov / mkv / mxf / avi / webm / other) |
| `ffmpeg args...` | Any FFmpeg options: filters, codecs, etc. |

### Options

- `--hidelogs` — put it anywhere in the command line. On failure, suppresses the
  FFmpeg error-log dump (keeps only the one-line error message).

### Per-export numbering

Inside `ffmpeg args`, use `$i` (or `$(($i+1))`) and it is substituted with the current
export index on every render:

```bash
# Windows
.\icf+.exe input.mp4 output.mp4 10 0.4 - mov mp4 -vf 'setpts=0.5*PTS,drawtext=fontfile=arial.ttf:text=$(($i+1)):x=(w-text_w)/2:y=60:fontsize=w/12:fontcolor=white:bordercolor=black:borderw=6' -c:v ffv1 -c:a pcm_s16le
```

Note: quote the `-vf` value with single quotes so your shell doesn't expand `$i` itself.

## Examples

Basic 10-export loop, half-speed video, double-speed audio:

```bash
.\icf+.exe input.mp4 output.mp4 10 0.4 - mov mp4 -vf "setpts=0.5*PTS" -af atempo=2 -c:v ffv1 -c:a pcm_s16le
```

Reverse order (exports negative):

```bash
.\icf+.exe input.mp4 output.mp4 -5 0.4 - mov mp4 -vf "setpts=0.5*PTS" -c:v ffv1 -c:a pcm_s16le
```

## Multipitch mode

If the **last** FFmpeg arg is an output filename containing `$i`, Multipitch mode
activates: each export gets its audio pitch-shifted (`asetrate`, bass boost, custom
pitch shifter binary downloaded once from `https://file.garden/aTXso15ukD3mnuPI/multipitch`).

```bash
.\icf+.exe input.mp4 output.mp4 15 0.4 - mov mp4 -qp 1 -c:a pcm_s16le a$i.mp4
```

## Install

### Windows

Download `icf+.exe` from the Releases page and run it from any terminal:

```powershell
.\icf+.exe input.mp4 output.mp4 10 0.4 - mov mp4 -vf "setpts=0.5*PTS" -c:v ffv1 -c:a pcm_s16le
```

### Linux

```bash
curl -fsSL https://github.com/chuanvines/ihtx_custom_ffmpeg-/releases/latest/download/icf+.sh -o icf+.sh
chmod +x icf+.sh
./icf+.sh input.mp4 output.mp4 10 0.4 - mov mp4 -vf "setpts=0.5*PTS" -c:v ffv1 -c:a pcm_s16le
```

### Output formats

`mp4`/`mov` encode with libx264 (high profile, superfast), `mkv`/`mxf`/`avi` with
mpeg2video, `webm` copies streams; anything else falls back to stream copy with
`-pix_fmt yuv420p`.

## Building from source

```bash
# Windows exe (from icfplus.py)
pip install pyinstaller
pyinstaller --onefile --name "icf+" icfplus.py

# Linux script needs no build — it is the source.
```

## License

No license specified.
