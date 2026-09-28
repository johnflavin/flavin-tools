//! Recover clean source markdown from a Claude Code TUI selection.
//!
//! You copy some text out of the Claude Code TUI (in Ghostty) to paste into
//! Obsidian, and you get a garbled mess: every line prefixed with two spaces,
//! paragraphs hard-wrapped into a pile of newlines, and all the inline markup
//! (bold, `code`, headings, fences) flattened away by the renderer. This turns
//! that back into the markdown Claude actually emitted.
//!
//! Pipeline:
//!
//!   1. Acquire input -- an explicit string (argv/stdin, e.g. from an Alfred
//!      Universal Action on a clipboard-history entry) or, by default, the live
//!      clipboard's plain text.
//!
//!   2. Transcript recovery (high fidelity). Treat the copied text as a search
//!      needle against recent Claude Code session transcripts (~/.claude/projects/
//!      */*.jsonl). On a confident match we return the *original* source markdown --
//!      real backticks, links, code fences, headings, the lot.
//!
//!   3. Plain reflow (fallback). No confident match (content not from a recent
//!      session, or copied from somewhere else)? Just clean up the plain text:
//!      strip the TUI's 2-space indent, join soft-wrapped lines, keep paragraph and
//!      list breaks.
//!
//! The matcher is deliberately markup-agnostic. Rather than enumerate every way
//! markdown markers can differ between the rendered TUI text and the raw source
//! (bold, italic, code, strikethrough, intraword underscores, fence language
//! labels, headings, ...), it reduces BOTH sides to their alphanumeric skeleton --
//! letters and digits only -- so every marker, all whitespace, the soft-wrapping,
//! and the indent simply vanish, uniformly, with no per-marker code. It fuzzy-
//! aligns the skeletons (a port of Python difflib's SequenceMatcher) to find where
//! the selection begins and ends in the raw source, expands those two boundaries
//! outward to swallow leading `##`/`**`/opening-fence and trailing punctuation/
//! fence, and returns the raw slice between them verbatim. The middle never has to
//! line up character for character, so a stray marker there can't break the match.
//!
//! This is a Rust port of claude-copy.py. serde_json is the only dependency;
//! clipboard access is isolated in read_clipboard_text(). The Python's --test flag
//! became ordinary cargo tests (`cargo test`).

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};
use std::fs::File;
use std::io::{IsTerminal, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use serde_json::Value;

// ---------------------------------------------------------------------------
// Config -- the bits most likely to need tweaking as you iterate.
// ---------------------------------------------------------------------------

/// Inline markdown markers we pull back in at a slice boundary so we don't cut
/// through the middle of a **bold** or `code` span.
const INLINE_MD_CHARS: [char; 4] = ['*', '`', '_', '~'];

/// How many of the most-recently-touched transcripts to search by default.
/// Transcripts are streamed and short-circuited, so scanning more is cheap;
/// --scan-depth overrides (raise it to dig out an older session).
const TRANSCRIPT_SCAN_COUNT: usize = 10;

/// Don't trust a match whose alphanumeric skeleton is shorter than this -- too
/// little signal, too easy to false-positive.
const MIN_SKELETON_LEN: usize = 8;

/// Probe windows for the cheap pre-filter that finds the candidate message
/// before paying for the fuzzy alignment: PROBE_COUNT windows of PROBE_WIDTH
/// skeleton chars, spread across the needle. A message qualifies as a candidate
/// when it contains enough of them (see needed_probe_hits) as exact substrings --
/// robust because a stray fence label can break at most the probe it falls in.
const PROBE_COUNT: usize = 6;
const PROBE_WIDTH: usize = 24;

/// Minimum fraction of the needle skeleton that must align (matched chars /
/// needle length) to accept a match. A true selection embeds almost entirely in
/// its source -- the only misses are things the source genuinely lacks -- so this
/// sits high; it mostly rejects a wrong message that happens to share some probes.
const MIN_RATIO: f64 = 0.90;

// ---------------------------------------------------------------------------
// Clipboard I/O  (the only macOS-specific layer)
// ---------------------------------------------------------------------------

/// Plain-text flavor of the clipboard, or "" if none.
fn read_clipboard_text() -> String {
    std::process::Command::new("pbpaste")
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default()
}

// ---------------------------------------------------------------------------
// Transcript enumeration
// ---------------------------------------------------------------------------

/// The n most-recently-modified transcript files, newest first.
///
/// Ranking by mtime means we must stat every file -- there's no cheaper way to
/// learn recency (directory mtimes don't track appends to existing files). But a
/// bounded min-heap keeps only n entries while streaming the directory walk, so
/// we avoid materializing and fully sorting the whole (ever-growing) list.
fn recent_transcripts(n: usize) -> Vec<PathBuf> {
    let base = match std::env::var_os("HOME") {
        Some(home) => PathBuf::from(home).join(".claude").join("projects"),
        None => return Vec::new(),
    };
    let mut heap: BinaryHeap<Reverse<(SystemTime, PathBuf)>> = BinaryHeap::new();
    let hidden = |p: &Path| {
        p.file_name()
            .and_then(|s| s.to_str())
            .is_some_and(|s| s.starts_with('.'))
    };
    let Ok(dirs) = std::fs::read_dir(&base) else {
        return Vec::new();
    };
    for dir in dirs.flatten() {
        let sub = dir.path();
        if hidden(&sub) {
            continue; // match the Python glob, which skips dotfiles
        }
        let Ok(files) = std::fs::read_dir(&sub) else {
            continue;
        };
        for file in files.flatten() {
            let p = file.path();
            if hidden(&p) || p.extension().and_then(|e| e.to_str()) != Some("jsonl") {
                continue;
            }
            let mtime = p
                .metadata()
                .and_then(|m| m.modified())
                .unwrap_or(SystemTime::UNIX_EPOCH);
            heap.push(Reverse((mtime, p)));
            if heap.len() > n {
                heap.pop(); // evict the oldest of the n+1
            }
        }
    }
    let mut kept: Vec<(SystemTime, PathBuf)> = heap.into_iter().map(|Reverse(t)| t).collect();
    kept.sort_by(|a, b| b.0.cmp(&a.0)); // newest first
    kept.into_iter().map(|(_, p)| p).collect()
}

/// Yields a binary stream's newline-separated lines from last to first, reading
/// backward one chunk at a time so a caller that stops early never touches the
/// front of a many-MB file. Splitting on b'\n' is UTF-8-safe -- 0x0A never
/// appears inside a multi-byte codepoint -- so each yielded line decodes on its
/// own. Lines have no trailing newline; a final blank line yields b"".
struct ReversedLines<R: Read + Seek> {
    inner: R,
    pos: u64,
    tail: Vec<u8>, // the not-yet-complete left fragment carried across chunks
    chunk_size: u64,
    pending: Vec<Vec<u8>>, // complete lines from the current chunk; pop() = next line
    done: bool,
}

fn reversed_lines<R: Read + Seek>(mut inner: R, chunk_size: u64) -> ReversedLines<R> {
    let pos = inner.seek(SeekFrom::End(0)).unwrap_or(0);
    ReversedLines {
        inner,
        pos,
        tail: Vec::new(),
        chunk_size,
        pending: Vec::new(),
        done: false,
    }
}

impl<R: Read + Seek> Iterator for ReversedLines<R> {
    type Item = Vec<u8>;

    fn next(&mut self) -> Option<Vec<u8>> {
        loop {
            if let Some(line) = self.pending.pop() {
                return Some(line);
            }
            if self.pos == 0 {
                if self.done {
                    return None;
                }
                self.done = true;
                return Some(std::mem::take(&mut self.tail));
            }
            let step = self.chunk_size.min(self.pos);
            self.pos -= step;
            self.inner.seek(SeekFrom::Start(self.pos)).ok()?;
            let mut buf = vec![0u8; step as usize];
            self.inner.read_exact(&mut buf).ok()?;
            buf.append(&mut self.tail);
            let mut parts: Vec<Vec<u8>> = buf.split(|&b| b == b'\n').map(<[u8]>::to_vec).collect();
            self.tail = parts.remove(0); // extends further left; hold for the next chunk
            self.pending = parts; // pop() walks them back-to-front, i.e. newest first
        }
    }
}

/// Yields the markdown of each assistant text block, newest first.
///
/// Lazy: it reads the transcript backward (see ReversedLines) and parses one
/// line at a time, so a caller matching against the newest message -- the common
/// case -- never reads or JSON-parses the rest of the file. Skips the cheap way
/// past non-assistant lines before paying for the JSON parse (most of a session
/// is user/tool_result/tool_use entries).
struct AssistantMessages<R: Read + Seek> {
    lines: ReversedLines<R>,
    pending: Vec<String>, // text blocks of the current message; pop() = newest first
}

impl<R: Read + Seek> Iterator for AssistantMessages<R> {
    type Item = String;

    fn next(&mut self) -> Option<String> {
        loop {
            if let Some(text) = self.pending.pop() {
                return Some(text);
            }
            let line = self.lines.next()?;
            const MARKER: &[u8] = b"\"assistant\"";
            if !line.windows(MARKER.len()).any(|w| w == MARKER) {
                continue;
            }
            let Ok(obj) = serde_json::from_slice::<Value>(&line) else {
                continue;
            };
            if obj.get("type").and_then(Value::as_str) != Some("assistant") {
                continue;
            }
            self.pending = obj
                .pointer("/message/content")
                .and_then(Value::as_array)
                .map(|blocks| {
                    blocks
                        .iter()
                        .filter(|b| b.get("type").and_then(Value::as_str) == Some("text"))
                        .filter_map(|b| b.get("text").and_then(Value::as_str))
                        .filter(|t| !t.is_empty())
                        .map(String::from)
                        .collect()
                })
                .unwrap_or_default();
        }
    }
}

fn assistant_messages(path: &Path) -> Box<dyn Iterator<Item = String>> {
    match File::open(path) {
        Ok(f) => Box::new(AssistantMessages {
            lines: reversed_lines(f, 1 << 16),
            pending: Vec::new(),
        }),
        Err(_) => Box::new(std::iter::empty()),
    }
}

// ---------------------------------------------------------------------------
// difflib port -- SequenceMatcher.get_matching_blocks, no junk, autojunk=False
// ---------------------------------------------------------------------------

/// The maximal non-overlapping matching blocks between a and b, as
/// (a_start, b_start, size) triples sorted by position, adjacent runs merged.
/// A faithful port of CPython difflib's recursive longest-match splitting,
/// minus the junk machinery (we never use it) and the (0-size) sentinel.
fn matching_blocks(a: &[char], b: &[char]) -> Vec<(usize, usize, usize)> {
    let mut b2j: HashMap<char, Vec<usize>> = HashMap::new();
    for (j, &ch) in b.iter().enumerate() {
        b2j.entry(ch).or_default().push(j); // ascending j, so `break` below is safe
    }

    let find_longest = |alo: usize, ahi: usize, blo: usize, bhi: usize| {
        let (mut besti, mut bestj, mut bestsize) = (alo, blo, 0usize);
        // j2len[j] = length of the longest match ending at a[i-1]/b[j]
        let mut j2len: HashMap<usize, usize> = HashMap::new();
        for (i, ch) in a.iter().enumerate().take(ahi).skip(alo) {
            let mut newj2len: HashMap<usize, usize> = HashMap::new();
            for &j in b2j.get(ch).map(Vec::as_slice).unwrap_or(&[]) {
                if j < blo {
                    continue;
                }
                if j >= bhi {
                    break;
                }
                let k = if j == blo { 1 } else { j2len.get(&(j - 1)).copied().unwrap_or(0) + 1 };
                newj2len.insert(j, k);
                if k > bestsize {
                    (besti, bestj, bestsize) = (i + 1 - k, j + 1 - k, k);
                }
            }
            j2len = newj2len;
        }
        (besti, bestj, bestsize)
    };

    let mut queue = vec![(0, a.len(), 0, b.len())];
    let mut blocks = Vec::new();
    while let Some((alo, ahi, blo, bhi)) = queue.pop() {
        let (i, j, k) = find_longest(alo, ahi, blo, bhi);
        if k > 0 {
            blocks.push((i, j, k));
            if alo < i && blo < j {
                queue.push((alo, i, blo, j));
            }
            if i + k < ahi && j + k < bhi {
                queue.push((i + k, ahi, j + k, bhi));
            }
        }
    }
    blocks.sort_unstable();

    let mut merged: Vec<(usize, usize, usize)> = Vec::new();
    for (i2, j2, k2) in blocks {
        match merged.last_mut() {
            Some((i1, j1, k1)) if *i1 + *k1 == i2 && *j1 + *k1 == j2 => *k1 += k2,
            _ => merged.push((i2, j2, k2)),
        }
    }
    merged
}

// ---------------------------------------------------------------------------
// Transcript recovery -- skeleton + fuzzy-anchor
// ---------------------------------------------------------------------------

/// The alphanumeric skeleton of `raw`: letters and digits only, lowercased.
///
/// Everything else -- markdown markers, whitespace, punctuation, fences,
/// headings -- drops out. That's the whole trick: the TUI-rendered text and the
/// raw source differ almost entirely in that discarded material, so their
/// skeletons line up without us knowing what any marker means.
fn skeleton(raw: &str) -> Vec<char> {
    raw.chars()
        .filter(|ch| ch.is_alphanumeric())
        .flat_map(char::to_lowercase)
        .collect()
}

/// skeleton() plus index_map, where index_map[i] is the byte offset in `raw` of
/// the char that produced skeleton char i (used to map a match back to raw).
fn skeleton_with_map(raw: &str) -> (Vec<char>, Vec<usize>) {
    let mut keep = Vec::new();
    let mut idx = Vec::new();
    for (i, ch) in raw.char_indices() {
        if ch.is_alphanumeric() {
            for lc in ch.to_lowercase() {
                keep.push(lc);
                idx.push(i);
            }
        }
    }
    (keep, idx)
}

/// PROBE_COUNT skeleton windows of PROBE_WIDTH chars, spread across the needle
/// (deduped by start offset). Short needles yield a single probe (the whole
/// skeleton). Used only for the cheap candidate pre-filter.
fn probes(nskel: &[char]) -> Vec<Vec<char>> {
    let length = nskel.len();
    if length <= PROBE_WIDTH {
        return vec![nskel.to_vec()];
    }
    let step = (length - PROBE_WIDTH) as f64 / (PROBE_COUNT - 1) as f64;
    let mut seen = std::collections::HashSet::new();
    let mut ps = Vec::new();
    for t in 0..PROBE_COUNT {
        let start = ((t as f64 * step) as usize).min(length - PROBE_WIDTH);
        if seen.insert(start) {
            ps.push(nskel[start..start + PROBE_WIDTH].to_vec());
        }
    }
    ps
}

/// How many probes a message must contain to earn a fuzzy-alignment pass. Two
/// for a real (multi-probe) needle -- selective, and robust to a label breaking
/// one -- but one for a short needle that only produced a single probe.
fn needed_probe_hits(probe_count: usize) -> usize {
    if probe_count >= 3 {
        2
    } else {
        1
    }
}

/// First occurrence of `needle` in `hay`, by skeleton-char index.
fn find_sub(hay: &[char], needle: &[char]) -> Option<usize> {
    if needle.len() > hay.len() {
        return None;
    }
    hay.windows(needle.len()).position(|w| w == needle)
}

/// Fuzzy-aligns the needle skeleton within a source skeleton and returns
/// (start, end, ratio) in source-skeleton coordinates, or None.
///
/// The matching blocks between the two bracket where the needle sits in the
/// source -- a stray label the source has but the needle doesn't is just a
/// skipped gap between blocks. We bound the alignment input to a window around
/// the probe hits so cost stays ~O(needle).
fn anchor_span(nskel: &[char], sskel: &[char], probe_hits: &[usize]) -> Option<(usize, usize, f64)> {
    let min_hit = *probe_hits.iter().min()?;
    let max_hit = *probe_hits.iter().max()?;
    let lo = min_hit.saturating_sub(nskel.len());
    let hi = (max_hit + nskel.len() + PROBE_WIDTH).min(sskel.len());
    let window = &sskel[lo..hi];
    let blocks = matching_blocks(nskel, window);
    let (first, last) = (*blocks.first()?, *blocks.last()?);
    let matched: usize = blocks.iter().map(|b| b.2).sum();
    // Map the needle's first/last char into the window, allowing for a few
    // unmatched needle chars hanging off either end of the outermost blocks.
    let start = lo + first.1.saturating_sub(first.0);
    let end = lo + (last.1 + last.2 + (nskel.len() - (last.0 + last.2))).min(window.len());
    Some((start, end, matched as f64 / nskel.len() as f64))
}

/// A code-fence delimiter line: optional indent, 3+ backticks/tildes, then an
/// optional info string (e.g. ```bash). Python: ^[ \t]*(`{3,}|~{3,})[^\n]*$
fn is_fence_line(line: &str) -> bool {
    let s = line.trim_start_matches([' ', '\t']);
    s.starts_with("```") || s.starts_with("~~~")
}

/// Byte ranges (open_start, close_end) of complete fenced blocks in `raw`.
///
/// open_start is the offset of the opening fence line; close_end is the offset
/// just past the closing fence line. An unterminated fence runs to end-of-text.
/// Used to snap a boundary that lands inside a block out to the whole block.
fn fence_blocks(raw: &str) -> Vec<(usize, usize)> {
    let mut blocks = Vec::new();
    let mut open_start: Option<usize> = None;
    let mut pos = 0;
    let n = raw.len();
    loop {
        let nl = raw[pos..].find('\n').map(|i| pos + i);
        let line_end = nl.unwrap_or(n);
        if is_fence_line(&raw[pos..line_end]) {
            match open_start {
                None => open_start = Some(pos),
                Some(os) => {
                    blocks.push((os, line_end));
                    open_start = None;
                }
            }
        }
        match nl {
            None => break,
            Some(x) => pos = x + 1,
        }
    }
    if let Some(os) = open_start {
        blocks.push((os, n));
    }
    blocks
}

/// The end (byte offset) of an ATX heading marker anchored at line_start: up to
/// 3 spaces/tabs of indent then 1-6 `#`, never looking past endpos. None if no
/// `#` run is there. Python: HEADING_HASHES.match(raw, line_start, start).
fn heading_hashes_end(raw: &str, line_start: usize, endpos: usize) -> Option<usize> {
    let bytes = raw.as_bytes();
    let mut i = line_start;
    while i < endpos && i - line_start < 3 && (bytes[i] == b' ' || bytes[i] == b'\t') {
        i += 1;
    }
    let hashes_start = i;
    while i < endpos && i - hashes_start < 6 && bytes[i] == b'#' {
        i += 1;
    }
    (i > hashes_start).then_some(i)
}

/// Widen the start boundary leftward to recover markup the skeleton dropped.
///
/// In priority order: an enclosing code fence (take the whole block), a leading
/// ATX heading marker on the same line ("## "), then the needle's own leading
/// punctuation (`lead`, e.g. a "- " list marker) consumed in reverse while
/// skipping markdown markers the TUI rendered away (a `**`/`` ` `` at the edge).
fn expand_start(mut start: usize, raw: &str, lead: &[char], blocks: &[(usize, usize)]) -> usize {
    for &(bs, be) in blocks {
        if bs <= start && start < be {
            return bs;
        }
    }
    let line_start = raw[..start].rfind('\n').map_or(0, |i| i + 1);
    if let Some(hend) = heading_hashes_end(raw, line_start, start) {
        if hend < start && matches!(raw.as_bytes()[hend], b' ' | b'\t') {
            let mut j = hend;
            while j < start && matches!(raw.as_bytes()[j], b' ' | b'\t') {
                j += 1;
            }
            if j == start {
                // everything before `start` on this line is the marker
                return line_start;
            }
        }
    }
    let mut li = lead.len();
    while let Some(ch) = raw[..start].chars().next_back() {
        if li > 0 && ch == lead[li - 1] {
            start -= ch.len_utf8();
            li -= 1;
        } else if INLINE_MD_CHARS.contains(&ch) {
            start -= ch.len_utf8();
        } else {
            break;
        }
    }
    start
}

/// Widen the end boundary rightward: an enclosing fence (take the whole block),
/// else the needle's trailing punctuation (`tail`, e.g. ".") consumed while
/// skipping markdown markers (a closing `` ` ``/`**` the TUI dropped).
fn expand_end(mut end: usize, raw: &str, tail: &[char], blocks: &[(usize, usize)]) -> usize {
    for &(bs, be) in blocks {
        if bs < end && end <= be {
            return be;
        }
    }
    let mut ti = 0;
    while let Some(ch) = raw[end..].chars().next() {
        if ti < tail.len() && ch == tail[ti] {
            end += ch.len_utf8();
            ti += 1;
        } else if INLINE_MD_CHARS.contains(&ch) {
            end += ch.len_utf8();
        } else {
            break;
        }
    }
    end
}

/// Find the needle in the given transcripts and return the exact source
/// markdown slice, or None if there's no confident match.
fn recover_in_files(needle_text: &str, paths: &[PathBuf]) -> Option<String> {
    // Collapse all whitespace runs to single spaces, trimmed (\s+ -> " ").
    let nnorm = needle_text.split_whitespace().collect::<Vec<_>>().join(" ");
    let nskel = skeleton(&nnorm);
    if nskel.len() < MIN_SKELETON_LEN {
        return None;
    }
    // The needle's leading/trailing punctuation fringe -- markup outside the
    // first/last alphanumeric char that a boundary expansion should recover.
    let first = nnorm
        .char_indices()
        .find(|(_, c)| c.is_alphanumeric())
        .map(|(i, _)| i)?;
    let (last, last_ch) = nnorm
        .char_indices()
        .rev()
        .find(|(_, c)| c.is_alphanumeric())?;
    let lead: Vec<char> = nnorm[..first].chars().collect();
    let tail: Vec<char> = nnorm[last + last_ch.len_utf8()..].chars().collect();

    let probes = probes(&nskel);
    let need = needed_probe_hits(probes.len());
    let mut best: Option<(f64, String)> = None;
    for path in paths {
        for raw in assistant_messages(path) {
            let sskel = skeleton(&raw);
            let hits: Vec<usize> = probes.iter().filter_map(|p| find_sub(&sskel, p)).collect();
            if hits.len() < need {
                continue;
            }
            let Some((s0, e0, ratio)) = anchor_span(&nskel, &sskel, &hits) else {
                continue;
            };
            if ratio < MIN_RATIO {
                continue;
            }
            let (_, sidx) = skeleton_with_map(&raw); // build the map only on a hit
            let blocks = fence_blocks(&raw);
            let start = expand_start(sidx[s0], &raw, &lead, &blocks);
            let last_byte = sidx[e0 - 1];
            let past_last = last_byte + raw[last_byte..].chars().next().map_or(0, char::len_utf8);
            let end = expand_end(past_last, &raw, &tail, &blocks);
            let slice = raw[start..end].trim();
            if slice.is_empty() {
                continue;
            }
            if best.as_ref().is_none_or(|(r, _)| ratio > *r) {
                best = Some((ratio, slice.to_string()));
            }
            if ratio >= 0.999 {
                // a near-perfect embed won't be beaten; stop here
                return Some(slice.to_string());
            }
        }
    }
    best.map(|(_, s)| s)
}

// ---------------------------------------------------------------------------
// Plain reflow (fallback)
// ---------------------------------------------------------------------------

/// Remove the TUI's leading 2-space response indent (1 or 2 spaces).
fn strip_indent(line: &str) -> &str {
    let mut s = line;
    for _ in 0..2 {
        s = s.strip_prefix(' ').unwrap_or(s);
    }
    s
}

/// A line is a list item if, after indent-stripping, it starts like one.
/// Python: ^\s*([-*+]\s|\d+[.)]\s)
fn is_list_item(line: &str) -> bool {
    let s = line.trim_start();
    let mut chars = s.chars();
    match chars.next() {
        Some('-' | '*' | '+') => chars.next().is_some_and(char::is_whitespace),
        Some(c) if c.is_ascii_digit() => {
            let rest = s.trim_start_matches(|c: char| c.is_ascii_digit());
            let mut rc = rest.chars();
            matches!(rc.next(), Some('.' | ')')) && rc.next().is_some_and(char::is_whitespace)
        }
        _ => false,
    }
}

/// Clean up plain TUI text: strip the 2-space indent, join soft-wrapped lines
/// into one, and preserve paragraph breaks (blank lines) and list-item breaks.
fn reflow(text: &str) -> String {
    let mut out = String::new();
    let mut pending_para = false; // a blank line was seen -> next content starts a paragraph
    let mut have_content = false;
    for physical in text.split('\n') {
        let line = strip_indent(physical);
        if line.trim().is_empty() {
            if have_content {
                pending_para = true;
            }
            continue;
        }
        if out.is_empty() {
            out.push_str(line);
        } else if pending_para {
            out.push_str("\n\n");
            out.push_str(line);
        } else if is_list_item(line) {
            out.push('\n');
            out.push_str(line);
        } else {
            // soft wrap -> a single space, unless one already abuts the seam
            if !out.ends_with(' ') && !line.starts_with(' ') {
                out.push(' ');
            }
            out.push_str(line);
        }
        pending_para = false;
        have_content = true;
    }
    out.trim().to_string()
}

// ---------------------------------------------------------------------------
// Obsidian quote wrapping
// ---------------------------------------------------------------------------

fn to_quote(md: &str) -> String {
    let mut out = vec!["> [!quote]".to_string()];
    for line in md.split('\n') {
        out.push(if line.trim().is_empty() {
            ">".to_string()
        } else {
            format!("> {line}")
        });
    }
    out.join("\n")
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

struct Args {
    text: Option<String>,
    quote: bool,
    no_transcript: bool,
    scan_depth: usize,
}

const USAGE: &str = "\
usage: claude-copy [-h] [--quote] [--no-transcript] [--scan-depth N] [text]

Recover clean source markdown from a Claude Code TUI selection.

positional arguments:
  text             explicit plain-text input (else stdin, else live clipboard)

options:
  -h, --help       show this help message and exit
  --quote          wrap as an Obsidian > [!quote] callout
  --no-transcript  skip transcript recovery
  --scan-depth N   how many recent transcripts to search for a match
                   (default 10); raise to dig out older sessions
";

fn arg_error(msg: &str) -> ! {
    eprint!("{USAGE}");
    eprintln!("claude-copy: error: {msg}");
    std::process::exit(2);
}

fn parse_args() -> Args {
    let mut args = Args {
        text: None,
        quote: false,
        no_transcript: false,
        scan_depth: TRANSCRIPT_SCAN_COUNT,
    };
    let parse_depth = |v: &str| {
        v.parse()
            .unwrap_or_else(|_| arg_error(&format!("argument --scan-depth: invalid value: '{v}'")))
    };
    let mut argv = std::env::args().skip(1);
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "-h" | "--help" => {
                print!("{USAGE}");
                std::process::exit(0);
            }
            "--quote" => args.quote = true,
            "--no-transcript" => args.no_transcript = true,
            "--scan-depth" => {
                let v = argv
                    .next()
                    .unwrap_or_else(|| arg_error("argument --scan-depth: expected one argument"));
                args.scan_depth = parse_depth(&v);
            }
            s if s.starts_with("--scan-depth=") => {
                args.scan_depth = parse_depth(&s["--scan-depth=".len()..]);
            }
            s if s.starts_with('-') && s.len() > 1 => {
                arg_error(&format!("unrecognized arguments: {s}"));
            }
            _ => {
                if args.text.is_some() {
                    arg_error(&format!("unrecognized arguments: {arg}"));
                }
                args.text = Some(arg);
            }
        }
    }
    args
}

