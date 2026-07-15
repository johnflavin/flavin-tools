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
import itertools
import json
import re
import subprocess
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the bits most likely to need tweaking as you iterate.
# ---------------------------------------------------------------------------

# A line is a list item if, after indent-stripping, it starts like one of these.
LIST_MARKER = re.compile(r"^\s*([-*+]\s|\d+[.)]\s)")

# Markdown punctuation that may be markup at a slice boundary. `*` `_` and (in
# pairs) `~` are emphasis/strikethrough the TUI strips; backticks delimit code.
# NB: a *lone* `~` is literal ("~50"), not strikethrough -- see _normalize_core.
INLINE_MD_CHARS = set("*`_~")

# A code-fence delimiter line: optional indent, 3+ backticks/tildes, then an
# optional info string (e.g. ```bash). The TUI renders neither the fence nor the
# info string, so for matching purposes these lines contribute nothing.
FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*$")

# The leading marker of an ATX heading: up to 3 spaces of indent then 1-6 `#`.
# CommonMark only treats it as a heading if a space/tab (or end of line) follows
# the # run -- "#tag" is literal text -- so callers must verify that separately.
# The TUI renders headings with the # markers (and any closing # run) stripped.
HEADING_HASHES = re.compile(r"[ \t]{0,3}#{1,6}")
# The optional closing # run of an ATX heading (must be preceded by whitespace).
HEADING_CLOSE = re.compile(r"[ \t]+#+[ \t]*\Z")

# How many of the most-recently-touched transcripts to search by default. Bumped
# 3 -> 10 so a source session doesn't fall out of range when several worktree/CC
# sessions are active in parallel (the case that broke recovery). Transcripts are
# streamed and short-circuited, so scanning more is cheap; --scan-depth overrides.
TRANSCRIPT_SCAN_COUNT = 10

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
    # osascript wraps long output across lines, so the hex run can be broken by
    # whitespace; grab everything up to the closing guillemet and strip it.
    m = re.search(r"HTML([0-9A-Fa-f\s]+?)»", out) or re.search(r"HTML([0-9A-Fa-f\s]+)", out)
    if not m:
        return None
    hex_str = re.sub(r"\s", "", m.group(1))
    try:
        return bytes.fromhex(hex_str).decode("utf-8", "replace")
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
    """Raw markdown of each assistant text block, newest first.

    Streams the file line-by-line (transcripts run to many MB) and skips the
    cheap way past non-assistant lines before paying for json.loads -- most of a
    session is user/tool_result/tool_use entries. We still buffer the matched
    texts and reverse, since JSONL is forward-only and the caller wants newest
    first."""
    msgs = []
    try:
        f = path.open(errors="replace")
    except OSError:
        return msgs
    with f:
        for line in f:
            if '"assistant"' not in line:
                continue
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


