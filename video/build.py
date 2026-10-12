"""Build the 1-minute demo video: real captured terminal output + neural narration + burned-in subtitles."""
import asyncio
import json
import re
import subprocess
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
W, H, FPS = 1920, 1080, 10
VOICE = "en-US-AndrewNeural"
MONO = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 22)
MONO_B = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 24)
SANS_B = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 76)
SANS = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 36)
SANS_S = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 28)
BG, FG, DIM = (13, 17, 23), (220, 225, 232), (120, 130, 145)
GREEN, RED, CYAN, YELLOW = (63, 185, 80), (248, 81, 73), (88, 166, 255), (210, 168, 60)

SCENES = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))


def clean(path, keep=None):
    lines = []
    for ln in (HERE / path).read_text(encoding="utf-8", errors="replace").splitlines():
        ln = re.sub(r"\x1b\[[0-9;]*m", "", ln).rstrip()
        if not ln.strip() or "warn" in ln.lower() and "AGENT_MONGODB_URI" in ln:
            continue
        if lines and not ln.startswith((" ", "-", "gen ", "harness", "referee")):
            lines[-1] = lines[-1] + " " + ln.strip()   # re-join terminal soft wraps
            continue
        lines.append(ln)
    if keep:
        lines = [ln for ln in lines if re.search(keep, ln)]
    return [ln[:150] for ln in lines]


def color_for(ln):
    u = ln.upper()
    if "BLOCKED" in u or "ACCEPTED" in u or "RETIRED" in u or "PROMOTED" in u:
        return GREEN
    if "REJECTED" in u or "REGRESS" in u:
        return RED
    if "ATTACK" in u:
        return YELLOW
    if ln.lstrip().startswith(("gen ", "harness v", "referee")):
        return CYAN
    return FG


def terminal_frame(title, lines, shown):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 64], fill=(22, 27, 34))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([24 + i * 30, 22, 44 + i * 30, 42], fill=c)
    d.text((130, 16), title, font=MONO_B, fill=DIM)
    visible = lines[:shown]
    max_rows = 30
    visible = visible[-max_rows:]
    y = 90
    for ln in visible:
        d.text((40, y), ln, font=MONO, fill=color_for(ln))
        y += 29
    return im


def card_frame(head, sub, foot=""):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((140, 330), head, font=SANS_B, fill=FG)
    y = 450
    for s in sub.split("\n"):
        d.text((144, y), s, font=SANS, fill=CYAN if y == 450 else FG)
        y += 56
    if foot:
        d.text((144, 660), foot, font=SANS_S, fill=DIM)
    return im


async def tts(text, out):
    await edge_tts.Communicate(text, VOICE, rate="+18%").save(str(out))


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main():
    work = HERE / "build"
    work.mkdir(exist_ok=True)
    srt, t0, parts = [], 0.0, []
    for i, sc in enumerate(SCENES):
        audio = work / f"a{i}.mp3"
        asyncio.run(tts(sc["say"], audio))
        dur = duration(audio) + 0.4
        frames_dir = work / f"f{i}"
        frames_dir.mkdir(exist_ok=True)
        for f in frames_dir.glob("*.png"):
            f.unlink()
        n = int(dur * FPS)
        if sc["kind"] == "card":
            im = card_frame(sc["head"], sc["sub"], sc.get("foot", ""))
            for k in range(n):
                im.save(frames_dir / f"{k:05}.png") if k == 0 else None
            # single still image looped
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(frames_dir / "00000.png"),
                            "-i", str(audio), "-t", f"{dur:.2f}", "-r", str(FPS), "-c:v", "libx264", "-pix_fmt",
                            "yuv420p", "-c:a", "aac", "-af", "apad", str(work / f"p{i}.mp4")], check=True)
        else:
            lines = clean(sc["file"], sc.get("keep"))
            for k in range(n):
                shown = min(len(lines), int(len(lines) * (k + 1) / (n * 0.8)) + 1)
                terminal_frame(sc["title"], lines, shown).save(frames_dir / f"{k:05}.png")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
                            str(frames_dir / "%05d.png"), "-i", str(audio), "-t", f"{dur:.2f}", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-af", "apad", str(work / f"p{i}.mp4")], check=True)
        # subtitles: split narration into sentences, time proportional to length
        sents = [s.strip() for s in re.split(r"(?<=[.!?:])\s+", sc["say"]) if s.strip()]
        total = sum(len(s) for s in sents)
        t = t0
        for s in sents:
            dt = (dur - 0.4) * len(s) / total
            srt.append((t, t + dt, s))
            t += dt
        t0 += dur
        parts.append(work / f"p{i}.mp4")
        print(f"scene {i}: {dur:.1f}s")
    (work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
    (work / "subs.srt").write_text("".join(f"{k + 1}\n{srt_time(a)} --> {srt_time(b)}\n{s}\n\n"
                                           for k, (a, b, s) in enumerate(srt)), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-c", "copy", "joined.mp4"], cwd=work, check=True)
    style = "FontName=Segoe UI,FontSize=15,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,BorderStyle=4,Outline=0,MarginV=28"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "joined.mp4", "-vf",
                    f"subtitles=subs.srt:force_style='{style}'", "-c:a", "copy", "../custos_demo.mp4"],
                   cwd=work, check=True)
    print(f"total {t0:.1f}s -> video/custos_demo.mp4")


if __name__ == "__main__":
    main()
