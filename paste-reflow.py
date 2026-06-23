#!/usr/bin/env python3
"""Reformat copied Claude Code TUI output into clean (Obsidian) markdown.

Pipeline (see README for the full story):

  1. Acquire input. Either an explicit plain-text needle (passed as an arg or on
     stdin, e.g. from an Alfred Universal Action on a clipboard-history entry) or,
     by default, the live clipboard -- from which we grab BOTH the plain text and
     the styled `public.html` flavor that Ghostty writes.

  2. A3 -- transcript recovery (high fidelity). Use the plain text as a search
     needle against recent Claude Code session transcripts (~/.claude/projects/
     */*.jsonl). On a confident match we return the *original* source markdown --
     real backticks, links, code fences, the lot.

  3. B1 -- HTML reconstruction (fallback). No confident transcript match? Rebuild
     markdown from the clipboard HTML: bold via font-weight, inline code from any
     colored span (the TUI only colors accented text), then reflow.

  4. B2 -- plain reflow (last resort). No HTML either (e.g. an Alfred history
     entry, where the rich flavor has been stripped)? Reflow the plain text.

  5. Format. Strip the TUI's 2-space indent, collapse soft-wrapped single
     newlines into spaces, keep paragraph breaks and list breaks, then -- with
     --quote -- wrap as an Obsidian `> [!quote]` callout.

The clipboard I/O is deliberately isolated in read_clipboard_html/text() so the
guts can be swapped to pyobjc (NSPasteboard) later without touching anything else.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the bits most likely to need tweaking as you iterate.
# ---------------------------------------------------------------------------

# A line is a list item if, after indent-stripping, it starts like one of these.
LIST_MARKER = re.compile(r"^\s*([-*+]\s|\d+[.)]\s)")

# Markdown punctuation dropped when normalizing source text for matching.
INLINE_MD_CHARS = set("*`_~")

# How many of the most-recently-touched transcripts to search.
TRANSCRIPT_SCAN_COUNT = 3

# Don't trust a transcript match shorter than this (too easy to false-positive).
MIN_MATCH_LEN = 8

EMPTY = frozenset()


# ---------------------------------------------------------------------------
# Clipboard I/O  (the only macOS-specific layer -- swap to pyobjc here if ever)
# ---------------------------------------------------------------------------

def read_clipboard_text():
    """Plain-text flavor of the clipboard, or '' if none."""
    try:
        return subprocess.run(
            ["pbpaste"], capture_output=True, text=True, check=True
        ).stdout
    except Exception:
        return ""


def read_clipboard_html():
    """The `public.html` flavor as a decoded string, or None if absent.

    AppleScript returns it as «data HTML<hex>»; we pull the hex and decode.
    """
    try:
        out = subprocess.run(
            ["osascript", "-e", "the clipboard as «class HTML»"],
            capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        return None
    m = re.search(r"HTML([0-9A-Fa-f]+)", out)
    if not m:
        return None
    try:
        return bytes.fromhex(m.group(1)).decode("utf-8", "replace")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# A3 -- transcript recovery
# ---------------------------------------------------------------------------

def recent_transcripts(n=TRANSCRIPT_SCAN_COUNT):
    base = Path.home() / ".claude" / "projects"
    files = sorted(
        base.glob("*/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:n]


def assistant_messages(path):
    """Raw markdown of each assistant text block, newest first."""
    msgs = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return msgs
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        for block in obj.get("message", {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                msgs.append(block["text"])
    msgs.reverse()
    return msgs


def _normalize_with_map(raw):
    """Return (normalized_text, index_map) where index_map[i] is the offset in
    `raw` that produced normalized char i. Drops inline markdown punctuation,
    lowercases, and collapses whitespace runs to single spaces."""
    norm = []
    idx = []
    prev_space = False
    for i, ch in enumerate(raw):
        if ch in INLINE_MD_CHARS:
            continue
        if ch.isspace():
            if prev_space:
                continue
            norm.append(" ")
            idx.append(i)
            prev_space = True
        else:
            norm.append(ch.lower())
            idx.append(i)
            prev_space = False
    return "".join(norm), idx


def _normalize_needle(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _balanced(s):
    return s.count("*") % 2 == 0 and s.count("`") % 2 == 0


def recover_from_transcripts(needle_text):
    """Find the needle in recent transcripts and return the exact source
    markdown slice, or None if there's no confident match."""
    needle = _normalize_needle(needle_text)
    if len(needle) < MIN_MATCH_LEN:
        return None
    for path in recent_transcripts():
        for raw in assistant_messages(path):
            norm, idx = _normalize_with_map(raw)
            pos = norm.find(needle)
            if pos == -1:
                continue
            start = idx[pos]
            end = idx[pos + len(needle) - 1] + 1
            # Expand over markers sitting right at the boundary so we don't
            # slice through the middle of a **bold** or `code` span.
            while start > 0 and raw[start - 1] in INLINE_MD_CHARS:
                start -= 1
            while end < len(raw) and raw[end] in INLINE_MD_CHARS:
                end += 1
            slice_ = raw[start:end].strip()
            if slice_ and _balanced(slice_):
                return slice_
    return None


