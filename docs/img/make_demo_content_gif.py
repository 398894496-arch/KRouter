"""Render docs/img/demo-content.gif: the same story as demo.gif, for short-video work instead of code. Every line
shown is real: the two vault pages are a demo vault's (the Chinese template plus these two pages), the `→` lines are
the router's recall output on it, and the answers are what `claude -p --plugin-dir .` (Claude Code with this repo's
plugin, a clean HOME, only the krouter_ask tool allowed) replied on 2026-10-18. Of three runs of the second
question, two answered as shown and one went off topic. Requires Pillow; macOS fonts.

    python3 docs/img/make_demo_content_gif.py docs/img/demo-content.gif
"""
import sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
W, H = 960, 540
BG, FG, DIM, ACC, OK, WARN, CARD = "#0f1115", "#e6e6e6", "#8a8f98", "#7aa2f7", "#9ece6a", "#e0af68", "#171a21"
MONO = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 17)
MONO_B = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 17, index=1)
CJK = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 17)
TITLE = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22, index=1)
CJK_TITLE = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 22, index=1)
SMALL = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
LH = 26
X0 = 40


def is_cjk(ch):
    return ord(ch) > 0x2E80


def draw_text(d, x, y, text, fill=FG, bold=False):
    for ch in text:
        f = CJK if is_cjk(ch) else (MONO_B if bold else MONO)
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f)
    return x


def wrap_en(text, width_chars=78):
    out, line = [], ""
    for word in text.split(" "):
        if len(line) + len(word) + 1 > width_chars:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    return out + [line]


def frame(title, day_color, lines, footer=True):
    """lines: [(text, color, bold)]"""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 54], fill=CARD)
    x = X0
    for ch in title:  # 标题字体不含汉字：汉字换成冬青黑体
        f = CJK_TITLE if is_cjk(ch) else TITLE
        d.text((x, 15), ch, font=f, fill=day_color)
        x += d.textlength(ch, font=f)
    y = 80
    for text, color, bold in lines:
        draw_text(d, X0, y, text, color, bold)
        y += LH
    if footer:
        draw_text(d, X0, H - 30, "真实输出：Claude Code + KRouter 插件，演示库，2026-10-18（github.com/398894496-arch/KRouter）", DIM)
    return im




frames, durations = [], []


def add(im, ms):
    frames.append(im)
    durations.append(ms)


mon = [("库：02 经验与方法/短视频/封面标题规则（周一）.md", DIM, False), ("", FG, False),
       ("# 封面标题规则（周一）", FG, True), ("", FG, False),
       ("封面标题用问句，最多 12 个字，例如「你的 agent 为什么总忘事？」。", FG, False)]
add(frame("周一 · 定了 A", ACC, mon), 2600)

wed = [("库：02 经验与方法/短视频/封面标题规则.md", DIM, False), ("", FG, False),
       ("# 封面标题规则", FG, True), ("", FG, False),
       ("封面标题直接给结论，最多 10 个字，不用问句。", OK, False),
       ("周三改的：问句标题发了三条，完播率都低于账号平均。", FG, False),
       ("取代「封面标题规则（周一）」。", FG, False), ("", FG, False),
       ("封面标题规则（周一）.md   status: superseded", WARN, False)]
add(frame("周三 · 改成 B", WARN, wed), 3400)

q1 = "封面标题现在怎么写？"
a1 = ["现在的封面标题要直接给结论，最多 10 个字，不用问句。", "例子：「agent 记住了你改的主意」",
      "来源：02 经验与方法/短视频/封面标题规则.md", "",
      "周一那版规则是用问句、最多 12 个字，比如「你的 agent 为什么总忘事？」。",
      "这版已经被上面的规则替换，不要再用了。"]
for i in range(0, len(q1) + 1):
    add(frame("周四 · 随便哪个 agent 来问", OK, [("> " + q1[:i] + "▌", FG, True)]), 110)
base = [("> " + q1, FG, True), ("", FG, False), ("  krouter_ask(\"封面标题现在怎么写？\")", DIM, False),
        ("  → 02 经验与方法/短视频/封面标题规则.md  tier=rule status=active", DIM, False), ("", FG, False)]
add(frame("周四 · 随便哪个 agent 来问", OK, base), 1400)
add(frame("周四 · 随便哪个 agent 来问", OK, base + [(ln, FG, False) for ln in a1]), 5200)

q2 = "我们定的直播几点开播？"
a2 = ["我在你的知识库里查过了，没有找到直播开播时间的记录，", "所以我没法告诉你定的是几点。", "",
      "如果这件事是在别处定的（比如聊天记录、日历或会议纪要），", "可以把时间发给我。"]
for i in range(0, len(q2) + 1):
    add(frame("库里没有的事", ACC, [("> " + q2[:i] + "▌", FG, True)]), 110)
base2 = [("> " + q2, FG, True), ("", FG, False), ("  krouter_ask(\"我们定的直播几点开播？\")", DIM, False),
         ("  → recall: none（库里没有页面覆盖这个问题；不要猜）", WARN, False), ("", FG, False)]
add(frame("库里没有的事", ACC, base2), 1400)
add(frame("库里没有的事", ACC, base2 + [(ln, FG, False) for ln in a2]), 5000)

pal = [f.convert("P", palette=Image.ADAPTIVE, colors=32) for f in frames]
pal[0].save(OUT, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True, disposal=1)
print(len(frames), "frames")