def _normalize_core(raw, want_map, emit_labels=False):
    """Normalize `raw` so it lines up with the TUI-rendered text we search for.

    Lowercases, collapses whitespace runs to single spaces, and -- crucially for
    code -- works fence- and inline-code-aware:

      * Fence-delimiter lines (``` / ~~~, with any info string) render to nothing
        in the TUI, so we emit nothing for them. This also stops the info string
        (the `bash` in ```bash) from leaking in as a stray word. EXCEPTION,
        controlled by emit_labels: an OPENING fence's info string may instead be
        emitted as a word, because some blocks render their language as a visible
        label above the code that lands in a copied selection. Whether a given
        block shows its label is inconsistent (a recognized, syntax-highlighted
        language like ```sql tends not to; an unrecognized one like ```fish
        does), and a single message can mix both -- so emit_labels is per-fence:
        False/empty -> emit no labels; True -> emit every opening fence's label;
        a set of ints -> emit only the opening fences whose 0-based document
        order is in the set. The closing fence has no info string, emits nothing.
      * An ATX heading's markers (leading `#`..`######` and any closing `#` run)
        render to nothing in the TUI, so we drop them and keep only the heading
        text -- otherwise a heading mid-selection ("## Foo") wouldn't line up
        with the needle ("Foo"). Headings only exist outside fenced blocks; a `#`
        inside a fence (a shell/py comment) stays literal.
      * Inside a fenced block we DON'T drop `* ` _ ~`: there they're literal code
        characters that the TUI renders verbatim, so the needle keeps them too.
      * Inside an inline `code` span (single backticks) the same holds: the TUI
        renders the span's contents literally -- underscores and all -- so a
        needle copied from the TUI keeps e.g. `to_date`'s underscore. We drop the
        backtick delimiters (the TUI shows no backticks) but keep `* _ ~` inside.
        Outside code, `*` and `_` are emphasis the TUI strips, so we strip them to
        match; `~` is stripped only as part of a `~~` strikethrough pair, since a
        lone `~` (e.g. "~50", "approximately") is literal text the TUI shows
        verbatim. (Inline code can't span physical lines, so the in-code state
        resets at every line break.)

    When want_map is True, also returns index_map where index_map[i] is the
    offset in `raw` that produced normalized char i (used to slice the original
    markdown back out on a hit)."""
    norm = []
    idx = [] if want_map else None
    prev_space = False
    in_fence = False
    fence_ord = 0  # 0-based index of the opening fence we're at, in doc order
    pos, n = 0, len(raw)

    def _append(ch, off):
        nonlocal prev_space
        if ch.isspace():
            if prev_space:
                return
            norm.append(" ")
            prev_space = True
        else:
            norm.append(ch.lower())
            prev_space = False
        if want_map:
            idx.append(off)

    while pos <= n:
        nl = raw.find("\n", pos)
        line_end = n if nl == -1 else nl
        fence = FENCE_LINE.match(raw[pos:line_end])
        if fence:
            opening = not in_fence
            in_fence = not in_fence  # delimiter line: toggle
            if opening:
                # The info string follows the ``` / ~~~ run; the TUI may show it
                # as the block's language label, so emit it as a word when this
                # fence is selected by emit_labels.
                if emit_labels is True:
                    emit_this = True
                elif emit_labels:  # a set of opening-fence ordinals
                    emit_this = fence_ord in emit_labels
                else:  # False or empty set
                    emit_this = False
                if emit_this:
                    for off in range(pos + fence.end(1), line_end):
                        _append(raw[off], off)
                fence_ord += 1
        else:
            in_code = False  # inline code never spans a physical line
            line_start, line_stop = pos, line_end
            if not in_fence:
                # Strip an ATX heading's markers: the TUI renders "## Foo" as
                # just "Foo". Only a # run followed by whitespace or end-of-line
                # is a heading ("#tag" is literal); any closing # run goes too.
                hm = HEADING_HASHES.match(raw, pos, line_end)
                if hm and (hm.end() == line_end or raw[hm.end()] in " \t"):
                    line_start = hm.end()
                    while line_start < line_end and raw[line_start] in " \t":
                        line_start += 1
                    cm = HEADING_CLOSE.search(raw[line_start:line_end])
                    if cm:
                        line_stop = line_start + cm.start()
            for off in range(line_start, line_stop):
                ch = raw[off]
                if not in_fence:
                    if ch == "`":
                        in_code = not in_code  # inline-code delimiter: drop it
                        continue
                    if not in_code:
                        if ch == "~":
                            # Strikethrough is a matched ~~ pair; a lone ~ is
                            # literal text the TUI shows verbatim (e.g. "~50"), so
                            # keep it. Drop a ~ only within a ~~ run. (Neighbor
                            # checks stay within the line's content region so a
                            # stripped heading marker never counts as adjacent.)
                            if (off + 1 < line_stop and raw[off + 1] == "~") or \
                               (off > line_start and raw[off - 1] == "~"):
                                continue
                        elif ch == "_":
                            # An intraword underscore (word_word) is literal in
                            # CommonMark -- it can't open or close emphasis -- so
                            # the TUI shows it verbatim (work_mem, snake_case).
                            # Keep it; strip only a flanking _ that is emphasis.
                            if not (off > line_start and raw[off - 1].isalnum()
                                    and off + 1 < line_stop and raw[off + 1].isalnum()):
                                continue
                        elif ch in INLINE_MD_CHARS:
                            continue  # * emphasis the TUI renders away
                _append(ch, off)
        if nl == -1:
            break
        # The line break between lines is whitespace -> a single space.
        if norm and not prev_space:
            norm.append(" ")
            if want_map:
                idx.append(nl)
            prev_space = True
        pos = nl + 1
    text = "".join(norm)
    return (text, idx) if want_map else text


def _normalize(raw, emit_labels=False):
    """Normalized text only -- used for the common no-match case, where building
    the parallel index map would be wasted."""
    return _normalize_core(raw, want_map=False, emit_labels=emit_labels)


def _normalize_with_map(raw, emit_labels=False):
    """(normalized_text, index_map); see _normalize_core. Built only on a hit."""
    return _normalize_core(raw, want_map=True, emit_labels=emit_labels)


def _labeled_fence_ordinals(raw):
    """0-based doc-order indices of the opening fences that carry a non-empty
    info string (a language label). Only these can differ between the label-on
    and label-off normalizations, so recovery enumerates over just this set."""
    ords = []
    ordinal = 0
    in_fence = False
    pos, n = 0, len(raw)
    while pos <= n:
        nl = raw.find("\n", pos)
        line_end = n if nl == -1 else nl
        m = FENCE_LINE.match(raw[pos:line_end])
        if m:
            if not in_fence:  # opening fence
                if raw[pos + m.end(1):line_end].strip():
                    ords.append(ordinal)
                ordinal += 1
            in_fence = not in_fence
        if nl == -1:
            break
        pos = nl + 1
    return ords


# Cap on labeled fences we enumerate all 2^k subsets of; beyond it we try only
# the two extremes (no labels / all labels). A message with this many labeled
# code blocks in one selection is pathological; the cap bounds the blow-up.
MAX_LABEL_ENUM = 12


def _label_combos(raw):
    """Yield emit_labels sets to try, cheapest/most-likely first: no labels,
    then (only if the message has labeled fences) every non-empty subset of
    them. Lazily computes the fence set so a fence-free message pays nothing
    beyond the first (empty) yield."""
    yield frozenset()
    if "```" not in raw and "~~~" not in raw:
        return
    labeled = _labeled_fence_ordinals(raw)
    if not labeled:
        return
    if len(labeled) > MAX_LABEL_ENUM:
        yield frozenset(labeled)  # too many to enumerate: try the all-on extreme
        return
    for r in range(1, len(labeled) + 1):
        for combo in itertools.combinations(labeled, r):
            yield frozenset(combo)