# ---------------------------------------------------------------------------
# Styled-char model: shared by the HTML (B1) and plain (B2) paths.
# A "char list" is a list of (character, style) where style is a frozenset
# subset of {"bold", "italic", "code"}.
# ---------------------------------------------------------------------------

def _style_from_css(style_attr):
    s = set()
    if re.search(r"font-weight:\s*(bold|[6-9]\d\d)", style_attr):
        s.add("bold")
    if re.search(r"font-style:\s*italic", style_attr):
        s.add("italic")
    # Any explicit text color -> inline code. The TUI only emits a `color:` for
    # accented spans (code, etc.); normal text carries none, so the specific
    # color doesn't matter. Match the `color` property, not `background-color`.
    if re.search(r"(?<![-\w])color\s*:\s*[^;]+", style_attr):
        s.add("code")
    return s


from html.parser import HTMLParser


class _GhosttyHTMLParser(HTMLParser):
    """Flattens Ghostty's clipboard HTML into a list of (char, style)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chars = []
        self._stack = [EMPTY]

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        added = _style_from_css(attr.get("style", ""))
        self._stack.append(self._stack[-1] | frozenset(added))
        if tag == "br":
            self.chars.append(("\n", EMPTY))
            self._stack.pop()

    def handle_endtag(self, tag):
        if len(self._stack) > 1:
            self._stack.pop()

    def handle_data(self, data):
        st = self._stack[-1]
        for ch in data:
            self.chars.append((ch, st))


def chars_from_html(html):
    p = _GhosttyHTMLParser()
    p.feed(html)
    return p.chars


def chars_from_plain(text):
    return [(ch, EMPTY) for ch in text]


# ---------------------------------------------------------------------------
# Reflow + markdown emission (operates on a char list)
# ---------------------------------------------------------------------------

def _strip_indent(line):
    """Remove the TUI's leading 2-space response indent (1 or 2 spaces)."""
    removed = 0
    while removed < 2 and line and line[0][0] == " " and not line[0][1]:
        line = line[1:]
        removed += 1
    return line


def _reflow(chars):
    """Join soft-wrapped lines, preserve paragraph and list breaks."""
    # Split on hard newlines into physical lines.
    lines = []
    cur = []
    for ch, st in chars:
        if ch == "\n":
            lines.append(cur)
            cur = []
        else:
            cur.append((ch, st))
    lines.append(cur)

    out = []
    pending_break = False  # a blank line was seen -> next content starts a paragraph
    for line in lines:
        line = _strip_indent(line)
        text = "".join(c[0] for c in line)
        if text.strip() == "":
            if out:
                pending_break = True
            continue
        if out:
            if pending_break:
                out += [("\n", EMPTY), ("\n", EMPTY)]
            elif LIST_MARKER.match(text):
                out.append(("\n", EMPTY))
            else:
                # soft wrap -> single space, unless one already abuts the seam
                if out[-1][0] != " " and line[0][0] != " ":
                    out.append((" ", EMPTY))
        out += line
        pending_break = False
    return out


