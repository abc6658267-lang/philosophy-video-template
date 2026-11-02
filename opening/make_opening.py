#!/usr/bin/env python3
"""哲学系列 · 开场模板
用法: python3 make_opening.py config.json
输出: <out>.mp4（画面 + 咔哒音效）、<out>_timing.json（配音对齐用的时间点）

结构: 引子(大字"今天我们要讲的是") → 概念轮播(每词约0.2秒, 咔哒声, 末尾减速) → 闪黑 → 揭晓主题(打字动画)
每期只需改 config.json 里的 words / reveal.title / reveal.background。
"""
import json, math, os, random, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CFG = json.load(open(sys.argv[1], encoding="utf-8"))
BASE = os.path.dirname(os.path.abspath(sys.argv[1]))
W, H = CFG.get("size", [1920, 1080])
FPS = CFG.get("fps", 30)
SR = 48000
FONT = CFG.get("font", "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc")
FONT_INDEX = CFG.get("font_index", 2)  # Noto CJK ttc: 2 = SC
ST = CFG.get("style", {})
SHADOW = tuple(ST.get("shadow_color", [232, 176, 48]))
SKEW = ST.get("skew", 0.18)
random.seed(7)


def P(p):
    return p if os.path.isabs(p) else os.path.join(BASE, p)


# ---------- 素材读取 ----------
def cover(img, w=W, h=H):
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    img = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


GRADE = CFG.get("grade", {})


def grade(img):
    """统一调色：对比度 + 暗角（让不同来源的照片更统一，标题更突出）"""
    c, v = GRADE.get("contrast", 1.0), GRADE.get("vignette", 0.0)
    if c == 1.0 and v == 0.0:
        return img
    a = np.asarray(img).astype(np.float32) / 255
    a = np.clip((a - 0.5) * c + 0.5, 0, 1)
    if v:
        h, w = a.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / math.sqrt(2)
        a *= (1 - v * np.clip(r, 0, 1) ** 2)[..., None]
    return Image.fromarray((a * 255).astype(np.uint8))


def load_bg(path, oversize=1.12):
    """读图并放大一点，留出推镜余量"""
    return grade(cover(Image.open(P(path)), int(W * oversize), int(H * oversize)))


def zoom_frame(big, z):
    """z: 1.0 = 完整画面范围的 1/oversize；z 越大越近"""
    bw, bh = big.size
    cw, ch = W * (bw / W) / z, H * (bh / H) / z
    cw, ch = min(cw, bw), min(ch, bh)
    x, y = (bw - cw) / 2, (bh - ch) / 2
    return big.resize((W, H), Image.BILINEAR, box=(x, y, x + cw, y + ch))


