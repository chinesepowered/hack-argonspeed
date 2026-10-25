#!/usr/bin/env python3
"""pitch/argon-speed.mp4, the deck narrated: ElevenLabs reads pitch/narration.json slide by slide,
Playwright screenshots pitch/slides.html at 1920x1080, and ffmpeg holds each slide for as long as its
narration runs. Narration is cached by its text in pitch/audio/, so a re-render only pays for the
slides whose words changed.

    scripts/slides.py && scripts/video.py      (ELEVENLABS_API_KEY in .env; ELEVENLABS_VOICE to change voice)
"""

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PITCH = os.path.join(ROOT, "pitch")
MODEL = "eleven_multilingual_v2"
PAD = 1.8  # seconds of quiet after each slide's narration

SHOOT = """
const { chromium } = require('playwright');
(async () => {
  const [html, out, count] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto('file://' + html);
  await page.evaluate(() => document.fonts.ready);
  for (let i = 0; i < Number(count); i++) {
    await page.evaluate(k => show(k), i);
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${out}/slide-${String(i + 1).padStart(2, '0')}.png` });
  }
  await browser.close();
})();
"""


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def narrate(text, voice, path):
    body = {"text": text, "model_id": MODEL, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128", data=json.dumps(body).encode(),
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)


def seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def main():
    load_env()
    voice = os.environ.get("ELEVENLABS_VOICE", "cjVigY5qzO86Huf0OWal")  # Eric: smooth, trustworthy
    slides = json.load(open(os.path.join(PITCH, "narration.json")))
    os.makedirs(os.path.join(PITCH, "audio"), exist_ok=True)
    spoken = 0
    audio = []
    for s in slides:
        key = hashlib.sha1(f"{voice}|{MODEL}|{s['text']}".encode()).hexdigest()[:16]
        path = os.path.join(PITCH, "audio", f"{s['slide']:02d}-{key}.mp3")
        if not os.path.exists(path):
            narrate(s["text"], voice, path)
            spoken += len(s["text"])
        audio.append(path)
    for name in os.listdir(os.path.join(PITCH, "audio")):  # narration of slides as they used to read
        if os.path.join(PITCH, "audio", name) not in audio:
            os.remove(os.path.join(PITCH, "audio", name))

    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "shoot.js")
        with open(script, "w") as f:
            f.write(SHOOT)
        subprocess.run(["node", script, os.path.join(PITCH, "slides.html"), tmp, str(len(slides))], check=True,
                       env={**os.environ, "NODE_PATH": subprocess.run(["npm", "root", "-g"], capture_output=True,
                                                                     text=True).stdout.strip()})
        parts = []
        for n, track in enumerate(audio, 1):
            part = os.path.join(tmp, f"part-{n:02d}.mp4")
            length = seconds(track) + PAD
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "30",
                            "-i", os.path.join(tmp, f"slide-{n:02d}.png"), "-i", track, "-af", f"apad=pad_dur={PAD}",
                            "-t", f"{length:.2f}", "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                            "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", part], check=True)
            parts.append(part)
        listing = os.path.join(tmp, "parts.txt")
        with open(listing, "w") as f:
            f.writelines(f"file '{p}'\n" for p in parts)
        out = os.path.join(PITCH, "argon-speed.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out],
                       check=True)
    print(f"{os.path.relpath(out, ROOT)}: {seconds(out):.0f} s over {len(slides)} slides;"
          f" {spoken:,} characters narrated this time")


if __name__ == "__main__":
    main()
