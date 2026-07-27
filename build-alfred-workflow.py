#!/usr/bin/env python3
"""Generate claude-copy.alfredworkflow -- the Alfred front-end for claude-copy.

This is the source of truth for the workflow. Edit here and re-run to regenerate
the bundle; then re-import into Alfred (or edit in Alfred and re-export, your call).

The workflow wires up, for each of three modes -- quote, raw, and verbatim-quote:
  - a Hotkey trigger (key is stripped on import; assign your own)
  - a Universal Action (acts on selected text / clipboard-history entries)
  - a Run Script action -> a Copy to Clipboard output with auto-paste

(verbatim-quote runs `--quote --verbatim`: quote-wrap the input as-is, skipping
transcript recovery and reflow -- for text already cleaned by Claude Code's /copy.)

The path to the claude-copy executable is an Alfred *user-configuration* variable
(SCRIPT_PATH), prompted at install time, so the bundle isn't tied to one machine's
checkout. It defaults to the compiled Rust binary (see claude-copy-rs/; build with
`cargo build --release`). Any executable that reads stdin works -- claude-copy.py
runs via its shebang if you point SCRIPT_PATH back at it.
"""

import os
import plistlib
import zipfile

# --- knobs ----------------------------------------------------------------
SCRIPT_PATH_DEFAULT = "/Users/jflavin/repos/flavin-tools/claude-copy-rs/target/release/claude-copy"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-copy.alfredworkflow")

# Stable UIDs so regenerating produces a deterministic, diffable bundle.
HK_Q = "A1B2C3D4-0001-4001-8001-000000000001"
UA_Q = "A1B2C3D4-0002-4002-8002-000000000002"
HK_R = "A1B2C3D4-0003-4003-8003-000000000003"
UA_R = "A1B2C3D4-0004-4004-8004-000000000004"
S_Q = "A1B2C3D4-0005-4005-8005-000000000005"
S_R = "A1B2C3D4-0006-4006-8006-000000000006"
CLIP = "A1B2C3D4-0007-4007-8007-000000000007"
HK_VQ = "A1B2C3D4-0008-4008-8008-000000000008"
UA_VQ = "A1B2C3D4-0009-4009-8009-000000000009"
S_VQ = "A1B2C3D4-000A-400A-800A-00000000000A"


def script_obj(uid, flags):
    # Input arrives on $1 (Alfred argument / Universal Action selection); we pipe
    # it to the script on stdin. Empty $1 (hotkey, no argument) -> the script reads
    # the live clipboard itself. `flags` is the (possibly empty) extra CLI flags.
    suffix = (" " + flags) if flags else ""
    body = 'printf \'%%s\' "$1" | "$SCRIPT_PATH"%s' % suffix
    return {"uid": uid, "version": 2, "type": "alfred.workflow.action.script",
            "config": {"concurrently": False, "escaping": 102, "script": body,
                       "scriptargtype": 1, "scriptfile": "", "type": 11}}


def hotkey_obj(uid):
    return {"uid": uid, "version": 0, "type": "alfred.workflow.trigger.hotkey",
            "config": {"action": 0, "argument": 0, "hotkey": 0, "hotmod": 0,
                       "leftcursor": False, "modsmode": 0}}


def ua_obj(uid, name):
    return {"uid": uid, "version": 1, "type": "alfred.workflow.trigger.universalaction",
            "config": {"acceptsfiles": False, "acceptsmulti": 0, "acceptstext": True,
                       "acceptsurls": False, "name": name}}


def conn(dest):
    return {"destinationuid": dest, "modifiers": 0, "modifiersubtext": "", "vitoclose": False}


clip_obj = {"uid": CLIP, "version": 3, "type": "alfred.workflow.output.clipboard",
            "config": {"autopaste": True, "clipboardtext": "{query}",
                       "ignoredynamicplaceholders": False, "transient": False}}

info = {
    "bundleid": "local.flavin.claude-copy",
    "category": "Tools",
    "name": "Claude Copy (Claude Code -> Obsidian)",
    "createdby": "John Flavin",
    "description": "Recover clean Obsidian markdown from a Claude Code TUI selection.",
    "disabled": False,
    "readme": ("Recovers the clean source markdown from text copied out of the Claude "
               "Code TUI.\n\n"
               "Set SCRIPT_PATH (in Configure Workflow) to your claude-copy executable "
               "(the Rust binary from claude-copy-rs/, or claude-copy.py).\n\n"
               "Hotkeys are stripped on import -- double-click each Hotkey object and set "
               "your own combo. Leave its Argument as the default; the script reads the "
               "live clipboard itself.\n\n"
               "  - Hotkey / Universal Action 'as Quote'          -> wraps in > [!quote]\n"
               "  - Hotkey / Universal Action 'raw'               -> plain markdown\n"
               "  - Hotkey / Universal Action 'verbatim as Quote' -> quote-wrap as-is, no\n"
               "    transcript recovery or reflow (for text already cleaned by /copy)\n\n"
               "Universal Actions act on selected text / clipboard-history entries."),
    "webaddress": "",
    "objects": [
        hotkey_obj(HK_Q), ua_obj(UA_Q, "Claude Copy as Quote"),
        hotkey_obj(HK_R), ua_obj(UA_R, "Claude Copy (raw)"),
        hotkey_obj(HK_VQ), ua_obj(UA_VQ, "Claude Copy verbatim as Quote"),
        script_obj(S_Q, "--quote"), script_obj(S_R, ""),
        script_obj(S_VQ, "--quote --verbatim"), clip_obj,
    ],
    "connections": {
        HK_Q: [conn(S_Q)], UA_Q: [conn(S_Q)],
        HK_R: [conn(S_R)], UA_R: [conn(S_R)],
        HK_VQ: [conn(S_VQ)], UA_VQ: [conn(S_VQ)],
        S_Q: [conn(CLIP)], S_R: [conn(CLIP)], S_VQ: [conn(CLIP)],
    },
    "uidata": {
        HK_Q: {"xpos": 30, "ypos": 50}, UA_Q: {"xpos": 30, "ypos": 150},
        HK_R: {"xpos": 30, "ypos": 290}, UA_R: {"xpos": 30, "ypos": 390},
        HK_VQ: {"xpos": 30, "ypos": 530}, UA_VQ: {"xpos": 30, "ypos": 630},
        S_Q: {"xpos": 280, "ypos": 100}, S_R: {"xpos": 280, "ypos": 340},
        S_VQ: {"xpos": 280, "ypos": 580},
        CLIP: {"xpos": 540, "ypos": 340},
    },
    "userconfigurationconfig": [
        {
            "type": "textfield",
            "variable": "SCRIPT_PATH",
            "label": "claude-copy path",
            "description": "Absolute path to the claude-copy executable -- the built "
                           "Rust binary (claude-copy-rs/target/release/claude-copy), "
                           "or claude-copy.py.",
            "config": {
                "default": SCRIPT_PATH_DEFAULT,
                "placeholder": "/path/to/claude-copy",
                "required": True,
                "trim": True,
            },
        },
    ],
    "variablesdontexport": [],
    "version": "1.0",
}


def main():
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.plist", plistlib.dumps(info))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