class VideoBg:
    """揭晓段可用视频当底（正片第一个镜头）"""
    def __init__(self, path):
        self.frames = []
        cmd = ["ffmpeg", "-v", "error", "-i", P(path), "-vf",
               f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        n = len(raw) // (W * H * 3)
        self.arr = np.frombuffer(raw[: n * W * H * 3], np.uint8).reshape(n, H, W, 3)

    def get(self, i):
        return Image.fromarray(self.arr[min(i, len(self.arr) - 1)])


# ---------- 字效 ----------
def text_sprite(text, size):
    """白色粗体 + 斜体 + 深色描边 + 金色硬投影 + 柔和暗光（保证任何底图都能看清）"""
    font = ImageFont.truetype(FONT, size, index=FONT_INDEX)
    l, t, r, b = font.getbbox(text)
    tw, th = r - l, b - t
    pad = int(size * 0.6)
    cw, ch = tw + pad * 2 + int(th * SKEW), th + pad * 2

    def layer(fill, stroke=0, stroke_fill=None, dx=0, dy=0):
        im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((pad - l + dx, pad - t + dy), text, font=font, fill=fill,
                                stroke_width=stroke, stroke_fill=stroke_fill)
        return im

    off = max(3, size // 22)
    glow = layer((0, 0, 0, 200), stroke=size // 10, stroke_fill=(0, 0, 0, 200)).filter(
        ImageFilter.GaussianBlur(size / 7))
    shadow = layer(SHADOW + (255,), stroke=max(2, size // 40), stroke_fill=SHADOW + (255,), dx=off, dy=off)
    main = layer((255, 255, 255, 255), stroke=max(2, size // 45), stroke_fill=(30, 30, 30, 255))
    out = Image.alpha_composite(Image.alpha_composite(glow, shadow), main)
    # 斜体：水平错切
    out = out.transform(out.size, Image.AFFINE, (1, SKEW, -SKEW * ch * 0.5, 0, 1, 0), Image.BICUBIC)
    return out


def paste_center(frame, sprite, cx, cy, scale=1.0, alpha=1.0):
    if scale != 1.0:
        sprite = sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))),
                               Image.BICUBIC)
    if alpha < 1.0:
        a = sprite.getchannel("A").point(lambda v: int(v * alpha))
        sprite = sprite.copy()
        sprite.putalpha(a)
    frame.paste(sprite, (int(cx - sprite.width / 2), int(cy - sprite.height / 2)), sprite)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


# ---------- 时间线 ----------
hook = CFG["hook"]
rou = CFG["roulette"]
rev = CFG["reveal"]
words = rou["words"]
imgs = rou["images"]
n = len(words)
base_d = rou.get("per_word", 0.2)
slow = rou.get("slowdown", [0.26, 0.34])        # 倒数第2、3个词的时长（减速）
last_d = rou.get("last_word", 0.55)             # 最后一个词（含渐暗）
durs = [base_d] * n
for k, d in enumerate(reversed(slow)):
    if n - 2 - k >= 0:
        durs[n - 2 - k] = d
durs[-1] = last_d
dim_d = rou.get("last_dim", 0.25)

# 若提供真实转盘音效：检测咔哒点，换词卡在咔哒上，最后一个词落在最后一声
ext_sfx = rou.get("click_sfx")
sfx_sig, sfx_lead = None, 0.0
if ext_sfx:
    speed = rou.get("sfx_speed", 1.0)
    af = f"atempo={speed}" if speed != 1.0 else "anull"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", P(ext_sfx), "-af", af, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    sfx_sig = np.frombuffer(raw, np.float32).copy()
    env_h = int(SR * 0.01)
    env = np.array([np.abs(sfx_sig[i:i + env_h]).max() for i in range(0, len(sfx_sig) - env_h, env_h)])
    th = env.max() * 0.35
    onsets = [i * env_h / SR for i in range(1, len(env)) if env[i] > th and env[i - 1] <= th]
    if env[0] > th:
        onsets.insert(0, 0.0)
    if len(onsets) >= n:
        idx = np.round(np.linspace(0, len(onsets) - 1, n)).astype(int)
        sfx_lead = onsets[0]
        rel = [onsets[j] - sfx_lead for j in idx]
        durs = [rel[i + 1] - rel[i] for i in range(n - 1)] + [last_d]
black_d = CFG.get("black", 0.5)

t_hook = hook.get("duration", 1.6)
t_rou0 = t_hook
starts = [t_rou0 + sum(durs[:i]) for i in range(n)]
t_black = t_rou0 + sum(durs)
t_rev = t_black + black_d
rev_d = rev.get("duration", 3.0)
T = t_rev + rev_d
NF = int(round(T * FPS))

# ---------- 预渲染 ----------
_hook_src = hook["image"]
hook_is_video = _hook_src.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
hook_vid = VideoBg(_hook_src) if hook_is_video else None
hook_big = None if hook_is_video else load_bg(_hook_src, 1.06)
hook_txt = text_sprite(hook["text"], hook.get("size", 120))
bg_bigs = [load_bg(imgs[i % len(imgs)]) for i in range(n)]
word_txt = [text_sprite(w, rou.get("size", 160)) for w in words]
rev_size = rev.get("size", 170)
title = rev["title"]
char_sprites = [text_sprite(c, rev_size) for c in title]
rev_bg_path = rev["background"]
rev_is_video = rev_bg_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
rev_bg = VideoBg(rev_bg_path) if rev_is_video else load_bg(rev_bg_path, 1.06)

# 揭晓标题逐字排版（按字宽计算位置）
font = ImageFont.truetype(FONT, rev_size, index=FONT_INDEX)
adv = [font.getlength(c) for c in title]
gap = rev_size * rev.get("letter_spacing", 0.04)
total_w = sum(adv) + gap * (len(title) - 1)
rev_cx, rev_cy = W * rev.get("x", 0.5), H * rev.get("y", 0.42)
char_x = []
x = rev_cx - total_w / 2
for a in adv:
    char_x.append(x + a / 2)
    x += a + gap
type_step = rev.get("type_step", 0.12)
text_out = rev.get("text_fade_out", 0.4)

hook_cx, hook_cy = W * hook.get("x", 0.5), H * hook.get("y", 0.36)
rou_cy = H * rou.get("y", 0.5)


def render(i):
    t = i / FPS
    if t < t_hook:  # 引子
        u = t / t_hook
        z = 1.0 + 0.04 * u
        fr = hook_vid.get(int(t * FPS)).copy() if hook_is_video else zoom_frame(hook_big, z)
        if HOOK_ANIM is not None:
            fr = HOOK_ANIM.apply(fr, t, z)
        p = ease_out(t / 0.18)
        paste_center(fr, hook_txt, hook_cx, hook_cy, scale=1.15 - 0.15 * p, alpha=p)
        return fr
    if t < t_black:  # 轮播
        k = max(j for j in range(n) if starts[j] <= t + 1e-9)
        lt = t - starts[k]
        u = lt / durs[k]
        fr = zoom_frame(bg_bigs[k], 1.08 - 0.06 * ease_out(u))
        p = ease_out(lt / 0.08)
        sx = sy = 0
        if lt < 0.07:
            sx, sy = random.uniform(-6, 6), random.uniform(-6, 6)
        paste_center(fr, word_txt[k], W / 2 + sx, rou_cy + sy, scale=1.28 - 0.28 * p)
        if k == n - 1 and lt > durs[k] - dim_d:  # 最后一个词渐暗
            a = (lt - (durs[k] - dim_d)) / dim_d
            fr = Image.blend(fr, Image.new("RGB", (W, H)), min(1.0, a))
        return fr
    if t < t_rev:  # 闪黑
        return Image.new("RGB", (W, H))
    # 揭晓
    lt = t - t_rev
    if rev_is_video:
        fr = rev_bg.get(int(lt * FPS)).copy()
    else:
        fr = zoom_frame(rev_bg, 1.0 + 0.03 * lt / rev_d)
    fade = 1.0
    if lt > rev_d - text_out:
        fade = max(0.0, 1 - (lt - (rev_d - text_out)) / text_out)
    t0 = rev.get("type_delay", 0.15)
    for j, sp in enumerate(char_sprites):
        ct = lt - t0 - j * type_step
        if ct < 0:
            continue
        p = ease_out(ct / 0.1)
        paste_center(fr, sp, char_x[j], rev_cy, scale=1.2 - 0.2 * p, alpha=p * fade)
    return fr


# ---------- 引子动画：神经网络 ----------
from PIL import ImageChops

class NeuralAnim:
    """思绪从一个点（人物头顶）升起，长成一张发光的神经网络，信号沿连线流动。
    config: hook.anim = {"type": "neural", "origin": [x, y], "spread": 0.55, "nodes": 30,
                         "color": [255, 232, 180], "grow": 1.3, "seed": 11}
    origin 用画面比例坐标（0~1），一般放在引子图里人物的头顶。"""
    def __init__(self, cfg, dur):
        rnd = random.Random(cfg.get("seed", 11))
        self.col = tuple(cfg.get("color", [255, 232, 180]))
        self.dur = dur
        self.grow = min(cfg.get("grow", 1.3), dur * 0.8)
        ox, oy = cfg.get("origin", [0.5, 0.7])
        self.O = (ox * W, oy * H)
        R = cfg.get("spread", 0.55) * H
        self.R = R
        n = cfg.get("nodes", 30)
        a0, a1 = cfg.get("angles", [-175, -5])
        pts = []
        while len(pts) < n:
            ang = math.radians(rnd.uniform(a0, a1))
            r = R * (0.12 + 0.88 * rnd.random() ** 0.8)
            x, y = self.O[0] + r * math.cos(ang) * 1.25, self.O[1] + r * math.sin(ang)
            if 30 < x < W - 30 and 30 < y < H - 30:
                pts.append((x, y))
        pts.sort(key=lambda p: math.dist(p, self.O))
        self.nodes = [self.O] + pts
        self.edges = []          # (a, b, t_start, t_end)
        self.appear = [0.0]
        for i in range(1, len(self.nodes)):
            p = self.nodes[i]
            par = min(range(i), key=lambda j: math.dist(self.nodes[j], p))
            t1 = 0.08 + self.grow * (math.dist(p, self.O) / R) ** 0.9
            self.appear.append(t1)
            self.edges.append((par, i, max(0.02, t1 - 0.28), t1))
        # 额外的近邻连线，让它更像网络而不是一棵树
        for i in range(2, len(self.nodes)):
            near = sorted(range(1, i), key=lambda j: math.dist(self.nodes[j], self.nodes[i]))[:2]
            for j in near[1:]:
                if math.dist(self.nodes[j], self.nodes[i]) < R * 0.35:
                    t1 = self.appear[i] + 0.15
                    self.edges.append((j, i, t1 - 0.2, t1))
        self.phase = [rnd.random() for _ in self.edges]
        self.blink = [rnd.uniform(0, 6.28) for _ in self.nodes]

    def apply(self, fr, t, z=1.0):
        cx, cy = W / 2, H / 2
        O = self.O
        def P_(p):  # 跟着底图一起推近；离起点越远的点越往上飘，起点固定在人物头顶
            drift = 22 * t * min(1.0, math.dist(p, O) / self.R)
            return (cx + (p[0] - cx) * z, cy + (p[1] - cy) * z - drift)
        sharp = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(sharp)
        fade = min(1.0, t / 0.25)
        for k, (a, b, t0, t1) in enumerate(self.edges):
            if t < t0:
                continue
            u = min(1.0, (t - t0) / max(1e-3, t1 - t0))
            u = ease_out(u)
            pa, pb = P_(self.nodes[a]), P_(self.nodes[b])
            pe = (pa[0] + (pb[0] - pa[0]) * u, pa[1] + (pb[1] - pa[1]) * u)
            d.line([pa, pe], fill=int(150 * fade), width=2)
            if u >= 1.0:  # 信号脉冲
                ph = ((t - t1) / 0.8 + self.phase[k]) % 1.0
                px, py = pa[0] + (pb[0] - pa[0]) * ph, pa[1] + (pb[1] - pa[1]) * ph
                d.ellipse([px - 3.5, py - 3.5, px + 3.5, py + 3.5], fill=int(255 * fade))
        for i, p in enumerate(self.nodes):
            if t < self.appear[i]:
                continue
            g = ease_out(min(1.0, (t - self.appear[i]) / 0.18))
            r = (3.0 + 2.0 * math.sin(t * 5 + self.blink[i]) * 0.5 + (4 if i == 0 else 0)) * g
            x, y = P_(p)
            d.ellipse([x - r, y - r, x + r, y + r], fill=int(255 * fade))
        glow = sharp.filter(ImageFilter.GaussianBlur(9))
        glow = glow.point(lambda v: min(255, int(v * 2.2)))
        col = Image.new("RGB", (W, H), self.col)
        black = Image.new("RGB", (W, H), (0, 0, 0))
        fr = ImageChops.screen(fr, Image.composite(col, black, glow))
        fr = ImageChops.screen(fr, Image.composite(col, black, sharp))
        return fr


_anim_cfg = hook.get("anim") or {}
HOOK_ANIM = NeuralAnim(_anim_cfg, t_hook) if _anim_cfg.get("type") == "neural" else None


# ---------- 咔哒音效 ----------
def click(strength=1.0, pitch=1.0, heavy=False):
    L = int(SR * 0.05)
    t = np.arange(L) / SR
    noise = np.random.randn(L) * np.exp(-t / 0.0025)
    noise = np.diff(noise, prepend=0)  # 粗略高通，让"咔"更脆
    ping = np.sin(2 * np.pi * 2600 * pitch * t) * np.exp(-t / 0.008) * 0.5
    ping2 = np.sin(2 * np.pi * 4100 * pitch * t) * np.exp(-t / 0.005) * 0.3
    thump = np.sin(2 * np.pi * (180 if heavy else 320) * t) * np.exp(-t / (0.02 if heavy else 0.008)) * (
        0.9 if heavy else 0.4)
    s = noise * 0.6 + ping + ping2 + thump
    return s / np.max(np.abs(s)) * strength


audio = np.zeros(int(SR * (T + 0.5)))


def put(sig, at):
    a = max(0, int(at * SR))
    audio[a:a + len(sig)] += sig[: len(audio) - a]


click_times = []
if sfx_sig is not None:
    sig = sfx_sig[: int(SR * (t_black - t_rou0 + sfx_lead))]
    put(sig / (np.max(np.abs(sig)) + 1e-9) * 0.8, t_rou0 - sfx_lead)
else:
    sub = rou.get("click_interval", 0.065)
    for k in range(n):
        put(click(0.85, random.uniform(0.95, 1.05)), starts[k])  # 换词必有一声
        click_times.append(starts[k])
        if k < n - 1:
            tt = starts[k] + sub
            while tt < starts[k + 1] - sub * 0.6 and durs[k] <= base_d + 1e-6:  # 快速段补中间咔哒
                put(click(0.55, random.uniform(0.9, 1.1)), tt)
                click_times.append(tt)
                tt += sub
    put(click(1.0, 0.8, heavy=True), starts[-1] + 0.005)  # 停住时一声闷"咔"

audio = audio / (np.max(np.abs(audio)) + 1e-9) * 0.7
out = P(CFG.get("out", "opening"))
wav = out + "_sfx.wav"
with wave.open(wav, "wb") as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    st = (np.repeat(audio[:, None], 2, axis=1) * 32767).astype(np.int16)
    wf.writeframes(st.tobytes())

# ---------- 输出视频 ----------
cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
       "-i", "-", "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{T:.3f}", out + ".mp4"]
pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
for i in range(NF):
    pr.stdin.write(render(i).tobytes())
pr.stdin.close()
pr.wait()

timing = {
    "total": round(T, 3),
    "hook_voice_at": 0.1,
    "roulette_start": round(t_rou0, 3),
    "word_starts": {w: round(s, 3) for w, s in zip(words, starts)},
    "black_start": round(t_black, 3),
    "reveal_start": round(t_rev, 3),
    "title_voice_at": round(t_rev + rev.get("type_delay", 0.15), 3),
    "reveal_video_used_seconds": round(rev_d, 3) if rev_is_video else None,
    "note": "正片接在揭晓段之后；若揭晓底用的是正片第一个镜头视频，正片从该镜头第 reveal_video_used_seconds 秒接着放",
}
json.dump(timing, open(out + "_timing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(timing, ensure_ascii=False, indent=2))