def _fence_blocks(raw):
    """Char ranges (open_start, close_end) of complete fenced blocks in `raw`.

    open_start is the offset of the opening fence line; close_end is the offset
    just past the closing fence line. An unterminated fence runs to end-of-text.
    Used to snap a match boundary that lands inside a block out to the whole
    block, so the recovered slice never has a dangling ``` fence."""
    blocks = []
    open_start = None
    pos, n = 0, len(raw)
    while pos <= n:
        nl = raw.find("\n", pos)
        line_end = n if nl == -1 else nl
        if FENCE_LINE.match(raw[pos:line_end]):
            if open_start is None:
                open_start = pos
            else:
                blocks.append((open_start, line_end))
                open_start = None
        if nl == -1:
            break
        pos = nl + 1
    if open_start is not None:
        blocks.append((open_start, n))
    return blocks


def _snap_to_fences(start, end, blocks):
    """If start/end land inside a fenced block, widen them to the whole block."""
    for bs, be in blocks:
        if bs <= start < be:
            start = bs
        if bs < end <= be:
            end = be
    return start, end


def _snap_to_heading_start(start, raw):
    """If `start` sits at the first text char of an ATX heading -- i.e. the whole
    of that line before `start` is just the heading's `#` marker and its spaces
    -- move it back onto the marker. A selection that began at the start of a
    heading line thus keeps its "## " rather than dropping it (normalize strips
    heading markers, so the raw match otherwise starts past them)."""
    ls = raw.rfind("\n", 0, start) + 1  # start of the line containing `start`
    hm = HEADING_HASHES.match(raw, ls, start)
    # A real heading needs whitespace after the # run; "##content" is literal.
    if not hm or hm.end() >= start or raw[hm.end()] not in " \t":
        return start
    j = hm.end()
    while j < start and raw[j] in " \t":
        j += 1
    return ls if j == start else start