def _collapse_spaces(chars):
    """Collapse runs of spaces to one (keeping the first's style); leave \n."""
    out = []
    for ch, st in chars:
        if ch == " " and out and out[-1][0] == " ":
            continue
        out.append((ch, st))
    return out


def _group(chars):
    groups = []
    for ch, st in chars:
        if groups and groups[-1][1] == st:
            groups[-1][0].append(ch)
        else:
            groups.append([[ch], st])
    return [("".join(g), st) for g, st in groups]


def _merge_ws_flanked(groups):
    """A whitespace-only plain group between two same non-empty styles belongs
    inside that style (e.g. `inline` <sp> `code` -> one `inline code` span)."""
    merged = []
    for i, (text, st) in enumerate(groups):
        if (not st and text.strip() == "" and merged and i + 1 < len(groups)
                and merged[-1][1] and merged[-1][1] == groups[i + 1][1]):
            merged[-1] = (merged[-1][0] + text, merged[-1][1])
            continue
        if merged and merged[-1][1] == st:
            merged[-1] = (merged[-1][0] + text, st)
        else:
            merged.append((text, st))
    return merged


def _markers(style):
    open_ = ("**" if "bold" in style else "") + ("*" if "italic" in style else "") + ("`" if "code" in style else "")
    close = ("`" if "code" in style else "") + ("*" if "italic" in style else "") + ("**" if "bold" in style else "")
    return open_, close


def _emit(groups):
    out = []
    for text, st in groups:
        if not st or not text.strip():
            out.append(text)
            continue
        core = text.strip()
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        open_, close = _markers(st)
        out.append(lead + open_ + core + close + trail)
    return "".join(out)


def chars_to_markdown(chars):
    reflowed = _collapse_spaces(_reflow(chars))
    return _emit(_merge_ws_flanked(_group(reflowed))).strip()


# ---------------------------------------------------------------------------
# Obsidian quote wrapping
# ---------------------------------------------------------------------------

def to_quote(md):
    out = ["> [!quote]"]
    for line in md.split("\n"):
        out.append("> " + line if line.strip() else ">")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def acquire(args):
    """Return (needle_text, html). html may be None.

    Robust to however Alfred's hotkey "argument" is configured: we always read
    the live clipboard (HTML and all). Explicit input (an argv/stdin string, e.g.
    an Alfred Universal Action on a history entry) overrides the needle, but we
    only trust the clipboard HTML when it corresponds to that same text.
    """
    if args.html_file:
        html = Path(args.html_file).read_text(errors="replace")
        return (args.text or ""), html

    explicit = None
    if args.text:
        explicit = args.text
    elif not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            explicit = piped

    clip_text = read_clipboard_text()
    clip_html = read_clipboard_html()

    if explicit is None:
        return clip_text, clip_html  # hotkey path: act on the live clipboard
    if clip_html and explicit.strip() == (clip_text or "").strip():
        return explicit, clip_html   # same content -> the HTML really is for it
    return explicit, None            # history/selection text -> no matching HTML


def build_markdown(needle_text, html, use_transcript=True):
    if use_transcript and needle_text and needle_text.strip():
        recovered = recover_from_transcripts(needle_text)
        if recovered is not None:
            return recovered  # already-clean source markdown
    if html:
        return chars_to_markdown(chars_from_html(html))
    if needle_text:
        return chars_to_markdown(chars_from_plain(needle_text))
    return ""


def main():
    ap = argparse.ArgumentParser(description="Reformat copied Claude Code output to markdown.")
    ap.add_argument("text", nargs="?", help="explicit plain-text input (else stdin, else live clipboard)")
    ap.add_argument("--quote", action="store_true", help="wrap as an Obsidian > [!quote] callout")
    ap.add_argument("--no-transcript", action="store_true", help="skip A3 transcript recovery")
    ap.add_argument("--html-file", help="read the HTML flavor from a file (testing)")
    args = ap.parse_args()

    needle_text, html = acquire(args)
    md = build_markdown(needle_text, html, use_transcript=not args.no_transcript)
    if not md:
        sys.stderr.write("paste-reflow: nothing to reformat\n")
        sys.exit(1)
    if args.quote:
        md = to_quote(md)
    sys.stdout.write(md)


if __name__ == "__main__":
    main()
