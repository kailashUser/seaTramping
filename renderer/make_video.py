"""
Turn a recorded voyage into an MP4.

Two inputs are supported:

  webm    the file the page's REC button downloads (real-time canvas capture).
          Fastest route - a 5m45s video records in 5m45s.

  frames  PNGs posted to renderer/frames by a deterministic capture run.
          Slower but exact, and immune to dropped frames on a busy machine.

    python renderer/make_video.py webm  path/to/voyage_run19.webm
    python renderer/make_video.py frames --fps 30

Output lands in renderer/output/.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_DIR = os.path.join(_HERE, "frames")
OUT_DIR = os.path.join(_HERE, "output")


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        sys.exit("ffmpeg not found. Run: pip install imageio-ffmpeg")


def run(cmd):
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    proc = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        # ffmpeg puts everything on stderr; only surface it when it actually failed.
        print(proc.stderr[-4000:], file=sys.stderr)
        sys.exit(f"ffmpeg failed (exit {proc.returncode})")


def from_webm(src, out, crf, fps):
    if not os.path.isfile(src):
        sys.exit(f"not found: {src}")
    run([ffmpeg_exe(), "-y", "-i", src,
         "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         *(["-r", str(fps)] if fps else []),
         out])


def from_frames(out, crf, fps, pattern):
    files = sorted(glob.glob(os.path.join(FRAME_DIR, pattern)))
    if not files:
        sys.exit(f"no frames matching {pattern} in {FRAME_DIR}")
    print(f"{len(files)} frames -> {os.path.basename(out)} at {fps} fps "
          f"({len(files)/fps:.1f}s)")
    run([ffmpeg_exe(), "-y", "-framerate", str(fps),
         "-i", os.path.join(FRAME_DIR, pattern.replace("*", "%06d")),
         "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["webm", "frames"])
    ap.add_argument("source", nargs="?", help="webm file (mode=webm)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=18, help="lower = better quality")
    ap.add_argument("--pattern", default="cap_*.png")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    out = args.out or os.path.join(OUT_DIR, "voyage.mp4")

    if args.mode == "webm":
        if not args.source:
            sys.exit("mode=webm needs the recorded .webm path")
        from_webm(args.source, out, args.crf, args.fps)
    else:
        from_frames(out, args.crf, args.fps, args.pattern)

    size = os.path.getsize(out) / 1e6
    print(f"\nwrote {out}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