/// Return the needle text: an explicit argv/stdin string if given, else the
/// live clipboard.
fn acquire(args: &Args) -> String {
    if let Some(text) = &args.text {
        if !text.is_empty() {
            return text.clone();
        }
    }
    if !std::io::stdin().is_terminal() {
        let mut piped = Vec::new();
        if std::io::stdin().read_to_end(&mut piped).is_ok() {
            let piped = String::from_utf8_lossy(&piped);
            if !piped.trim().is_empty() {
                return piped.into_owned();
            }
        }
    }
    read_clipboard_text()
}

/// Transcript recovery first (when given transcripts to search and a non-blank
/// needle), plain reflow as the fallback.
fn build_markdown(needle_text: &str, transcripts: Option<&[PathBuf]>) -> String {
    if let Some(paths) = transcripts {
        if !needle_text.trim().is_empty() {
            if let Some(recovered) = recover_in_files(needle_text, paths) {
                return recovered; // already-clean source markdown
            }
        }
    }
    reflow(needle_text)
}

fn main() {
    let args = parse_args();
    let needle_text = acquire(&args);
    let transcripts = (!args.no_transcript).then(|| recent_transcripts(args.scan_depth));
    let md = build_markdown(&needle_text, transcripts.as_deref());
    if md.is_empty() {
        eprintln!("claude-copy: nothing to reformat");
        std::process::exit(1);
    }
    print!("{}", if args.quote { to_quote(&md) } else { md });
}

