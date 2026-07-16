#!/usr/bin/env python3
"""
tailscale-acl-toggle.py

Toggle a single user's membership in a named group of the Tailscale tailnet
policy file (the admin console's "Access controls"), by commenting or
un-commenting exactly one line.

The tailnet policy file is HuJSON (JSON + // comments + trailing commas). This
tool downloads the *raw* HuJSON text, flips the comment state of the one line
that names you inside the target group, and uploads the raw text back. It never
parses or re-serializes the JSON, so every comment, blank line, and byte of
whitespace outside the single toggled line is preserved exactly.

    "access on"  = your line is active (not commented) -> you can reach the servers
    "access off" = your line is commented out          -> access revoked

Auth is via a Tailscale OAuth client (scope: acl, write). The long-lived client
secret lives in 1Password and is fetched by a small helper script that shells
out to `op read`; a short-lived API token is minted on each run, so there is
nothing to rotate.

USAGE
    tailscale-acl-toggle.py status          # report current state, no changes
    tailscale-acl-toggle.py off             # comment your line (revoke access)
    tailscale-acl-toggle.py on              # un-comment your line (grant access)
    tailscale-acl-toggle.py toggle          # flip whatever the current state is

Add --dry-run to any mutating command to preview the one-line diff without
uploading. Add -v/--verbose for HTTP detail.

CONFIG
    Reads ~/.config/tailscale-acl-toggle/config.json (override with --config):
        {
          "group": "group:phi",             # target group (group: prefix optional)
          "user": "you@example.com",         # your identity as it appears in the ACL
          "client_id": "kXXXXXXXXXXXX",       # OAuth client id (not secret)
          "tailnet": "-",                    # "-" = the OAuth client's own tailnet
          "secret_command": "tailscale-acl-oauth-secret.sh"  # prints the secret
        }
    secret_command may be a string (split like a shell line) or a list of args;
    a bare filename is resolved next to this script. It must print the OAuth
    client secret on stdout. Any config value can be overridden on the command
    line (--group/--user/--client-id/--tailnet/--secret-command).
"""

import argparse
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.tailscale.com/api/v2"
DEFAULT_CONFIG_PATH = os.path.expanduser(
    "~/.config/tailscale-acl-toggle/config.json"
)
DEFAULT_SECRET_COMMAND = "tailscale-acl-oauth-secret.sh"


# --------------------------------------------------------------------------- #
# Config & credentials
# --------------------------------------------------------------------------- #
def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        die(f"config file {path} is not valid JSON: {e}")


def resolve_secret_command(spec):
    """Normalize the configured secret_command into an argv list.

    A string is split like a shell line; a list is used as-is. A bare
    filename (no path separator) for the first argument is resolved next to
    this script, so the bundled helper is found regardless of cwd.
    """
    argv = spec if isinstance(spec, list) else shlex.split(spec)
    if not argv:
        die("secret_command is empty.")
    prog = argv[0]
    if os.sep not in prog and not os.path.isabs(prog):
        bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), prog)
        if os.path.exists(bundled):
            argv = [bundled] + argv[1:]
    return argv


def get_client_secret(secret_command):
    """Run the configured helper (e.g. `op read ...`) and return its stdout."""
    argv = resolve_secret_command(secret_command)
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        die(f"secret_command not found: {argv[0]!r}")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        die(
            f"secret_command failed ({' '.join(argv)!r}): "
            f"{detail or 'exit ' + str(result.returncode)}"
        )
    secret = result.stdout.decode("utf-8").strip()
    if not secret:
        die(f"secret_command produced no output: {' '.join(argv)!r}")
    return secret


