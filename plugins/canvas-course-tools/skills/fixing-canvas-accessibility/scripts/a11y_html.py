"""Shared code for scan_a11y.py and fix_a11y.py: locate elements, check them, edit them.

Every finding names its element by file, tag and occurrence number, and records the
element's exact start tag. The fixer re-parses the file and refuses to edit an element
whose start tag no longer matches, so a fix can never land on the wrong element.
Standard library only.
"""
import colorsys
import html
import html.parser
import re
from urllib.parse import urlparse

VOID = {"img", "br", "hr", "input", "meta", "link", "source", "area", "col", "embed", "wbr", "param", "track"}
HEADINGS = {f"h{i}": i for i in range(1, 7)}
VAGUE_LINK = {"click here", "here", "click", "link", "this link", "read more", "more", "learn more", "see here",
              "this", "go", "details", "more info", "info", "download", "click this"}
NAMED = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
         "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0", "maroon": "#800000", "navy": "#000080",
         "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080", "teal": "#008080", "olive": "#808000",
         "lime": "#00ff00", "aqua": "#00ffff", "fuchsia": "#ff00ff", "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3",
         "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9"}
MAX_ALT = 150        # characters; longer alt text belongs in a caption or long description
MAX_HEADING = 120    # characters, the limit the Canvas accessibility checker uses
NORMAL_RATIO, LARGE_RATIO = 4.5, 3.0   # WCAG 2.1 AA, success criterion 1.4.3


class Element:
    def __init__(self, tag, attrs, raw, start, index):
        self.tag, self.attrs, self.raw, self.start, self.index = tag, dict(attrs), raw, start, index
        self.end_start = self.end = None   # offsets of the end tag
        self.text = []                     # text directly or indirectly inside
        self.parent = None
        self.children = []

    @property
    def inner_text(self):
        return re.sub(r"\s+", " ", "".join(self.text)).strip()

    def locator(self, file):
        return {"file": file, "tag": self.tag, "index": self.index, "raw": self.raw}