// ---------------------------------------------------------------------------
// Tests  (run with `cargo test`)
//
// Ported from the Python original's built-in suite. They cover the pure
// transform logic plus the parsing inside the transcript streaming (via
// in-memory readers and temp files), but not the live clipboard itself.
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn chars(s: &str) -> Vec<char> {
        s.chars().collect()
    }

    // -- skeleton / probes --------------------------------------------------

    #[test]
    fn skeleton_keeps_only_alphanumerics_lowercased() {
        assert_eq!(skeleton("**Hi**, `to_date`!  #Heading"), chars("hitodateheading"));
    }

    #[test]
    fn skeleton_map_points_back_at_source() {
        let raw = "a **Bold** c";
        let (skel, idx) = skeleton_with_map(raw);
        assert_eq!(skel, skeleton(raw));
        assert_eq!(skel.len(), idx.len());
        let bold = find_sub(&skel, &chars("bold")).unwrap();
        assert_eq!(&raw[idx[bold]..idx[bold] + 1], "B");
    }

    #[test]
    fn probes_span_and_dedupe() {
        let skel = skeleton(&"x".repeat(200));
        let ps = probes(&skel);
        assert!(ps.iter().all(|p| p.len() == PROBE_WIDTH));
        assert!(ps.len() <= PROBE_COUNT);
    }

    #[test]
    fn short_needle_single_probe() {
        assert_eq!(probes(&chars("abcdef")), vec![chars("abcdef")]);
        assert_eq!(needed_probe_hits(1), 1);
        assert_eq!(needed_probe_hits(6), 2);
    }

    // -- reflow ---------------------------------------------------------------

    #[test]
    fn soft_wrap_joins_paragraphs_split() {
        assert_eq!(
            reflow("This is a soft\nwrapped line.\n\nSecond para.\n"),
            "This is a soft wrapped line.\n\nSecond para."
        );
    }

    #[test]
    fn list_items_keep_their_breaks() {
        assert_eq!(reflow("- one\n- two\n- three\n"), "- one\n- two\n- three");
    }

    #[test]
    fn strips_tui_indent() {
        assert_eq!(reflow("  indented line\n"), "indented line");
    }

    // -- quote ----------------------------------------------------------------

    #[test]
    fn callout_wrapping() {
        assert_eq!(to_quote("a\n\nb"), "> [!quote]\n> a\n>\n> b");
    }

    // -- fence blocks -----------------------------------------------------------

    #[test]
    fn fence_block_ranges() {
        let raw = "a\n```py\ncode\n```\nb";
        let blocks = fence_blocks(raw);
        assert_eq!(blocks.len(), 1);
        let (bs, be) = blocks[0];
        assert_eq!(&raw[bs..be], "```py\ncode\n```");
    }

    #[test]
    fn unterminated_fence_runs_to_end() {
        let raw = "```\nstuff to the end";
        assert_eq!(fence_blocks(raw), vec![(0, raw.len())]);
    }

    // -- reversed lines ---------------------------------------------------------

    fn rev(data: &[u8], chunk_size: u64) -> Vec<String> {
        reversed_lines(Cursor::new(data.to_vec()), chunk_size)
            .map(|b| String::from_utf8(b).unwrap())
            .collect()
    }

    #[test]
    fn no_trailing_newline() {
        // Small chunk forces multi-chunk reassembly across boundaries.
        assert_eq!(rev(b"AB\nCD\nEF", 3), ["EF", "CD", "AB"]);
    }

    #[test]
    fn trailing_newline_yields_blank_first() {
        assert_eq!(rev(b"AB\nCD\n", 3), ["", "CD", "AB"]);
    }

    #[test]
    fn single_line() {
        assert_eq!(rev(b"only line", 4), ["only line"]);
    }

    #[test]
    fn matches_forward_split_reversed() {
        let data = "some\nlonger\nmultiline\ncontent\nhere".repeat(3);
        let mut expected: Vec<String> = data.split('\n').map(String::from).collect();
        expected.reverse();
        for cs in [1, 4, 7, 4096] {
            assert_eq!(rev(data.as_bytes(), cs), expected);
        }
    }

    // -- build_markdown -----------------------------------------------------------

    #[test]
    fn transcript_takes_priority() {
        let src = "the transcript source text here";
        let p = write_transcript(&[src]);
        assert_eq!(
            build_markdown("the transcript\nsource text here", Some(&[p])),
            src
        );
    }

    #[test]
    fn reflow_fallback_when_no_match() {
        assert_eq!(build_markdown("  soft\n  wrap\n", Some(&[])), "soft wrap");
        assert_eq!(build_markdown("  soft\n  wrap\n", None), "soft wrap");
    }

    // -- transcript recovery --------------------------------------------------------

    static COUNTER: AtomicUsize = AtomicUsize::new(0);

    fn write_transcript(msgs: &[&str]) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "claude-copy-test-{}-{}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::SeqCst)
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("session.jsonl");
        let mut recs = vec![serde_json::json!({"type": "user", "message": {"content": "noise"}})];
        for text in msgs {
            recs.push(serde_json::json!({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": text}]}
            }));
        }
        let body = recs.iter().map(Value::to_string).collect::<Vec<_>>().join("\n");
        std::fs::write(&p, body).unwrap();
        p
    }

    fn recover(msgs: &[&str], needle: &str) -> Option<String> {
        recover_in_files(needle, &[write_transcript(msgs)])
    }

    #[test]
    fn assistant_messages_streams_newest_first() {
        let p = write_transcript(&["first", "second"]);
        let got: Vec<String> = assistant_messages(&p).collect();
        assert_eq!(got, ["second", "first"]);
    }

    #[test]
    fn assistant_messages_is_lazy() {
        // An iterator, so a caller can stop after the newest message without
        // the rest being parsed. Taking one item must yield "newest".
        let p = write_transcript(&["oldest", "newest"]);
        assert_eq!(assistant_messages(&p).next().unwrap(), "newest");
    }

    #[test]
    fn short_needle_rejected() {
        assert_eq!(recover(&["short text here"], "short"), None);
    }

    #[test]
    fn no_match_returns_none() {
        assert_eq!(
            recover(&["completely different content"], "absent needle phrase entirely"),
            None
        );
    }

    #[test]
    fn recovers_bold_and_inline_code() {
        let src = "Here is **bold** and `code` to find in the text.";
        // Needle ends at "text" (no period selected) -> slice stops there too.
        assert_eq!(
            recover(&[src], "bold and code to find in the text").unwrap(),
            "**bold** and `code` to find in the text"
        );
    }

    #[test]
    fn recovers_inline_code_with_underscore() {
        // snake_case inside inline code -- handled with no underscore logic.
        let src = "Parsing uses `to_date`/`to_timestamp` on the raw HL7 strings.";
        assert_eq!(
            recover(&[src], "to_date/to_timestamp on the raw HL7 strings").unwrap(),
            "`to_date`/`to_timestamp` on the raw HL7 strings"
        );
    }

    #[test]
    fn recovers_intraword_underscore_in_prose() {
        let src = "spilling to disk (work_mem too small for the data)";
        assert_eq!(
            recover(&[src], "work_mem too small for the data").unwrap(),
            "work_mem too small for the data"
        );
    }

    #[test]
    fn recovers_with_lone_tilde() {
        let src = "Drop `completionSize` to ~50\u{2013}100 and lean on the timeout.";
        assert_eq!(
            recover(&[src], "completionSize to ~50\u{2013}100 and lean on the timeout").unwrap(),
            "`completionSize` to ~50\u{2013}100 and lean on the timeout"
        );
    }

    #[test]
    fn recovers_fenced_code_block() {
        let src = "Run this:\n\n```python\nfoo_bar = compute_value(x)\n```\n\nDone.";
        assert_eq!(
            recover(&[src], "foo_bar = compute_value(x)").unwrap(),
            "```python\nfoo_bar = compute_value(x)\n```"
        );
    }

    #[test]
    fn recovers_when_needle_includes_fence_label() {
        // A block whose language label was copied ("fish\ncmd"): the label is
        // in the source skeleton, and the aligner skips it as a gap if the
        // needle lacks it or matches it if present -- either way the block
        // comes back.
        let src = "Run it:\n\n```fish\nkubectl get pods\n```\n\nDone.";
        assert_eq!(
            recover(&[src], "fish\nkubectl get pods").unwrap(),
            "```fish\nkubectl get pods\n```"
        );
        assert_eq!(
            recover(&[src], "kubectl get pods").unwrap(),
            "```fish\nkubectl get pods\n```"
        );
    }

    #[test]
    fn recovers_mixed_fence_labels_in_one_message() {
        // Two blocks, only one label copied -- no special handling needed.
        let src = "```sql\nSELECT 1\n```\n```fish\nls -a\n```";
        assert_eq!(recover(&[src], "SELECT 1\nfish\nls -a").unwrap(), src);
    }

    #[test]
    fn recovers_keeps_leading_heading_marker() {
        // A selection beginning at a heading keeps its marker, every level.
        for lvl in 1..=6 {
            let src = format!("{} Title Here\n\nSome body text after.", "#".repeat(lvl));
            assert_eq!(
                recover(&[&src], "Title Here\nSome body text after.").unwrap(),
                src
            );
        }
    }

    #[test]
    fn recovers_across_midselection_heading() {
        let src = "Intro para.\n\n## A Heading\n\nBody follows here.";
        assert_eq!(
            recover(&[src], "Intro para.\nA Heading\nBody follows here.").unwrap(),
            src
        );
    }

    #[test]
    fn keeps_trailing_punctuation() {
        // The alnum skeleton ends at the last letter; the fringe sync pulls
        // back the trailing punctuation the selection included.
        let src = "End with the `ApplicationError(\"no data\")`.";
        assert_eq!(
            recover(&[src], "End with the ApplicationError(\"no data\").").unwrap(),
            src
        );
    }

    #[test]
    fn keeps_leading_list_marker() {
        let src = "Intro.\n\n- alpha item here\n- beta item here\n\nEnd.";
        assert_eq!(
            recover(&[src], "- alpha item here\n- beta item here").unwrap(),
            "- alpha item here\n- beta item here"
        );
    }

    #[test]
    fn bold_span_at_selection_end() {
        let src = "Here is **important stuff** you want.";
        assert_eq!(recover(&[src], "important stuff").unwrap(), "**important stuff**");
    }

    #[test]
    fn scan_depth_limits_search() {
        // The scan depth caps how many transcripts recovery looks at. With the
        // needle in the 2nd-most-recent file, depth 1 misses it, depth 2 hits.
        let newer = write_transcript(&["nothing relevant here at all today"]);
        let older = write_transcript(&["distinctive findable phrase here now"]);
        let files = [newer, older]; // index 0 == most recent
        let needle = "distinctive findable phrase here now";
        assert_eq!(recover_in_files(needle, &files[..1]), None);
        assert_eq!(recover_in_files(needle, &files[..2]).unwrap(), needle);
    }
}