# --------------------------------------------------------------------------- #
# HTTP / Tailscale API
# --------------------------------------------------------------------------- #
def _request(method, url, *, headers=None, data=None, verbose=False):
    req = urllib.request.Request(url, method=method, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if verbose:
        eprint(f"--> {method} {url}")
        for k, v in (headers or {}).items():
            shown = v if k.lower() != "authorization" else "Bearer <redacted>"
            eprint(f"    {k}: {shown}")
    try:
        resp = urllib.request.urlopen(req)
        body = resp.read()
        if verbose:
            eprint(f"<-- {resp.status} {resp.reason}")
        return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if verbose:
            eprint(f"<-- {e.code} {e.reason}\n{body}")
        return e.code, dict(e.headers), body.encode("utf-8")


def get_access_token(client_id, client_secret, verbose=False):
    data = urllib.parse.urlencode(
        {"client_id": client_id, "client_secret": client_secret}
    ).encode("utf-8")
    status, _, body = _request(
        "POST",
        f"{API_BASE}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        verbose=verbose,
    )
    if status != 200:
        die(f"OAuth token request failed ({status}): {body.decode('utf-8', 'replace')}")
    try:
        token = json.loads(body)["access_token"]
    except (json.JSONDecodeError, KeyError):
        die(f"unexpected OAuth token response: {body.decode('utf-8', 'replace')}")
    return token


def get_acl(token, tailnet, verbose=False):
    """Return (raw_hujson_text, etag)."""
    status, headers, body = _request(
        "GET",
        f"{API_BASE}/tailnet/{urllib.parse.quote(tailnet)}/acl",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/hujson"},
        verbose=verbose,
    )
    if status != 200:
        die(f"failed to fetch policy file ({status}): {body.decode('utf-8', 'replace')}")
    etag = headers.get("ETag") or headers.get("Etag")
    return body.decode("utf-8"), etag


def post_acl(token, tailnet, text, etag, verbose=False):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/hujson",
    }
    if etag:
        headers["If-Match"] = etag
    status, _, body = _request(
        "POST",
        f"{API_BASE}/tailnet/{urllib.parse.quote(tailnet)}/acl",
        headers=headers,
        data=text.encode("utf-8"),
        verbose=verbose,
    )
    if status == 412:
        die(
            "the policy file changed on the server since it was fetched "
            "(If-Match/ETag mismatch). Re-run to retry with a fresh copy."
        )
    if status != 200:
        die(f"failed to upload policy file ({status}): {body.decode('utf-8', 'replace')}")


# --------------------------------------------------------------------------- #
# HuJSON text surgery — locate the group's array, then the user's line.
# --------------------------------------------------------------------------- #
def _iter_significant_chars(line):
    """Yield chars of `line` that are outside strings and // comments.

    Handles HuJSON strings (with backslash escapes) so that brackets or
    slashes inside a quoted value are ignored.
    """
    in_str = False
    escaped = False
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "/" and i + 1 < n and line[i + 1] == "/":
                return  # rest of line is a comment
            else:
                yield c
        i += 1


def find_group_array_span(lines, group_key):
    """Return (start_line, end_line) inclusive covering the group's [ ... ].

    start_line is the line holding the opening '['; end_line holds the
    matching ']'. Bracket matching ignores brackets inside strings/comments.
    """
    key_pat = re.compile(r'"' + re.escape(group_key) + r'"\s*:')
    decl_idx = None
    for idx, line in enumerate(lines):
        if key_pat.search(line):
            decl_idx = idx
            break
    if decl_idx is None:
        die(f"group {group_key!r} not found in the policy file.")

    # Find the opening '[' at or after the declaration line.
    depth = 0
    start = None
    for idx in range(decl_idx, len(lines)):
        for c in _iter_significant_chars(lines[idx]):
            if c == "[":
                if start is None:
                    start = idx
                depth += 1
            elif c == "]":
                depth -= 1
                if start is not None and depth == 0:
                    return start, idx
    die(f"could not find the closing ']' for group {group_key!r}.")


def find_user_line(lines, span, user):
    start, end = span
    user_pat = re.compile(r'"' + re.escape(user) + r'"')
    matches = [i for i in range(start, end + 1) if user_pat.search(lines[i])]
    if not matches:
        die(
            f"user {user!r} not found inside group. "
            f"The line must already exist (commented or not) so it can be toggled."
        )
    if len(matches) > 1:
        die(
            f"user {user!r} appears on {len(matches)} lines inside the group "
            f"(lines {[m + 1 for m in matches]}); refusing to guess which to toggle."
        )
    return matches[0]