class Parsed(html.parser.HTMLParser):
    """Parse HTML, keeping each element's exact offsets so edits can be surgical."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.line_starts = [0]
        for m in re.finditer("\n", source):
            self.line_starts.append(m.end())
        self.elements, self.stack, self.counts = [], [], {}
        self.feed(source)
        self.close()

    def _offset(self):
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        n = self.counts.get(tag, 0)
        self.counts[tag] = n + 1
        el = Element(tag, attrs, self.get_starttag_text(), self._offset(), n)
        el.parent = self.stack[-1] if self.stack else None
        if el.parent:
            el.parent.children.append(el)
        self.elements.append(el)
        if tag not in VOID:
            self.stack.append(el)
        else:
            el.end_start = el.end = el.start + len(el.raw)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1].tag == tag and tag not in VOID:
            el = self.stack.pop()
            el.end_start = el.end = el.start + len(el.raw)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                el = self.stack[i]
                el.end_start = self._offset()
                close = self.source.find(">", el.end_start)
                el.end = close + 1 if close != -1 else el.end_start
                del self.stack[i:]
                return

    def handle_data(self, data):
        for el in self.stack:
            el.text.append(data)

    def find(self, tag, index):
        for el in self.elements:
            if el.tag == tag and el.index == index:
                return el
        return None


# ---------------------------------------------------------------- color

def parse_color(value):
    v = (value or "").strip().lower()
    if v in NAMED:
        return NAMED[v]
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)", v)
    if m and (m.group(4) is None or float(m.group(4)) >= 1):
        return "#%02x%02x%02x" % tuple(min(255, int(m.group(i))) for i in (1, 2, 3))
    return None


def luminance(hexs):
    r, g, b = (int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(fg, bg):
    a, b = luminance(fg), luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def fix_color(fg, bg, target):
    """The closest color to fg, same hue and saturation, that meets target against bg."""
    r, g, b = (int(fg[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    best = None
    for step in range(0, 101):
        for direction in (-1, 1):
            nl = l + direction * step / 100
            if not 0 <= nl <= 1:
                continue
            cand = "#%02x%02x%02x" % tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, nl, s))
            if contrast(cand, bg) >= target:
                best = cand
                break
        if best:
            break
    return best or ("#000000" if luminance(bg) > 0.18 else "#ffffff")


def style_props(style):
    props = {}
    for part in (style or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            props[k.strip().lower()] = v.strip()
    return props


def size_pt(value):
    m = re.fullmatch(r"([\d.]+)\s*(pt|px|em|rem|%)?", (value or "").strip().lower())
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2) or "px"
    return {"pt": n, "px": n * 0.75, "em": n * 12, "rem": n * 12, "%": n * 0.12}[unit]


# ---------------------------------------------------------------- checks

def effective(el, prop):
    """The nearest value of a style property on el or an ancestor, and the element it is on."""
    node = el
    while node is not None:
        props = style_props(node.attrs.get("style"))
        for key in ([prop] if prop != "background-color" else ["background-color", "background"]):
            if key in props:
                val = props[key] if key != "background" else (props[key].split() or [""])[0]
                return val, node
        node = node.parent
    return None, None


def is_large(el):
    size, _ = effective(el, "font-size")
    pt = size_pt(size) if size else None
    node, bold = el, False
    while node is not None:
        if node.tag in ("b", "strong", "h1", "h2", "h3", "h4", "h5", "h6") or \
                style_props(node.attrs.get("style")).get("font-weight", "") in ("bold", "bolder", "700", "800", "900"):
            bold = True
        if node.tag in ("h1", "h2") and pt is None:
            return True
        node = node.parent
    if pt is None:
        return False
    return pt >= 18 or (bold and pt >= 14)


def check(file, source, title=""):
    """Every finding in one HTML body. Each is a dict ready for the report and the plan."""
    p = Parsed(source)
    out = []

    def add(rule, el, message, fix=None, value=None, needs=None, severity="defect", wcag=""):
        out.append({"rule": rule, "severity": severity, "wcag": wcag, "file": file, "title": title,
                    "element": el.locator(file) if el else None, "message": message,
                    "fix": fix, "value": value, "needs": needs})

    last_level = None
    for el in p.elements:
        t = el.tag
        if t in HEADINGS:
            level = HEADINGS[t]
            text = el.inner_text
            if not text:
                add("heading-empty", el, f"an empty <{t}> is announced to screen readers as a heading with no name",
                    fix="remove", severity="defect", wcag="1.3.1")
                continue
            if level == 1:
                add("heading-h1", el, f'"{text[:60]}" is an h1; Canvas uses h1 for the page title, so headings in the body start at h2',
                    fix="rename", value="h2", wcag="1.3.1")
                level = 2
            elif last_level is not None and level > last_level + 1:
                new = f"h{last_level + 1}"
                add("heading-skip", el, f'"{text[:60]}" is an <{t}> after an <h{last_level}>, skipping a level',
                    fix="rename", value=new, wcag="1.3.1")
                level = last_level + 1
            if len(text) > MAX_HEADING:
                add("heading-long", el, f"a heading of {len(text)} characters reads as a paragraph", severity="warning", wcag="2.4.6")
            last_level = level
        elif t == "img":
            alt = el.attrs.get("alt")
            role = (el.attrs.get("role") or "").lower()
            src = el.attrs.get("src") or ""
            if alt is None and role != "presentation":
                add("img-alt-missing", el, f"image {src.split('/')[-1][:60]!r} has no alt text",
                    fix="set_attr:alt", needs="alt text describing what the image shows, or \"\" if it is decorative", wcag="1.1.1")
            elif alt is not None and alt.strip() and (re.search(r"\.(png|jpe?g|gif|svg|webp|bmp)$", alt.strip(), re.I)
                                                       or alt.strip().lower() in ("image", "picture", "photo", "graphic")):
                add("img-alt-useless", el, f"alt text {alt!r} does not describe the image",
                    fix="set_attr:alt", needs="alt text describing what the image shows", wcag="1.1.1")
            elif alt and len(alt) > MAX_ALT:
                add("img-alt-long", el, f"alt text is {len(alt)} characters; screen readers cannot skim it",
                    severity="warning", fix="set_attr:alt", needs=f"a shorter alt text (under {MAX_ALT} characters)", wcag="1.1.1")
        elif t == "a" and el.attrs.get("href"):
            text = el.inner_text
            has_img_alt = any(c.tag == "img" and (c.attrs.get("alt") or "").strip() for c in el.children)
            label = el.attrs.get("aria-label") or el.attrs.get("title")
            if not text and not has_img_alt and not label:
                add("link-empty", el, f"a link to {el.attrs['href'][:60]!r} has no text", fix="link_text",
                    needs="link text that says where the link goes", wcag="2.4.4")
            elif text.lower().strip(" .:!") in VAGUE_LINK:
                add("link-vague", el, f'link text "{text[:60]}" does not say where it goes ({el.attrs["href"][:60]})',
                    fix="link_text", needs="link text that says where the link goes", wcag="2.4.4")
            elif re.fullmatch(r"(https?://|www\.)\S+", text):
                # A bare address does say where it goes, but a screen reader spells it out.
                add("link-bare-url", el, f'link text is the address itself ("{text[:60]}"), which screen readers read character by character',
                    severity="warning", fix="link_text", needs="link text naming the page", wcag="2.4.4")
        elif t == "table":
            rows = [c for c in el.children if c.tag == "tr"] + [r for c in el.children if c.tag in ("thead", "tbody")
                                                                for r in c.children if r.tag == "tr"]
            cells = [c for r in rows for c in r.children if c.tag in ("td", "th")]
            if not cells:
                continue
            if not any(c.tag == "th" for c in cells):
                first = [c.inner_text for c in rows[0].children if c.tag in ("td", "th")] if rows else []
                add("table-no-header", el, f"a table of {len(rows)} rows has no header cells; its first row is {first[:4]}",
                    fix="header_row", value="first_row", needs="confirm the first row is the header, or \"skip\" for a layout table",
                    wcag="1.3.1")
            if not any(c.tag == "caption" and c.inner_text for c in el.children):
                # The proposal is the text of the nearest heading above the table, which
                # usually names it; with no heading there is no proposal.
                above = [h for h in p.elements if h.tag in HEADINGS and h.end is not None and h.end <= el.start]
                heading = above[-1].inner_text[:90] if above else ""
                add("table-no-caption", el, "a table has no caption naming what it shows", severity="warning",
                    fix="caption", value=heading or None, needs="a short caption naming what the table shows", wcag="1.3.1")
            for c in cells:
                if c.tag == "th" and not c.attrs.get("scope"):
                    in_first_row = rows and c.parent is rows[0]
                    add("th-no-scope", c, f'header cell "{c.inner_text[:40]}" does not say whether it heads a row or a column',
                        fix="set_attr:scope", value="col" if in_first_row else "row", wcag="1.3.1")
        elif t == "iframe":
            if not (el.attrs.get("title") or "").strip():
                host = urlparse(el.attrs.get("src") or "").netloc or "another site"
                add("iframe-no-title", el, f"embedded content from {host} has no title", fix="set_attr:title",
                    value=f"Embedded content from {host}", needs="a title naming what is embedded", wcag="4.1.2")
        elif t == "u":
            add("underline", el, f'underlined text "{el.inner_text[:40]}" looks like a link', severity="warning", wcag="1.3.3")

    # Contrast: each element whose own style sets a text color, checked against the
    # nearest background (white when none is set, as in Canvas).
    for el in p.elements:
        color = style_props(el.attrs.get("style")).get("color")
        if not color or not el.inner_text:
            continue
        fg = parse_color(color)
        bg_raw, _ = effective(el, "background-color")
        bg = parse_color(bg_raw) if bg_raw else "#ffffff"
        if not fg or not bg:
            continue
        target = LARGE_RATIO if is_large(el) else NORMAL_RATIO
        ratio = contrast(fg, bg)
        if ratio < target:
            add("contrast", el, f'text "{el.inner_text[:40]}" is {fg} on {bg}, a contrast of {ratio:.2f}:1; it needs {target}:1',
                fix="set_style:color", value=fix_color(fg, bg, target), wcag="1.4.3")

    # Lists typed as paragraphs: two or more consecutive paragraphs starting with a bullet.
    paras = [el for el in p.elements if el.tag == "p"]
    run = 0
    for el in paras:
        if re.match(r"^\s*([-•*–]|\d+[.)])\s+\S", el.inner_text):
            run += 1
            if run == 2:
                add("fake-list", el, "paragraphs that start with bullets or numbers are read as plain text, not a list",
                    severity="warning", wcag="1.3.1")
        else:
            run = 0
    return out


# ---------------------------------------------------------------- edits

def set_attr(raw, name, value):
    val = html.escape(value, quote=True)
    pattern = re.compile(rf'(\s{re.escape(name)}\s*=\s*)("[^"]*"|\'[^\']*\'|[^\s>]+)', re.I)
    if pattern.search(raw):
        return pattern.sub(lambda m: f'{m.group(1)}"{val}"', raw, count=1)
    return re.sub(r"\s*(/?)>$", lambda m: f' {name}="{val}"{(" " + m.group(1)) if m.group(1) else ""}>', raw, count=1)


def set_style(raw, prop, value):
    m = re.search(r'\sstyle\s*=\s*("([^"]*)"|\'([^\']*)\')', raw, re.I)
    style = (m.group(2) if m and m.group(2) is not None else m.group(3)) if m else ""
    parts = [x for x in style.split(";") if x.strip() and x.split(":")[0].strip().lower() != prop]
    parts.append(f"{prop}: {value}")
    return set_attr(raw, "style", "; ".join(x.strip() for x in parts))


def ops_for(fix, el):
    """Turn one fix into element-level operations.

    ("tag", element, function) rewrites an element's start tag; several of these on the
    same element are combined, so a heading can be renamed and recolored in one pass.
    ("range", start, end, text) replaces a span of the source outside any start tag.
    """
    kind, value = fix["fix"], fix["value"]
    if kind == "rename":
        ops = [("tag", el, lambda raw, v=value, t=el.tag: re.sub(rf"^<{t}", f"<{v}", raw, count=1, flags=re.I))]
        if el.end_start is not None and el.end_start > el.start:
            ops.append(("range", el.end_start, el.end, f"</{value}>"))
        return ops
    if kind == "remove":
        return [("range", el.start, el.end, "")]
    if kind.startswith("set_attr:"):
        name = kind.split(":", 1)[1]
        return [("tag", el, lambda raw, n=name, v=value: set_attr(raw, n, v))]
    if kind.startswith("set_style:"):
        prop = kind.split(":", 1)[1]
        return [("tag", el, lambda raw, n=prop, v=value: set_style(raw, n, v))]
    if kind == "link_text":
        return [("range", el.start + len(el.raw), el.end_start, html.escape(value, quote=False))]
    if kind == "caption":
        at = el.start + len(el.raw)
        return [("range", at, at, f"<caption>{html.escape(value, quote=False)}</caption>")]
    if kind == "header_row":
        if value == "skip":
            return []
        rows = [c for c in el.children if c.tag == "tr"] + [r for c in el.children if c.tag in ("thead", "tbody")
                                                            for r in c.children if r.tag == "tr"]
        ops = []
        for c in rows[0].children if rows else []:
            if c.tag == "td":
                ops.append(("tag", c, lambda raw: set_attr(re.sub(r"^<td", "<th", raw, count=1, flags=re.I), "scope", "col")))
                if c.end_start is not None and c.end_start > c.start:
                    ops.append(("range", c.end_start, c.end, "</th>"))
        return ops
    raise ValueError(f"unknown fix {kind}")


def apply(source, fixes):
    """Apply fixes to one file's source. Raises ValueError if any element moved or changed."""
    p = Parsed(source)
    tag_ops, ranges = {}, []
    for f in fixes:
        loc = f["element"]
        el = p.find(loc["tag"], loc["index"])
        if el is None or el.raw != loc["raw"]:
            raise ValueError(f'{loc["file"]}: <{loc["tag"]}> #{loc["index"]} is not where the scan found it; rescan first')
        for op in ops_for(f, el):
            if op[0] == "tag":
                tag_ops.setdefault(id(op[1]), [op[1], []])[1].append(op[2])
            else:
                ranges.append(op[1:])
    for el, fns in tag_ops.values():
        raw = el.raw
        for fn in fns:
            raw = fn(raw)
        ranges.append((el.start, el.start + len(el.raw), raw))
    ranges.sort(key=lambda e: (e[0], e[1]), reverse=True)
    for i in range(1, len(ranges)):
        if ranges[i][1] > ranges[i - 1][0]:
            raise ValueError("two fixes overlap; apply one, rescan, then apply the other")
    for start, end, text in ranges:
        source = source[:start] + text + source[end:]
    return source
