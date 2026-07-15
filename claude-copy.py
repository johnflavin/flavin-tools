#!/usr/bin/env python3
"""Recover clean source markdown from a Claude Code TUI selection.

You copy some text out of the Claude Code TUI (in Ghostty) to paste into
Obsidian, and you get a garbled mess: every line prefixed with two spaces,
paragraphs hard-wrapped into a pile of newlines, and all the inline markup
(bold, `code`, headings, fences) flattened away by the renderer. This turns
that back into the markdown Claude actually emitted.

Pipeline:

  1. Acquire input -- an explicit string (argv/stdin, e.g. from an Alfred
     Universal Action on a clipboard-history entry) or, by default, the live
     clipboard's plain text.

  2. Transcript recovery (high fidelity). Treat the copied text as a search
     needle against recent Claude Code session transcripts (~/.claude/projects/
     */*.jsonl). On a confident match we return the *original* source markdown --
     real backticks, links, code fences, headings, the lot.

  3. Plain reflow (fallback). No confident match (content not from a recent
     session, or copied from somewhere else)? Just clean up the plain text:
     strip the TUI's 2-space indent, join soft-wrapped lines, keep paragraph and
     list breaks.

The matcher is deliberately markup-agnostic. Rather than enumerate every way
markdown markers can differ between the rendered TUI text and the raw source
(bold, italic, code, strikethrough, intraword underscores, fence language
labels, headings, ...), it reduces BOTH sides to their alphanumeric skeleton --
letters and digits only -- so every marker, all whitespace, the soft-wrapping,
and the indent simply vanish, uniformly, with no per-marker code. It fuzzy-
aligns the skeletons (stdlib difflib) to find where the selection begins and
ends in the raw source, expands those two boundaries outward to swallow leading
`##`/`**`/opening-fence and trailing punctuation/fence, and returns the raw
slice between them verbatim. The middle never has to line up character for
character, so a stray marker there can't break the match.

Pure stdlib -- no dependencies -- so it runs under whatever python3 Alfred
resolves. Clipboard access is isolated in read_clipboard_text().
"""

import argparse
import difflib
import heapq
import json
import os
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

# A code-fence delimiter line: optional indent, 3+ backticks/tildes, then an
# optional info string (e.g. ```bash). Used to widen a boundary that lands
# inside a block out to the whole block, so a recovered slice never has a
# dangling fence.
FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*$")

# The leading marker of an ATX heading: up to 3 spaces of indent then 1-6 `#`.
# It's only a heading if whitespace (or end of line) follows the # run.
HEADING_HASHES = re.compile(r"[ \t]{0,3}#{1,6}")

# Inline markdown markers we pull back in at a slice boundary so we don't cut
# through the middle of a **bold** or `code` span.
INLINE_MD_CHARS = set("*`_~")

# How many of the most-recently-touched transcripts to search by default.
# Transcripts are streamed and short-circuited, so scanning more is cheap;
# --scan-depth overrides (raise it to dig out an older session).
TRANSCRIPT_SCAN_COUNT = 10

# Don't trust a match whose alphanumeric skeleton is shorter than this -- too
# little signal, too easy to false-positive.
MIN_SKELETON_LEN = 8

# Probe windows for the cheap pre-filter that finds the candidate message
# before paying for difflib: PROBE_COUNT windows of PROBE_WIDTH skeleton chars,
# spread across the needle. A message qualifies as a candidate when it contains
# enough of them (see _needed_probe_hits) as exact substrings -- robust because
# a stray fence label can break at most the probe it falls in.
PROBE_COUNT = 6
PROBE_WIDTH = 24

# Minimum fraction of the needle skeleton that must align (difflib matched chars
# / needle length) to accept a match. A true selection embeds almost entirely in
# its source -- the only misses are things the source genuinely lacks -- so this
# sits high; it mostly rejects a wrong message that happens to share some probes.
MIN_RATIO = 0.90


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