def line_is_commented(line):
    return re.match(r"\s*//", line) is not None


def comment_line(line):
    # Insert "// " right after the leading whitespace.
    return re.sub(r"^(\s*)(\S.*)$", r"\1// \2", line, count=1)


def uncomment_line(line):
    # Remove one leading "//" (and a single following space) after indentation.
    return re.sub(r"^(\s*)//[ ]?", r"\1", line, count=1)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def die(msg):
    eprint(f"error: {msg}")
    sys.exit(1)


def state_word(commented):
    return "OFF (commented out)" if commented else "ON (active)"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Toggle a user's line in a Tailscale ACL group.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "action",
        choices=["status", "on", "off", "toggle"],
        help="status: report only; on/off/toggle: change access",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH,
                        help=f"config file (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--group", help="target group (group: prefix optional)")
    parser.add_argument("--user", help="your identity as it appears in the ACL")
    parser.add_argument("--client-id", help="OAuth client id")
    parser.add_argument("--tailnet", help="tailnet name, or '-' for the client's own")
    parser.add_argument("--secret-command",
                        help="command that prints the OAuth client secret")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the one-line change but do not upload")
    parser.add_argument("-v", "--verbose", action="store_true", help="show HTTP detail")
    args = parser.parse_args()

    cfg = load_config(args.config)

    group = args.group or cfg.get("group")
    user = args.user or cfg.get("user")
    client_id = args.client_id or cfg.get("client_id")
    tailnet = args.tailnet or cfg.get("tailnet") or "-"
    secret_command = (
        args.secret_command or cfg.get("secret_command") or DEFAULT_SECRET_COMMAND
    )
    if not group:
        die("no group set (use --group or 'group' in the config file).")
    if not user:
        die("no user set (use --user or 'user' in the config file).")
    if not client_id:
        die("no OAuth client id set (use --client-id or 'client_id' in the config).")
    if not group.startswith("group:"):
        group = "group:" + group

    client_secret = get_client_secret(secret_command)
    token = get_access_token(client_id, client_secret, verbose=args.verbose)
    text, etag = get_acl(token, tailnet, verbose=args.verbose)

    # splitlines(keepends=True) preserves each line's exact ending so a rejoin
    # reproduces the original bytes when nothing is changed.
    lines = text.splitlines(keepends=True)
    span = find_group_array_span(lines, group)
    idx = find_user_line(lines, span, user)

    currently_commented = line_is_commented(lines[idx])
    current = state_word(currently_commented)

    if args.action == "status":
        print(f"{user} in {group}: access is {current}")
        print(f"  line {idx + 1}: {lines[idx].rstrip(chr(10))}")
        return

    if args.action == "on":
        want_commented = False
    elif args.action == "off":
        want_commented = True
    else:  # toggle
        want_commented = not currently_commented

    if want_commented == currently_commented:
        print(f"No change: {user} in {group} is already {current}.")
        return

    old_line = lines[idx]
    new_line = comment_line(old_line) if want_commented else uncomment_line(old_line)
    lines[idx] = new_line

    print(f"{user} in {group}: {current} -> {state_word(want_commented)}")
    diff = difflib.unified_diff(
        [old_line], [new_line],
        fromfile=f"line {idx + 1} (before)", tofile=f"line {idx + 1} (after)",
    )
    sys.stdout.writelines(diff)
    if not old_line.endswith("\n"):
        print()

    if args.dry_run:
        print("(dry run: policy file not uploaded)")
        return

    new_text = "".join(lines)
    post_acl(token, tailnet, new_text, etag, verbose=args.verbose)
    print("Uploaded. Access is now", state_word(want_commented) + ".")


if __name__ == "__main__":
    main()