def _normalize_needle(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _balanced(s):
    # Every inline-markdown marker we expand over at slice boundaries must come
    # in pairs, or we'd return a slice with a dangling */`/_/~ marker. Markers
    # INSIDE a fenced block are literal code, not markup, so they may be odd --
    # strip fenced regions out before counting.
    outside = []
    prev = 0
    for bs, be in _fence_blocks(s):
        outside.append(s[prev:bs])
        prev = be
    outside.append(s[prev:])
    rest = "".join(outside)
    # Walk what's left tracking inline-code spans the same way _normalize_core
    # does: `_ * ~` inside a `code` span are literal, so they don't need to
    # pair; only the backticks and the emphasis markers outside code do. `~` is
    # special: a lone one is literal ("~50"), so only a `~~` strikethrough run is
    # a delimiter -- we require those runs to pair but never reject on a lone ~.
    # `_` is likewise special: an intraword underscore (word_word) is literal in
    # CommonMark ("work_mem"), so it doesn't pair -- only a flanking _ does.
    # In-code state resets at line breaks (inline code is single-line).
    counts = {"*": 0, "_": 0, "`": 0}
    tilde_runs = 0  # runs of >=2 tildes: strikethrough delimiters, must pair
    in_code = False
    i, m = 0, len(rest)
    while i < m:
        ch = rest[i]
        if ch == "\n":
            in_code = False
            i += 1
        elif ch == "`":
            counts["`"] += 1
            in_code = not in_code
            i += 1
        elif in_code:
            i += 1
        elif ch == "~":
            j = i
            while j < m and rest[j] == "~":
                j += 1
            if j - i >= 2:
                tilde_runs += 1
            i = j
        elif ch == "_":
            # Intraword _ (word_word) is literal, not an emphasis delimiter;
            # only a flanking _ needs to pair.
            if not (i > 0 and rest[i - 1].isalnum()
                    and i + 1 < m and rest[i + 1].isalnum()):
                counts["_"] += 1
            i += 1
        elif ch in counts:  # *
            counts[ch] += 1
            i += 1
        else:
            i += 1
    return all(v % 2 == 0 for v in counts.values()) and tilde_runs % 2 == 0


def recover_from_transcripts(needle_text, scan_depth=TRANSCRIPT_SCAN_COUNT):
    """Find the needle in recent transcripts and return the exact source
    markdown slice, or None if there's no confident match.

    scan_depth caps how many of the most-recently-touched transcripts to search
    (default TRANSCRIPT_SCAN_COUNT); raise it to dig content out of an older
    session."""
    needle = _normalize_needle(needle_text)
    if len(needle) < MIN_MATCH_LEN:
        return None
    for path in recent_transcripts(scan_depth):
        for raw in assistant_messages(path):
            # Try the default normalization first (all fence labels dropped); on
            # a miss, retry with per-fence subsets of the language labels emitted,
            # since a selection may include some blocks' labels but not others'
            # (see _normalize_core). The enumeration only kicks in for a message
            # that has labeled fences and didn't already match.
            for emit_labels in _label_combos(raw):
                pos = _normalize(raw, emit_labels).find(needle)
                if pos == -1:
                    continue
                _, idx = _normalize_with_map(raw, emit_labels)  # map only on a hit
                start = idx[pos]
                end = idx[pos + len(needle) - 1] + 1
                # A match that lands inside a code fence must carry the whole
                # fence, or we'd return a block with a dangling ``` delimiter.
                start, end = _snap_to_fences(start, end, _fence_blocks(raw))
                # Expand over markers sitting right at the boundary so we don't
                # slice through the middle of a **bold** or `code` span.
                while start > 0 and raw[start - 1] in INLINE_MD_CHARS:
                    start -= 1
                while end < len(raw) and raw[end] in INLINE_MD_CHARS:
                    end += 1
                # If the match began at the text of a heading, pull the "## "
                # marker back in -- a selection that started at the line head
                # meant to include it (normalize drops markers for alignment).
                start = _snap_to_heading_start(start, raw)
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

    # read_clipboard_html() shells out to osascript (slow), so only pay for it on
    # the paths that actually use the result.
    if explicit is None:
        return clip_text, read_clipboard_html()  # hotkey path: act on live clipboard
    if explicit.strip() == (clip_text or "").strip():
        clip_html = read_clipboard_html()
        if clip_html:
            return explicit, clip_html   # same content -> the HTML really is for it
    return explicit, None                # history/selection text -> no matching HTML


def build_markdown(needle_text, html, use_transcript=True,
                   scan_depth=TRANSCRIPT_SCAN_COUNT):
    if use_transcript and needle_text and needle_text.strip():
        recovered = recover_from_transcripts(needle_text, scan_depth)
        if recovered is not None:
            return recovered  # already-clean source markdown
    if html:
        return chars_to_markdown(chars_from_html(html))
    if needle_text:
        return chars_to_markdown(chars_from_plain(needle_text))
    return ""


# ---------------------------------------------------------------------------
# Tests  (run with `paste-reflow.py --test`)
#
# Self-contained stdlib unittest -- the repo has no test runner and the script
# ships as a single file, so the tests live here too. They cover the pure
# transform logic plus the parsing inside the clipboard/transcript I/O (by
# faking subprocess and using temp files), but not the live clipboard itself.
# ---------------------------------------------------------------------------

def _run_tests():
    import unittest
    suite = unittest.defaultTestLoader.loadTestsFromName(__name__)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


try:
    import unittest as _unittest
except ImportError:  # pragma: no cover
    _unittest = None

if _unittest is not None:
    import contextlib
    import tempfile

    @contextlib.contextmanager
    def _patched(obj, name, value):
        """Temporarily set obj.name = value for the duration of the block."""
        sentinel = object()
        old = getattr(obj, name, sentinel)
        setattr(obj, name, value)
        try:
            yield
        finally:
            if old is sentinel:
                delattr(obj, name)
            else:
                setattr(obj, name, old)

    def _fake_run(stdout):
        """A subprocess.run replacement that returns a fixed stdout."""
        def run(*a, **k):
            return types.SimpleNamespace(stdout=stdout)
        return run

    class NormalizeTests(_unittest.TestCase):
        def test_drops_md_chars_lowercases_collapses(self):
            self.assertEqual(_normalize("**Hi**   _There_"), "hi there")

        def test_map_matches_normalize_string(self):
            raw = "A  **bold**\n\nword"
            norm, idx = _normalize_with_map(raw)
            self.assertEqual(norm, _normalize(raw))
            self.assertEqual(len(norm), len(idx))

        def test_index_map_points_at_source(self):
            raw = "x **yz**"
            norm, idx = _normalize_with_map(raw)
            pos = norm.find("yz")
            self.assertEqual(raw[idx[pos]], "y")

        def test_needle_normalization(self):
            self.assertEqual(_normalize_needle("  Foo\n  Bar  "), "foo bar")

    class BalancedTests(_unittest.TestCase):
        def test_marker_pairing(self):
            # * _ ` must pair char-for-char (regression: _balanced once checked
            # only * and `).
            self.assertTrue(_balanced("a *b* `c` _d_"))
            self.assertFalse(_balanced("a _b"))
            self.assertFalse(_balanced("a `b"))
            self.assertFalse(_balanced("a *b"))

        def test_lone_tilde_never_unbalances(self):
            # A lone ~ is literal ("~50"), so it must not reject an otherwise
            # balanced slice; only a dangling ~~ strikethrough run does.
            self.assertTrue(_balanced("about ~50 items"))
            self.assertTrue(_balanced("a ~~struck~~ b"))
            self.assertFalse(_balanced("a ~~struck"))

        def test_intraword_underscore_never_unbalances(self):
            # An intraword _ (work_mem) is literal, not an emphasis delimiter, so
            # an odd number of them must not reject a slice; a flanking _ still
            # has to pair.
            self.assertTrue(_balanced("set work_mem and maintenance_work_mem"))
            self.assertTrue(_balanced("a _emph_ and work_mem"))
            self.assertFalse(_balanced("a _emph and work_mem"))

    class StyleTests(_unittest.TestCase):
        def test_bold_weight(self):
            self.assertIn("bold", _style_from_css("font-weight: bold"))
            self.assertIn("bold", _style_from_css("font-weight:700"))
            self.assertNotIn("bold", _style_from_css("font-weight:400"))

        def test_italic(self):
            self.assertIn("italic", _style_from_css("font-style: italic"))

        def test_color_is_code_but_not_background(self):
            self.assertIn("code", _style_from_css("color:#abc"))
            self.assertNotIn("code", _style_from_css("background-color:#abc"))

    class HtmlReconstructionTests(_unittest.TestCase):
        def test_bold_and_code_spans(self):
            html = ('<span style="font-weight:bold">Bold</span> and '
                    '<span style="color:#abc">code</span> here.')
            self.assertEqual(chars_to_markdown(chars_from_html(html)),
                             "**Bold** and `code` here.")

        def test_br_is_soft_wrap_and_keeps_style(self):
            # A <br> is a TUI line wrap -> collapses to a space, and the bold
            # span survives across it (i.e. the stack isn't corrupted).
            html = ('<span style="font-weight:bold">a<br>b</span>')
            md = chars_to_markdown(chars_from_html(html))
            self.assertEqual(md, "**a b**")

    class ReflowTests(_unittest.TestCase):
        def test_soft_wrap_joins_paragraphs_split(self):
            md = chars_to_markdown(chars_from_plain(
                "This is a soft\nwrapped line.\n\nSecond para.\n"))
            self.assertEqual(md, "This is a soft wrapped line.\n\nSecond para.")

        def test_list_items_keep_their_breaks(self):
            md = chars_to_markdown(chars_from_plain("- one\n- two\n- three\n"))
            self.assertEqual(md, "- one\n- two\n- three")

        def test_strips_tui_indent(self):
            md = chars_to_markdown(chars_from_plain("  indented line\n"))
            self.assertEqual(md, "indented line")

    class TranscriptTests(_unittest.TestCase):
        def _write_transcript(self, msgs):
            d = tempfile.mkdtemp()
            p = Path(d) / "session.jsonl"
            recs = [{"type": "user", "message": {"content": "noise"}}]
            for text in msgs:
                recs.append({"type": "assistant",
                             "message": {"content": [{"type": "text", "text": text}]}})
            p.write_text("\n".join(json.dumps(r) for r in recs))
            return p

        def test_assistant_messages_streams_newest_first(self):
            p = self._write_transcript(["first", "second"])
            self.assertEqual(assistant_messages(p), ["second", "first"])

        def test_recovers_original_markdown(self):
            p = self._write_transcript(["Here is **bold** and `code` to find."])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("bold and code to find")
            self.assertEqual(got, "**bold** and `code` to find")

        def test_short_needle_rejected(self):
            p = self._write_transcript(["short text here"])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                self.assertIsNone(recover_from_transcripts("short"))  # < MIN_MATCH_LEN

        def test_no_match_returns_none(self):
            p = self._write_transcript(["completely different content"])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                self.assertIsNone(recover_from_transcripts("absent needle phrase"))

        def test_recovers_inline_code_with_underscore(self):
            # Regression: a selection whose only divergence from the source is an
            # underscore inside an inline `code` span must still match. Before the
            # fix, the source normalized to `todate` while the TUI needle kept
            # `to_date`, so recovery silently fell through to plain reflow.
            src = "Parsing uses `to_date`/`to_timestamp` on the raw HL7 strings."
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("to_date/to_timestamp on the raw HL7 strings")
            self.assertEqual(got, "`to_date`/`to_timestamp` on the raw HL7 strings")

        def test_recovers_with_lone_tilde(self):
            # Regression: a lone ~ ("~50", approximately) is literal in the TUI,
            # so the needle keeps it and the source markdown does too. Before the
            # fix _normalize stripped every ~ as strikethrough, so the source
            # normalized to "50-100" while the needle had "~50-100" -- one dropped
            # char that broke the whole match and fell back to plain reflow.
            src = "Drop `completionSize` to ~50–100 and lean on the timeout."
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts(
                    "completionSize to ~50–100 and lean on the timeout")
            self.assertEqual(got, "`completionSize` to ~50–100 and lean on the timeout")

        def test_scan_depth_limits_search(self):
            # scan_depth caps how many transcripts recovery looks at. With the
            # needle in the 2nd-most-recent file, depth 1 misses it, depth 2 hits.
            newer = self._write_transcript(["nothing relevant here at all"])
            older = self._write_transcript(["a distinctive findable phrase here"])
            files = [newer, older]  # index 0 == most recent
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n: files[:n]):
                self.assertIsNone(
                    recover_from_transcripts("distinctive findable phrase here", scan_depth=1))
                self.assertEqual(
                    recover_from_transcripts("distinctive findable phrase here", scan_depth=2),
                    "distinctive findable phrase here")

        def test_recovers_intraword_underscore_in_prose(self):
            # Regression: a snake_case identifier in plain prose (no backticks,
            # no fence) -- work_mem -- must still match. Before the fix _normalize
            # stripped the underscore to "workmem" while the TUI needle kept it,
            # breaking recovery of any message mentioning such an identifier.
            src = "spilling to disk (work_mem too small for the data)"
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("work_mem too small for the data")
            self.assertEqual(got, "work_mem too small for the data")

        def test_recovers_fenced_code_block(self):
            # The TUI renders neither the ```python fence nor its info string, and
            # keeps the snake_case underscore literal -- so the needle is just the
            # rendered code. Recovery must return the block WITH its fences.
            src = "Run this:\n\n```python\nfoo_bar = compute_value(x)\n```\n\nDone."
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("foo_bar = compute_value(x)")
            self.assertEqual(got, "```python\nfoo_bar = compute_value(x)\n```")

        def test_recovers_when_needle_includes_fence_label(self):
            # Regression: some TUI renders show the fence's language as a visible
            # label above the block, so it lands in the copied needle ("fish\ncmd").
            # The default normalization drops the info string, so recovery must
            # retry with it emitted -- returning the block WITH its ```fish fence.
            src = "Run it:\n\n```fish\nkubectl get pods\n```\n\nDone."
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("fish\nkubectl get pods")
            self.assertEqual(got, "```fish\nkubectl get pods\n```")

        def test_recovers_without_fence_label_when_absent(self):
            # The complementary case: the same source, but the needle omits the
            # label (the TUI/selection dropped it). Default normalization matches
            # first, so recovery still returns the fenced block.
            src = "Run it:\n\n```fish\nkubectl get pods\n```\n\nDone."
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("kubectl get pods")
            self.assertEqual(got, "```fish\nkubectl get pods\n```")

        def test_recovers_keeps_leading_heading_marker(self):
            # A selection that begins at the start of a heading line keeps its
            # marker -- the user selected the whole line, so the recovered slice
            # should carry it even though the TUI/needle rendered it away. Every
            # heading level h1-h6 is snapped back, not just "##".
            for lvl in range(1, 7):
                src = "#" * lvl + " Title Here\n\nSome body text after."
                p = self._write_transcript([src])
                needle = "Title Here\nSome body text after."  # marker rendered away
                with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                    got = recover_from_transcripts(needle)
                self.assertEqual(got, src)

        def test_recovers_midselection_heading_marker_when_leading_absent(self):
            # A heading NOT at the start of the selection is preserved because the
            # raw slice spans it; only a leading heading relies on the snap. Here
            # the needle starts in prose, so the ## is naturally inside the slice.
            src = "Intro line.\n\n### Sub\n\nTail line."
            p = self._write_transcript([src])
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts("Intro line.\nSub\nTail line.")
            self.assertEqual(got, src)

        def test_recovers_across_midselection_heading(self):
            # Regression: a needle spanning a heading in the MIDDLE of the
            # selection must still match. The TUI drops "## " so the needle has
            # bare "A Heading", but normalize kept the # as literal text, so the
            # source read "## a heading" and alignment broke. The recovered slice
            # is the raw source, heading markers intact.
            src = "Intro para.\n\n## A Heading\n\nBody follows here."
            p = self._write_transcript([src])
            needle = "Intro para.\nA Heading\nBody follows here."  # as TUI renders
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts(needle)
            self.assertEqual(got, src)

        def test_recovers_mixed_fence_labels_in_one_message(self):
            # Regression: two adjacent blocks where the selection kept ONE label
            # (fish) but not the other (sql) -- a recognized language renders
            # highlighted with no visible label, an unrecognized one shows its
            # name. Neither all-off nor all-on matches; recovery must find the
            # per-fence subset that emits only fish, and return the exact source.
            src = "```sql\nSELECT 1\n```\n```fish\nls -a\n```"
            p = self._write_transcript([src])
            needle = "SELECT 1\nfish\nls -a"  # sql label absent, fish label present
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts(needle)
            self.assertEqual(got, src)

        def test_recovers_across_blocks_and_prose(self):
            # A needle spanning code, interleaved prose, and a second code block
            # comes back as the exact source -- both fences intact, prose between.
            src = ("```bash\ncd $MY_DIR && ls\n```\n\nThen:\n"
                   "```bash\necho done\n```")
            p = self._write_transcript([src])
            needle = "cd $MY_DIR && ls\nThen:\necho done"  # as the TUI renders it
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n=3: [p]):
                got = recover_from_transcripts(needle)
            self.assertEqual(got, src)

    class FenceNormalizeTests(_unittest.TestCase):
        def test_fence_lines_and_info_string_drop_out(self):
            # ```bash renders to nothing -- no stray "bash" in the normalized text.
            self.assertEqual(_normalize("a\n```bash\ncode\n```\nb"), "a code b")

        def test_emit_labels_surfaces_opening_fence_label(self):
            # With emit_labels, an OPENING fence's language label is emitted as a
            # word (some blocks show it); the closing fence still emits nothing,
            # and the default (drop) mode is unchanged.
            self.assertEqual(_normalize("a\n```fish\ncode\n```\nb"), "a code b")
            self.assertEqual(_normalize("a\n```fish\ncode\n```\nb", emit_labels=True),
                             "a fish code b")

        def test_emit_labels_is_per_fence(self):
            # A per-fence set emits only the selected opening fences' labels, so a
            # message mixing a shown label with a hidden one can be matched. Here
            # fence 0 (sql) stays hidden and fence 1 (fish) is surfaced.
            raw = "```sql\nSELECT 1\n```\n```fish\nls\n```"
            # (trailing space: the closing fence contributes an inter-line space
            # that _normalize leaves in; _normalize_needle is what strips.)
            self.assertEqual(_normalize(raw, emit_labels=frozenset({1})),
                             "select 1 fish ls ")
            self.assertEqual(_normalize(raw, emit_labels=frozenset({0})),
                             "sql select 1 ls ")

        def test_md_chars_kept_inside_fence(self):
            # Inside a fence, _ * ~ ` are literal code, not markup.
            self.assertIn("foo_bar", _normalize("```\nfoo_bar\n```"))
            # ...but stripped in prose, as before.
            self.assertEqual(_normalize("**hi**"), "hi")

        def test_md_chars_kept_inside_inline_code(self):
            # The TUI renders inline `to_date` with its underscore visible, so the
            # needle keeps it; the normalized source must too (backticks dropped,
            # underscore kept) or recovery misses snake_case identifiers.
            self.assertEqual(_normalize("call `to_date`/`to_timestamp` now"),
                             "call to_date/to_timestamp now")
            # Emphasis outside code is still stripped; markers inside are literal.
            self.assertEqual(_normalize("a `b_c` **d** _e_"), "a b_c d e")

        def test_inline_code_state_resets_each_line(self):
            # A lone backtick doesn't swallow the next line's emphasis markup.
            self.assertEqual(_normalize("a `b\n_c_ d"), "a b c d")

        def test_lone_tilde_kept_but_strikethrough_dropped(self):
            # A lone ~ is literal ("~50"); the TUI shows it, so we keep it. A
            # ~~pair~~ IS strikethrough markup the TUI strips.
            self.assertEqual(_normalize("about ~50 items"), "about ~50 items")
            self.assertEqual(_normalize("a ~~struck~~ b"), "a struck b")
            # Inside a fence tildes are literal code regardless of pairing.
            self.assertEqual(_normalize("a\n```\n~~x~~\n```\nb"), "a ~~x~~ b")

        def test_intraword_underscore_kept_flanking_stripped(self):
            # An intraword underscore (work_mem, snake_case) is literal in
            # CommonMark, so the TUI shows it and the needle keeps it -- the
            # normalized source must too, even in plain prose with no backticks.
            # A flanking _ is still emphasis the TUI strips.
            self.assertEqual(_normalize("set work_mem too small"),
                             "set work_mem too small")
            self.assertEqual(_normalize("maintenance_work_mem and shared_buffers"),
                             "maintenance_work_mem and shared_buffers")
            self.assertEqual(_normalize("a _emph_ word"), "a emph word")
            # A digit_digit underscore is literal too (e.g. "1_000").
            self.assertEqual(_normalize("value 1_000 here"), "value 1_000 here")

        def test_map_matches_normalize_with_intraword_underscore(self):
            raw = "set work_mem now"
            norm, idx = _normalize_with_map(raw)
            self.assertEqual(norm, _normalize(raw))
            self.assertEqual(len(norm), len(idx))
            self.assertEqual(raw[idx[norm.find("work_mem")]], "w")

        def test_map_matches_normalize_with_inline_code(self):
            raw = "run `a_b` then"
            norm, idx = _normalize_with_map(raw)
            self.assertEqual(norm, _normalize(raw))
            self.assertEqual(len(norm), len(idx))
            self.assertEqual(raw[idx[norm.find("a_b")]], "a")

        def test_map_matches_normalize_with_fences(self):
            raw = "x\n```py\na_b = 1\n```\ny"
            norm, idx = _normalize_with_map(raw)
            self.assertEqual(norm, _normalize(raw))
            self.assertEqual(len(norm), len(idx))
            self.assertEqual(raw[idx[norm.find("a_b")]], "a")

        def test_atx_heading_markers_stripped(self):
            # "## Foo" renders as "Foo" in the TUI, so the markers -- leading run
            # and any closing run -- drop out of the normalized text. Every level
            # h1-h6 is handled (the # run is 1-6 long).
            self.assertEqual(_normalize("## Where the text"), "where the text")
            self.assertEqual(_normalize("# Title ##"), "title")
            self.assertEqual(_normalize("a\n\n### Heading\n\nb"), "a heading b")
            for lvl in range(1, 7):
                self.assertEqual(_normalize("#" * lvl + " Heading"), "heading")

        def test_hash_not_a_heading_is_literal(self):
            # "#tag" (no space after the #) is literal text, not a heading.
            self.assertEqual(_normalize("#tag stays"), "#tag stays")
            # 7+ hashes isn't a valid ATX heading either.
            self.assertEqual(_normalize("####### seven"), "####### seven")
            # A '#' inside a fence is a literal comment, never a heading.
            # (Trailing space: the closing fence leaves an inter-line space that
            # _normalize keeps; _normalize_needle is what strips.)
            self.assertEqual(_normalize("```\n# comment\ncode\n```"), "# comment code ")

        def test_map_matches_normalize_with_heading(self):
            raw = "## Big Title\n\nbody text"
            norm, idx = _normalize_with_map(raw)
            self.assertEqual(norm, _normalize(raw))
            self.assertEqual(len(norm), len(idx))
            # The first normalized char maps to "B" of Title, past the "## ".
            self.assertEqual(raw[idx[0]], "B")

        def test_labeled_fence_ordinals(self):
            # Only opening fences with a non-empty info string count, in doc
            # order: here fence 0 (sql) and fence 2 (fish) are labeled; fence 1
            # (bare ```) is not.
            raw = "```sql\na\n```\n```\nb\n```\n```fish\nc\n```"
            self.assertEqual(_labeled_fence_ordinals(raw), [0, 2])

        def test_fence_blocks_and_snap(self):
            raw = "```\nABCDE\n```"  # block spans the whole string
            blocks = _fence_blocks(raw)
            self.assertEqual(len(blocks), 1)
            # A boundary inside the content widens out to the full block.
            inner = raw.index("ABCDE")
            self.assertEqual(_snap_to_fences(inner, inner + 3, blocks), (0, len(raw)))

    class ClipboardParseTests(_unittest.TestCase):
        def test_html_hex_decodes(self):
            payload = "<b>hi</b>".encode("utf-8").hex().upper()
            out = f"«data HTML{payload}»"
            with _patched(subprocess, "run", _fake_run(out)):
                self.assertEqual(read_clipboard_html(), "<b>hi</b>")

        def test_html_hex_survives_line_wrapping(self):
            # Regression: osascript wraps long output; the hex run gets split by
            # whitespace and must still decode.
            payload = "<b>hi</b>".encode("utf-8").hex().upper()
            wrapped = "«data HTML" + payload[:4] + "\n  " + payload[4:] + "»"
            with _patched(subprocess, "run", _fake_run(wrapped)):
                self.assertEqual(read_clipboard_html(), "<b>hi</b>")

        def test_no_html_returns_none(self):
            with _patched(subprocess, "run", _fake_run("«class TEXT»")):
                self.assertIsNone(read_clipboard_html())

    class AcquireTests(_unittest.TestCase):
        def _args(self, **kw):
            defaults = {"html_file": None, "text": None}
            defaults.update(kw)
            return types.SimpleNamespace(**defaults)

        def test_history_path_skips_osascript(self):
            # Regression: read_clipboard_html (slow osascript) must not run when
            # explicit text doesn't match the clipboard.
            calls = {"html": 0}

            def counting_html():
                calls["html"] += 1
                return "<b>x</b>"

            with _patched(sys.modules[__name__], "read_clipboard_text", lambda: "different"), \
                 _patched(sys.modules[__name__], "read_clipboard_html", counting_html):
                needle, html = acquire(self._args(text="explicit text input here"))
            self.assertEqual(needle, "explicit text input here")
            self.assertIsNone(html)
            self.assertEqual(calls["html"], 0)

        def test_matching_clipboard_keeps_html(self):
            with _patched(sys.modules[__name__], "read_clipboard_text", lambda: "same text"), \
                 _patched(sys.modules[__name__], "read_clipboard_html", lambda: "<b>same</b>"):
                needle, html = acquire(self._args(text="same text"))
            self.assertEqual((needle, html), ("same text", "<b>same</b>"))

    class BuildMarkdownTests(_unittest.TestCase):
        def test_transcript_takes_priority(self):
            with _patched(sys.modules[__name__], "recover_from_transcripts",
                          lambda t, scan_depth=TRANSCRIPT_SCAN_COUNT: "RECOVERED"):
                self.assertEqual(build_markdown("needle", "<b>x</b>"), "RECOVERED")

        def test_html_fallback_when_no_transcript(self):
            self.assertEqual(
                build_markdown("Bold here.", '<span style="font-weight:bold">Bold</span> here.',
                               use_transcript=False),
                "**Bold** here.")

        def test_plain_fallback(self):
            self.assertEqual(build_markdown("plain words", None, use_transcript=False),
                             "plain words")

    class QuoteTests(_unittest.TestCase):
        def test_callout_wrapping(self):
            self.assertEqual(to_quote("a\n\nb"), "> [!quote]\n> a\n>\n> b")