# ---------------------------------------------------------------------------
# Transcript enumeration
# ---------------------------------------------------------------------------

def recent_transcripts(n=TRANSCRIPT_SCAN_COUNT):
    """The n most-recently-modified transcript files, newest first.

    Ranking by mtime means we must stat every file -- there's no cheaper way to
    learn recency (directory mtimes don't track appends to existing files). But
    heapq.nlargest streams the glob and keeps only an n-sized heap, so we avoid
    materializing and fully sorting the whole (ever-growing) list."""
    base = Path.home() / ".claude" / "projects"

    def mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return -1.0

    return heapq.nlargest(n, base.glob("*/*.jsonl"), key=mtime)


def _reversed_lines(f, chunk_size=1 << 16):
    """Yield a binary file's newline-separated lines from last to first, reading
    backward one chunk at a time so a caller that stops early never touches the
    front of a many-MB file. Splitting on b'\\n' is UTF-8-safe -- 0x0A never
    appears inside a multi-byte codepoint -- so each yielded line decodes on its
    own. Lines have no trailing newline; a final blank line yields b''."""
    f.seek(0, os.SEEK_END)
    pos = f.tell()
    tail = b""  # the not-yet-complete left fragment carried across chunks
    while pos > 0:
        step = min(chunk_size, pos)
        pos -= step
        f.seek(pos)
        buf = f.read(step) + tail
        parts = buf.split(b"\n")
        tail = parts[0]  # extends further left; hold until the next chunk
        for piece in reversed(parts[1:]):
            yield piece
    yield tail


