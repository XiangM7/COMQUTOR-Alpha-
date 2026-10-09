#!/usr/bin/env python3
"""T4 delivery (round 31): add chapters and a soft subtitle track to copies of the existing demo videos.

Reads video/scene_index.json. For every video it writes <name>.srt / <name>.vtt (one cue per scene: label, what is shown, full
run_id, code identity) and <name>_chapters.mp4: the ORIGINAL video stream copied bit for bit (-c copy) plus chapter markers and
a mov_text subtitle track. Nothing is re-encoded, so the pixels (UI results) are exactly the original. The md5 of the video
stream of the original and of the copy is recorded in video/chapters_build.json to prove that.

Needs a local ffmpeg (default /opt/homebrew/bin/ffmpeg, or --ffmpeg). Run from the package root:
    python3 tools/build_video_chapters.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent


def ts(seconds: float, sep: str) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cue_lines(video: dict, scene: dict) -> list[str]:
    kind = scene["run_kind"]
    label = "【模拟·测试注入】" if "模拟" in kind else ("【FRESH 真实运行】" if "Fresh" in kind else ("【冻结/历史】" if scene["run_id"] else "【实例页面】"))
    return [f"{label} {scene['id']}：{scene['zh']}",
            f"run_id {scene['run_id'] or '—'} · 代码 {video['code_identity_shown'].split(' (')[0]}"]


def stream_md5(ffmpeg: str, path: Path) -> str:
    out = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return out.removeprefix("MD5=")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    args = ap.parse_args(argv)
    index = json.loads((PKG / "video" / "scene_index.json").read_text(encoding="utf-8"))
    results = []
    for video in index["videos"]:
        src = PKG / video["file"]
        stem = src.with_suffix("")
        srt, vtt, meta = [], ["WEBVTT", ""], [";FFMETADATA1", f"title=COMQUTOR T4 demo — {video['kind']}"]
        for i, scene in enumerate(video["scenes"], 1):
            a, b = scene["video_start_s"], scene["video_end_s"]
            lines = cue_lines(video, scene)
            srt += [str(i), f"{ts(a, ',')} --> {ts(b, ',')}", *lines, ""]
            vtt += [f"{ts(a, '.')} --> {ts(b, '.')}", *lines, ""]
            meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}",
                     f"title={scene['id']} {scene['run_kind']}"]
        Path(f"{stem}.srt").write_text("\n".join(srt) + "\n", encoding="utf-8")
        Path(f"{stem}.vtt").write_text("\n".join(vtt) + "\n", encoding="utf-8")
        meta_path = Path(f"{stem}.ffmetadata.txt")
        meta_path.write_text("\n".join(meta) + "\n", encoding="utf-8")
        out = Path(f"{stem}_chapters.mp4")
        subprocess.run([args.ffmpeg, "-v", "error", "-y", "-i", str(src), "-i", f"{stem}.srt", "-i", str(meta_path),
                        "-map", "0:v", "-map", "1:s", "-map_metadata", "2", "-map_chapters", "2",
                        "-c:v", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=chi", "-movflags", "+faststart", str(out)],
                       check=True)
        results.append({"video": video["file"], "chaptered_copy": str(out.relative_to(PKG)),
                        "original_video_stream_md5": stream_md5(args.ffmpeg, src),
                        "chaptered_video_stream_md5": stream_md5(args.ffmpeg, out)})
    for r in results:
        r["video_stream_identical"] = r["original_video_stream_md5"] == r["chaptered_video_stream_md5"]
    (PKG / "video" / "chapters_build.json").write_text(json.dumps({"ffmpeg": args.ffmpeg, "results": results}, ensure_ascii=False, indent=1) + "\n",
                                                      encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=1))
    return 0 if all(r["video_stream_identical"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