def main():
    ap = argparse.ArgumentParser(description="Reformat copied Claude Code output to markdown.")
    ap.add_argument("text", nargs="?", help="explicit plain-text input (else stdin, else live clipboard)")
    ap.add_argument("--quote", action="store_true", help="wrap as an Obsidian > [!quote] callout")
    ap.add_argument("--no-transcript", action="store_true", help="skip A3 transcript recovery")
    ap.add_argument("--scan-depth", type=int, default=TRANSCRIPT_SCAN_COUNT, metavar="N",
                    help="how many recent transcripts to search for a match "
                         f"(default {TRANSCRIPT_SCAN_COUNT}); raise to dig out older sessions")
    ap.add_argument("--html-file", help="read the HTML flavor from a file (testing)")
    ap.add_argument("--test", action="store_true", help="run the built-in unit tests and exit")
    args = ap.parse_args()

    if args.test:
        sys.exit(_run_tests())

    needle_text, html = acquire(args)
    md = build_markdown(needle_text, html, use_transcript=not args.no_transcript,
                        scan_depth=args.scan_depth)
    if not md:
        sys.stderr.write("paste-reflow: nothing to reformat\n")
        sys.exit(1)
    if args.quote:
        md = to_quote(md)
    sys.stdout.write(md)


if __name__ == "__main__":
    main()