def assistant_messages(path):
    """Yield the markdown of each assistant text block, newest first.

    A generator: it reads the transcript backward (see _reversed_lines) and
    parses one line at a time, so a caller matching against the newest message --
    the common case -- never reads or json.loads the rest of the file. Skips the
    cheap way past non-assistant lines before paying for json.loads (most of a
    session is user/tool_result/tool_use entries)."""
    try:
        f = open(path, "rb")
    except OSError:
        return
    with f:
        for raw_line in _reversed_lines(f):
            if b'"assistant"' not in raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except ValueError:
                continue
            if obj.get("type") != "assistant":
                continue
            texts = [b["text"] for b in obj.get("message", {}).get("content", []) or []
                     if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
            for text in reversed(texts):  # last block of the message is newest
                yield text


# ---------------------------------------------------------------------------
# Transcript recovery -- skeleton + fuzzy-anchor
# ---------------------------------------------------------------------------

def _skeleton(raw, want_map=False):
    """The alphanumeric skeleton of `raw`: letters and digits only, lowercased.

    Everything else -- markdown markers, whitespace, punctuation, fences,
    headings -- drops out. That's the whole trick: the TUI-rendered text and the
    raw source differ almost entirely in that discarded material, so their
    skeletons line up without us knowing what any marker means.

    With want_map, also returns index_map where index_map[i] is the offset in
    `raw` that produced skeleton char i (used to map a match back to raw)."""
    keep = []
    idx = [] if want_map else None
    for i, ch in enumerate(raw):
        if ch.isalnum():
            keep.append(ch.lower())
            if want_map:
                idx.append(i)
    text = "".join(keep)
    return (text, idx) if want_map else text


def _probes(nskel):
    """PROBE_COUNT skeleton windows of PROBE_WIDTH chars, spread across the
    needle (deduped by start offset). Short needles yield a single probe (the
    whole skeleton). Used only for the cheap candidate pre-filter."""
    length = len(nskel)
    if length <= PROBE_WIDTH:
        return [nskel]
    step = (length - PROBE_WIDTH) / (PROBE_COUNT - 1)
    seen, ps = set(), []
    for t in range(PROBE_COUNT):
        start = int(t * step)
        if start not in seen:
            seen.add(start)
            ps.append(nskel[start:start + PROBE_WIDTH])
    return ps


def _needed_probe_hits(probe_count):
    """How many probes a message must contain to earn a difflib pass. Two for a
    real (multi-probe) needle -- selective, and robust to a label breaking one --
    but one for a short needle that only produced a single probe."""
    return 2 if probe_count >= 3 else 1


def _anchor_span(nskel, sskel, probe_hits):
    """Fuzzy-align the needle skeleton within a source skeleton and return
    (start, end, ratio) in source-skeleton coordinates, or None.

    difflib gives the matching blocks between the two; the first and last blocks
    bracket where the needle sits in the source, and a stray label the source
    has but the needle doesn't is just a skipped gap between blocks. We bound the
    difflib input to a window around the probe hits so cost stays ~O(needle)."""
    lo = max(0, min(probe_hits) - len(nskel))
    hi = min(len(sskel), max(probe_hits) + len(nskel) + PROBE_WIDTH)
    window = sskel[lo:hi]
    sm = difflib.SequenceMatcher(None, nskel, window, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return None
    first, last = blocks[0], blocks[-1]
    matched = sum(b.size for b in blocks)
    # Map the needle's first/last char into the window, allowing for a few
    # unmatched needle chars hanging off either end of the outermost blocks.
    start = lo + max(0, first.b - first.a)
    end = lo + min(len(window), last.b + last.size + (len(nskel) - (last.a + last.size)))
    return start, end, matched / len(nskel)


def _fence_blocks(raw):
    """Char ranges (open_start, close_end) of complete fenced blocks in `raw`.

    open_start is the offset of the opening fence line; close_end is the offset
    just past the closing fence line. An unterminated fence runs to end-of-text.
    Used to snap a boundary that lands inside a block out to the whole block."""
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


def _expand_start(start, raw, lead, blocks):
    """Widen the start boundary leftward to recover markup the skeleton dropped.

    In priority order: an enclosing code fence (take the whole block), a leading
    ATX heading marker on the same line ("## "), then the needle's own leading
    punctuation (`lead`, e.g. a "- " list marker) consumed in reverse while
    skipping markdown markers the TUI rendered away (a `**`/`` ` `` at the edge)."""
    for bs, be in blocks:
        if bs <= start < be:
            return bs
    line_start = raw.rfind("\n", 0, start) + 1
    hm = HEADING_HASHES.match(raw, line_start, start)
    if hm and hm.end() < start and raw[hm.end()] in " \t":
        j = hm.end()
        while j < start and raw[j] in " \t":
            j += 1
        if j == start:  # everything before `start` on this line is the marker
            return line_start
    li = len(lead) - 1
    while start > 0:
        ch = raw[start - 1]
        if li >= 0 and ch == lead[li]:
            start -= 1
            li -= 1
        elif ch in INLINE_MD_CHARS:
            start -= 1
        else:
            break
    return start


def _expand_end(end, raw, tail, blocks):
    """Widen the end boundary rightward: an enclosing fence (take the whole
    block), else the needle's trailing punctuation (`tail`, e.g. ".") consumed
    while skipping markdown markers (a closing `` ` ``/`**` the TUI dropped)."""
    for bs, be in blocks:
        if bs < end <= be:
            return be
    ti = 0
    while end < len(raw):
        ch = raw[end]
        if ti < len(tail) and ch == tail[ti]:
            end += 1
            ti += 1
        elif ch in INLINE_MD_CHARS:
            end += 1
        else:
            break
    return end


def recover_from_transcripts(needle_text, scan_depth=TRANSCRIPT_SCAN_COUNT):
    """Find the needle in recent transcripts and return the exact source
    markdown slice, or None if there's no confident match.

    scan_depth caps how many of the most-recently-touched transcripts to search
    (default TRANSCRIPT_SCAN_COUNT); raise it to dig content out of an older
    session."""
    nnorm = re.sub(r"\s+", " ", needle_text).strip()
    nskel = _skeleton(nnorm)
    if len(nskel) < MIN_SKELETON_LEN:
        return None
    # The needle's leading/trailing punctuation fringe -- markup outside the
    # first/last alphanumeric char that a boundary expansion should recover.
    first = next((i for i, c in enumerate(nnorm) if c.isalnum()), 0)
    last = next((i for i in range(len(nnorm) - 1, -1, -1) if nnorm[i].isalnum()), len(nnorm) - 1)
    lead, tail = nnorm[:first], nnorm[last + 1:]

    probes = _probes(nskel)
    need = _needed_probe_hits(len(probes))
    best = None
    for path in recent_transcripts(scan_depth):
        for raw in assistant_messages(path):
            sskel = _skeleton(raw)
            hits = [pos for pos in (sskel.find(p) for p in probes) if pos >= 0]
            if len(hits) < need:
                continue
            span = _anchor_span(nskel, sskel, hits)
            if span is None:
                continue
            s0, e0, ratio = span
            if ratio < MIN_RATIO:
                continue
            _, sidx = _skeleton(raw, want_map=True)  # build the map only on a hit
            blocks = _fence_blocks(raw)
            start = _expand_start(sidx[s0], raw, lead, blocks)
            end = _expand_end(sidx[e0 - 1] + 1, raw, tail, blocks)
            slice_ = raw[start:end].strip()
            if not slice_:
                continue
            if best is None or ratio > best[0]:
                best = (ratio, slice_)
            if ratio >= 0.999:  # a near-perfect embed won't be beaten; stop here
                return slice_
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Plain reflow (fallback)
# ---------------------------------------------------------------------------

def _strip_indent(line):
    """Remove the TUI's leading 2-space response indent (1 or 2 spaces)."""
    removed = 0
    while removed < 2 and line[:1] == " ":
        line = line[1:]
        removed += 1
    return line


def reflow(text):
    """Clean up plain TUI text: strip the 2-space indent, join soft-wrapped
    lines into one, and preserve paragraph breaks (blank lines) and list-item
    breaks."""
    parts = []          # output fragments, joined at the end
    pending_para = False  # a blank line was seen -> next content starts a paragraph
    have_content = False
    for physical in text.split("\n"):
        line = _strip_indent(physical)
        if line.strip() == "":
            if have_content:
                pending_para = True
            continue
        if not parts:
            parts.append(line)
        elif pending_para:
            parts.append("\n\n" + line)
        elif LIST_MARKER.match(line):
            parts.append("\n" + line)
        else:  # soft wrap -> a single space, unless one already abuts the seam
            sep = "" if parts[-1].endswith(" ") or line[:1] == " " else " "
            parts.append(sep + line)
        pending_para = False
        have_content = True
    return "".join(parts).strip()


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
    """Return the needle text: an explicit argv/stdin string if given, else the
    live clipboard."""
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            return piped
    return read_clipboard_text()


def build_markdown(needle_text, use_transcript=True,
                   scan_depth=TRANSCRIPT_SCAN_COUNT):
    if use_transcript and needle_text and needle_text.strip():
        recovered = recover_from_transcripts(needle_text, scan_depth)
        if recovered is not None:
            return recovered  # already-clean source markdown
    if needle_text:
        return reflow(needle_text)
    return ""


# ---------------------------------------------------------------------------
# Tests  (run with `claude-copy.py --test`)
#
# Self-contained stdlib unittest -- the repo has no test runner and the script
# ships as a single file, so the tests live here too. They cover the pure
# transform logic plus the parsing inside the transcript/clipboard I/O (by
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

    class SkeletonTests(_unittest.TestCase):
        def test_keeps_only_alphanumerics_lowercased(self):
            self.assertEqual(_skeleton("**Hi**, `to_date`!  #Heading"),
                             "hitodateheading")

        def test_map_points_back_at_source(self):
            raw = "a **Bold** c"
            skel, idx = _skeleton(raw, want_map=True)
            self.assertEqual(skel, _skeleton(raw))
            self.assertEqual(len(skel), len(idx))
            self.assertEqual(raw[idx[skel.find("bold")]], "B")

        def test_probes_span_and_dedupe(self):
            skel = _skeleton("x" * 200)
            ps = _probes(skel)
            self.assertTrue(all(len(p) == PROBE_WIDTH for p in ps))
            self.assertLessEqual(len(ps), PROBE_COUNT)

        def test_short_needle_single_probe(self):
            self.assertEqual(_probes("abcdef"), ["abcdef"])
            self.assertEqual(_needed_probe_hits(1), 1)
            self.assertEqual(_needed_probe_hits(6), 2)

    class ReflowTests(_unittest.TestCase):
        def test_soft_wrap_joins_paragraphs_split(self):
            self.assertEqual(
                reflow("This is a soft\nwrapped line.\n\nSecond para.\n"),
                "This is a soft wrapped line.\n\nSecond para.")

        def test_list_items_keep_their_breaks(self):
            self.assertEqual(reflow("- one\n- two\n- three\n"),
                             "- one\n- two\n- three")

        def test_strips_tui_indent(self):
            self.assertEqual(reflow("  indented line\n"), "indented line")

    class QuoteTests(_unittest.TestCase):
        def test_callout_wrapping(self):
            self.assertEqual(to_quote("a\n\nb"), "> [!quote]\n> a\n>\n> b")

    class FenceBlockTests(_unittest.TestCase):
        def test_fence_block_ranges(self):
            raw = "a\n```py\ncode\n```\nb"
            blocks = _fence_blocks(raw)
            self.assertEqual(len(blocks), 1)
            bs, be = blocks[0]
            self.assertEqual(raw[bs:be], "```py\ncode\n```")

        def test_unterminated_fence_runs_to_end(self):
            raw = "```\nstuff to the end"
            self.assertEqual(_fence_blocks(raw), [(0, len(raw))])

    class ReversedLinesTests(_unittest.TestCase):
        def _rev(self, data, chunk_size):
            import io
            return [b.decode() for b in _reversed_lines(io.BytesIO(data), chunk_size)]

        def test_no_trailing_newline(self):
            # Small chunk forces multi-chunk reassembly across boundaries.
            self.assertEqual(self._rev(b"AB\nCD\nEF", 3), ["EF", "CD", "AB"])

        def test_trailing_newline_yields_blank_first(self):
            self.assertEqual(self._rev(b"AB\nCD\n", 3), ["", "CD", "AB"])

        def test_single_line(self):
            self.assertEqual(self._rev(b"only line", 4), ["only line"])

        def test_matches_forward_split_reversed(self):
            data = ("some\nlonger\nmultiline\ncontent\nhere" * 3).encode()
            for cs in (1, 4, 7, 4096):
                self.assertEqual(self._rev(data, cs),
                                 list(reversed(data.decode().split("\n"))))

    class ClipboardTests(_unittest.TestCase):
        def test_reads_pbpaste_stdout(self):
            with _patched(subprocess, "run", _fake_run("clip contents")):
                self.assertEqual(read_clipboard_text(), "clip contents")

    class AcquireTests(_unittest.TestCase):
        def _args(self, **kw):
            defaults = {"text": None}
            defaults.update(kw)
            return types.SimpleNamespace(**defaults)

        def test_explicit_text_wins(self):
            self.assertEqual(acquire(self._args(text="explicit")), "explicit")

        def test_falls_back_to_clipboard(self):
            with _patched(sys.modules[__name__], "read_clipboard_text", lambda: "from clip"):
                # stdin is a tty in the test runner, so no piped input is read.
                self.assertEqual(acquire(self._args()), "from clip")

    class BuildMarkdownTests(_unittest.TestCase):
        def test_transcript_takes_priority(self):
            with _patched(sys.modules[__name__], "recover_from_transcripts",
                          lambda t, scan_depth=TRANSCRIPT_SCAN_COUNT: "RECOVERED"):
                self.assertEqual(build_markdown("needle here"), "RECOVERED")

        def test_reflow_fallback_when_no_match(self):
            with _patched(sys.modules[__name__], "recover_from_transcripts",
                          lambda t, scan_depth=TRANSCRIPT_SCAN_COUNT: None):
                self.assertEqual(build_markdown("  soft\n  wrap\n"), "soft wrap")

    class RecoveryTests(_unittest.TestCase):
        def _write_transcript(self, msgs):
            d = tempfile.mkdtemp()
            p = Path(d) / "session.jsonl"
            recs = [{"type": "user", "message": {"content": "noise"}}]
            for text in msgs:
                recs.append({"type": "assistant",
                             "message": {"content": [{"type": "text", "text": text}]}})
            p.write_text("\n".join(json.dumps(r) for r in recs))
            return p

        def _recover(self, msgs, needle, **kw):
            p = self._write_transcript(msgs)
            with _patched(sys.modules[__name__], "recent_transcripts",
                          lambda n=TRANSCRIPT_SCAN_COUNT: [p]):
                return recover_from_transcripts(needle, **kw)

        def test_assistant_messages_streams_newest_first(self):
            p = self._write_transcript(["first", "second"])
            self.assertEqual(list(assistant_messages(p)), ["second", "first"])

        def test_assistant_messages_is_lazy(self):
            # It's a generator, so a caller can stop after the newest message
            # without the rest being parsed. Taking one item must yield "newest".
            p = self._write_transcript(["oldest", "newest"])
            gen = assistant_messages(p)
            self.assertEqual(next(gen), "newest")
            gen.close()

        def test_short_needle_rejected(self):
            self.assertIsNone(self._recover(["short text here"], "short"))

        def test_no_match_returns_none(self):
            self.assertIsNone(self._recover(["completely different content"],
                                            "absent needle phrase entirely"))

        def test_recovers_bold_and_inline_code(self):
            src = "Here is **bold** and `code` to find in the text."
            # Needle ends at "text" (no period selected) -> slice stops there too.
            self.assertEqual(self._recover([src], "bold and code to find in the text"),
                             "**bold** and `code` to find in the text")

        def test_recovers_inline_code_with_underscore(self):
            # snake_case inside inline code -- handled with no underscore logic.
            src = "Parsing uses `to_date`/`to_timestamp` on the raw HL7 strings."
            self.assertEqual(
                self._recover([src], "to_date/to_timestamp on the raw HL7 strings"),
                "`to_date`/`to_timestamp` on the raw HL7 strings")

        def test_recovers_intraword_underscore_in_prose(self):
            src = "spilling to disk (work_mem too small for the data)"
            self.assertEqual(self._recover([src], "work_mem too small for the data"),
                             "work_mem too small for the data")

        def test_recovers_with_lone_tilde(self):
            src = "Drop `completionSize` to ~50–100 and lean on the timeout."
            self.assertEqual(
                self._recover([src], "completionSize to ~50–100 and lean on the timeout"),
                "`completionSize` to ~50–100 and lean on the timeout")

        def test_recovers_fenced_code_block(self):
            src = "Run this:\n\n```python\nfoo_bar = compute_value(x)\n```\n\nDone."
            self.assertEqual(self._recover([src], "foo_bar = compute_value(x)"),
                             "```python\nfoo_bar = compute_value(x)\n```")

        def test_recovers_when_needle_includes_fence_label(self):
            # A block whose language label was copied ("fish\ncmd"): the label is
            # in the source skeleton, and difflib skips it as a gap if the needle
            # lacks it or matches it if present -- either way the block comes back.
            src = "Run it:\n\n```fish\nkubectl get pods\n```\n\nDone."
            self.assertEqual(self._recover([src], "fish\nkubectl get pods"),
                             "```fish\nkubectl get pods\n```")
            self.assertEqual(self._recover([src], "kubectl get pods"),
                             "```fish\nkubectl get pods\n```")

        def test_recovers_mixed_fence_labels_in_one_message(self):
            # Two blocks, only one label copied -- no special handling needed.
            src = "```sql\nSELECT 1\n```\n```fish\nls -a\n```"
            self.assertEqual(self._recover([src], "SELECT 1\nfish\nls -a"), src)

        def test_recovers_keeps_leading_heading_marker(self):
            # A selection beginning at a heading keeps its marker, every level.
            for lvl in range(1, 7):
                src = "#" * lvl + " Title Here\n\nSome body text after."
                self.assertEqual(
                    self._recover([src], "Title Here\nSome body text after."), src)

        def test_recovers_across_midselection_heading(self):
            src = "Intro para.\n\n## A Heading\n\nBody follows here."
            self.assertEqual(
                self._recover([src], "Intro para.\nA Heading\nBody follows here."), src)

        def test_keeps_trailing_punctuation(self):
            # The alnum skeleton ends at the last letter; the fringe sync pulls
            # back the trailing punctuation the selection included.
            src = 'End with the `ApplicationError("no data")`.'
            self.assertEqual(self._recover([src], 'End with the ApplicationError("no data").'),
                             'End with the `ApplicationError("no data")`.')

        def test_keeps_leading_list_marker(self):
            src = "Intro.\n\n- alpha item here\n- beta item here\n\nEnd."
            self.assertEqual(self._recover([src], "- alpha item here\n- beta item here"),
                             "- alpha item here\n- beta item here")

        def test_bold_span_at_selection_end(self):
            src = "Here is **important stuff** you want."
            self.assertEqual(self._recover([src], "important stuff"), "**important stuff**")

        def test_scan_depth_limits_search(self):
            # scan_depth caps how many transcripts recovery looks at. With the
            # needle in the 2nd-most-recent file, depth 1 misses it, depth 2 hits.
            newer = self._write_transcript(["nothing relevant here at all today"])
            older = self._write_transcript(["distinctive findable phrase here now"])
            files = [newer, older]  # index 0 == most recent
            needle = "distinctive findable phrase here now"
            with _patched(sys.modules[__name__], "recent_transcripts", lambda n: files[:n]):
                self.assertIsNone(recover_from_transcripts(needle, scan_depth=1))
                self.assertEqual(recover_from_transcripts(needle, scan_depth=2), needle)


def main():
    ap = argparse.ArgumentParser(
        description="Recover clean source markdown from a Claude Code TUI selection.")
    ap.add_argument("text", nargs="?", help="explicit plain-text input (else stdin, else live clipboard)")
    ap.add_argument("--quote", action="store_true", help="wrap as an Obsidian > [!quote] callout")
    ap.add_argument("--no-transcript", action="store_true", help="skip transcript recovery")
    ap.add_argument("--scan-depth", type=int, default=TRANSCRIPT_SCAN_COUNT, metavar="N",
                    help="how many recent transcripts to search for a match "
                         f"(default {TRANSCRIPT_SCAN_COUNT}); raise to dig out older sessions")
    ap.add_argument("--test", action="store_true", help="run the built-in unit tests and exit")
    args = ap.parse_args()

    if args.test:
        sys.exit(_run_tests())

    needle_text = acquire(args)
    md = build_markdown(needle_text, use_transcript=not args.no_transcript,
                        scan_depth=args.scan_depth)
    if not md:
        sys.stderr.write("claude-copy: nothing to reformat\n")
        sys.exit(1)
    if args.quote:
        md = to_quote(md)
    sys.stdout.write(md)


if __name__ == "__main__":
    main()
