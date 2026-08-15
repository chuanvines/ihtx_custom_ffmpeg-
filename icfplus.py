import os
import random
import re
import subprocess
import sys
import time


def run(cmd, log=None):
    fh = None
    if log:
        fh = open(log, "a", encoding="utf-8", errors="replace")
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=fh if fh else subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        out = ""
        if fh is None:
            out = p.stdout.decode("utf-8", errors="replace")
        return p.returncode, out
    finally:
        if fh:
            fh.close()


def render_args(args, i):
    out = []
    for a in args:
        a = re.sub(r"\$\(\s*\(\s*\$?i\s*\+\s*1\s*\)\s*\)", str(i + 1), a)
        a = re.sub(r"\$i\b", str(i), a)
        out.append(a)
    return out


def ffprobe(infile, args):
    cmd = ["ffprobe", "-v", "error"] + args + ["-of", "default=nokey=1:noprint_wrappers=1", infile]
    rc, out = run(cmd)
    return out.strip() if rc == 0 else ""


def main():
    argv = sys.argv[1:]
    hidelogs = "--hidelogs" in argv
    argv = [a for a in argv if a != "--hidelogs"]
    if len(argv) < 7:
        print(
            "Usage: icf+.exe [--hidelogs] <input> <output> <exports> <dur_frac> <no_trim> "
            "<input_format> <output_format> [ffmpeg args...]\n"
            "Multipitch mode: make the last ffmpeg arg an output filename containing "
            "$i, e.g. ... mov mp4 -qp 1 -c:a pcm_s16le a$i.mp4",
            file=sys.stderr,
        )
        sys.exit(2)

    start = time.time()

    input_file = argv[0]
    output_file = argv[1]
    exports = int(argv[2])
    dur = argv[3]
    no_trim = argv[4]
    input_format = argv[5]
    output_format = argv[6]
    ffmpeg_args = argv[7:]

    abs_exports = abs(exports)

    if not os.path.isfile(input_file):
        print("input file not found: %s" % input_file, file=sys.stderr)
        sys.exit(1)

    if abs_exports < 1:
        print("exports must be non-zero", file=sys.stderr)
        sys.exit(1)

    if input_format == "default":
        input_format = os.path.splitext(os.path.basename(input_file))[1].lstrip(".")
    if output_format == "default":
        output_format = os.path.splitext(os.path.basename(input_file))[1].lstrip(".")

    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    log = "err_%d.log" % random.randint(0, 2**31 - 1)

    def fail():
        if not hidelogs and os.path.isfile(log):
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                sys.stderr.write(f.read())
        cleanup()
        sys.exit(1)

    def run_ffmpeg(cmd):
        rc, _ = run(cmd, log=log)
        if rc != 0:
            print("ffmpeg command failed: %s" % " ".join(cmd), file=sys.stderr)
            fail()
        return rc

    def cleanup():
        for pat in ("concat.txt", "0.mov", "0.mp4"):
            if os.path.isfile(pat):
                try:
                    os.remove(pat)
                except OSError:
                    pass
        for f in os.listdir("."):
            if f.endswith("." + input_format) and f not in (input_file, output_file):
                try:
                    os.remove(f)
                except OSError:
                    pass
            if multipitch and re.match(r"^(a\d+\.mp4|h\d+\.wav|out\d+\.wav|.*\.pitch\.mp4|pitch_multi_shifter)$", f):
                try:
                    os.remove(f)
                except OSError:
                    pass
        if os.path.isfile(log):
            try:
                os.remove(log)
            except OSError:
                pass

    def ensure_program():
        if os.path.isfile("program"):
            return
        rc, _ = run(["curl", "-sSL", "https://file.garden/aTXso15ukD3mnuPI/multipitch", "-o", "pitch_multi_shifter"])
        if rc != 0 or not os.path.isfile("pitch_multi_shifter"):
            print("failed to download multipitch program", file=sys.stderr)
            fail()
        os.replace("pitch_multi_shifter", "program")
        try:
            os.chmod("program", 0o755)
        except OSError:
            pass

    def pitch_export(i, base):
        run_ffmpeg(["ffmpeg", "-loglevel", "error", "-hide_banner", "-y",
                    "-i", base, "-af", "asetrate=%s/1" % sr, "h%d.wav" % i])
        rc, _ = run([os.path.join(".", "program"), "h%d.wav" % i, "out%d.wav" % i,
                     "7", "-12", "--no-normalize"], log=log)
        if rc != 0:
            print("multipitch program failed on export %d" % i, file=sys.stderr)
            fail()
        tmp = "%s.pitch.mp4" % base
        run_ffmpeg(["ffmpeg", "-loglevel", "error", "-hide_banner", "-y",
                    "-i", base, "-i", "out%d.wav" % i,
                    "-af", "asetrate=%s,bass=f=200:g=1.2:transform=5" % sr,
                    "-map", "0:v", "-map", "1:a",
                    "-preset", "ultrafast", "-qp", "1", "-c:a", "pcm_s16le", tmp])
        os.replace(tmp, base)

    # Build lossless intermediate 0.mov (always trimmed to dur, infinite loop)
    cmd0 = [
        "ffmpeg", "-loglevel", "error", "-hide_banner", "-y",
        "-stream_loop", "-1", "-i", input_file,
        "-c:v", "utvideo", "-c:a", "alac", "-t", dur,
        "-threads", "0", "-movflags", "+faststart", "0.mov",
    ]
    run_ffmpeg(cmd0)
    if not os.path.isfile("0.mov"):
        print("0.mov was not created even though ffmpeg exited 0 (utvideo supported?)", file=sys.stderr)
        fail()

    truthy = no_trim in ("true", "yes", "+")
    falsy = no_trim in ("false", "no", "-")

    multipitch = bool(ffmpeg_args) and "$i" in ffmpeg_args[-1]
    render_ffmpeg_args = ffmpeg_args[:-1] if multipitch else ffmpeg_args

    def out_name(i):
        if multipitch:
            return render_args([ffmpeg_args[-1]], i)[0]
        return "%d.%s" % (i, input_format)

    def render_cmd(src, dst, i):
        cmd = ["ffmpeg", "-loglevel", "error", "-hide_banner", "-y"]
        if not truthy:
            cmd += ["-stream_loop", "1"]
        cmd += ["-i", src] + render_args(render_ffmpeg_args, i)
        if not truthy:
            cmd += ["-t", dur]
        cmd += ["-movflags", "+faststart", dst]
        return cmd

    if not (truthy or falsy):
        print("invalid no_trim value: %s (expected true/yes/+ or false/no/-)" % no_trim, file=sys.stderr)
        fail()

    if multipitch:
        ensure_program()
        sr = ffprobe("0.mov", ["-select_streams", "a:0", "-show_entries", "stream=sample_rate"])

    if multipitch:
        run_ffmpeg(render_cmd("0.mov", out_name(0), 0))
        for i in range(1, abs_exports + 1):
            run_ffmpeg(render_cmd(out_name(i - 1), out_name(i), i))
            pitch_export(i, out_name(i))
    else:
        run_ffmpeg(render_cmd("0.mov", out_name(1), 0))
        for i in range(1, abs_exports + 1):
            run_ffmpeg(render_cmd(out_name(i), out_name(i + 1), i))

    # Build concat list
    if exports < 0:
        seq = range(abs_exports, 0, -1)
    else:
        seq = range(1, abs_exports + 1)
    with open("concat.txt", "w", encoding="utf-8") as f:
        for n in seq:
            f.write("file '%s'\n" % out_name(n))

    codec_args = {
        "mkv": ["-c:v", "mpeg2video", "-q:v", "1", "-c:a", "flac", "-pix_fmt", "yuv420p", "-bufsize", "16M", "-movflags", "+faststart", "-threads", "0"],
        "mxf": ["-c:v", "mpeg2video", "-qscale", "1", "-qmin", "1", "-c:a", "pcm_s16le", "-ar", "48000", "-pix_fmt", "yuv420p", "-bufsize", "16M", "-movflags", "+faststart", "-threads", "0"],
        "mov": ["-c:v", "libx264", "-profile:v", "high", "-level:v", "5", "-tune", "film", "-q:v", "1", "-crf", "30", "-g", "9", "-bf", "0", "-preset", "superfast", "-c:a", "aac", "-b:a", "224K", "-aac_coder", "fast", "-pix_fmt", "yuv420p", "-bufsize", "16M", "-movflags", "+faststart", "-threads", "0"],
        "mp4": ["-c:v", "libx264", "-profile:v", "high", "-level:v", "5", "-tune", "film", "-q:v", "1", "-crf", "30", "-g", "9", "-bf", "0", "-preset", "superfast", "-c:a", "aac", "-b:a", "224K", "-aac_coder", "fast", "-pix_fmt", "yuv420p", "-bufsize", "16M", "-movflags", "+faststart", "-threads", "0"],
        "avi": ["-c:v", "mpeg2video", "-c:a", "flac", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        "webm": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    }
    extra = codec_args.get(
        output_format,
        ["-pix_fmt", "yuv420p", "-bufsize", "16M", "-movflags", "+faststart", "-threads", "0"],
    )

    run_ffmpeg(
        ["ffmpeg", "-loglevel", "error", "-hide_banner", "-y",
         "-f", "concat", "-safe", "0", "-i", "concat.txt"]
        + extra
        + [output_file]
    )
    if not os.path.isfile(output_file):
        print("output was not created", file=sys.stderr)
        fail()

    file_size = os.path.getsize(output_file)

    if file_size >= 1048576:
        fs = "%.2f MB" % (file_size / 1048576)
    else:
        fs = "%.2f KB" % (file_size / 1024)

    elapsed = time.time() - start

    print("Done: %s (%s, took %.3f seconds)" % (output_file, fs, elapsed))

    cleanup()


if __name__ == "__main__":
    main()
