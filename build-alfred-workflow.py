#!/usr/bin/env python3
"""Generate paste-reflow.alfredworkflow -- the Alfred front-end for paste-reflow.py.

This is the source of truth for the workflow. Edit here and re-run to regenerate
the bundle; then re-import into Alfred (or edit in Alfred and re-export, your call).

The workflow wires up, for both quote and raw modes:
  - a Hotkey trigger (key is stripped on import; assign your own)
  - a Universal Action (acts on selected text / clipboard-history entries)
  - a Run Script action -> a Copy to Clipboard output with auto-paste

The path to paste-reflow.py is an Alfred *user-configuration* variable (SCRIPT_PATH),
prompted at install time, so the bundle isn't tied to one machine's checkout.
"""

import os
import plistlib
import zipfile

# --- knobs ----------------------------------------------------------------
PY3 = "/opt/homebrew/bin/python3"
SCRIPT_PATH_DEFAULT = "/Users/jflavin/repos/flavin-tools/paste-reflow.py"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paste-reflow.alfredworkflow")

# Stable UIDs so regenerating produces a deterministic, diffable bundle.
HK_Q = "A1B2C3D4-0001-4001-8001-000000000001"
UA_Q = "A1B2C3D4-0002-4002-8002-000000000002"
HK_R = "A1B2C3D4-0003-4003-8003-000000000003"
UA_R = "A1B2C3D4-0004-4004-8004-000000000004"
S_Q = "A1B2C3D4-0005-4005-8005-000000000005"
S_R = "A1B2C3D4-0006-4006-8006-000000000006"
CLIP = "A1B2C3D4-0007-4007-8007-000000000007"


def script_obj(uid, quote):
    # Input arrives on $1 (Alfred argument / Universal Action selection); we pipe
    # it to the script on stdin. Empty $1 (hotkey, no argument) -> the script reads
    # the live clipboard itself, HTML flavor and all.
    flag = " --quote" if quote else ""
    body = 'printf \'%%s\' "$1" | %s "$SCRIPT_PATH"%s' % (PY3, flag)
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
    "bundleid": "local.flavin.paste-reflow",
    "category": "Tools",
    "name": "Paste-reflow (Claude Code -> Obsidian)",
    "createdby": "John Flavin",
    "description": "Reformat copied Claude Code TUI output into clean Obsidian markdown.",
    "disabled": False,
    "readme": ("Reformats text copied out of the Claude Code TUI into clean markdown.\n\n"
               "Set SCRIPT_PATH (in Configure Workflow) to your paste-reflow.py.\n\n"
               "Hotkeys are stripped on import -- double-click each Hotkey object and set "
               "your own combo. Leave its Argument as the default; the script reads the "
               "live clipboard itself (to get the HTML flavor).\n\n"
               "  - Hotkey / Universal Action 'as Quote' -> wraps in > [!quote]\n"
               "  - Hotkey / Universal Action 'raw'       -> plain markdown\n\n"
               "Universal Actions act on selected text / clipboard-history entries."),
    "webaddress": "",
    "objects": [
        hotkey_obj(HK_Q), ua_obj(UA_Q, "Paste-reflow as Quote"),
        hotkey_obj(HK_R), ua_obj(UA_R, "Paste-reflow (raw)"),
        script_obj(S_Q, True), script_obj(S_R, False), clip_obj,
    ],
    "connections": {
        HK_Q: [conn(S_Q)], UA_Q: [conn(S_Q)],
        HK_R: [conn(S_R)], UA_R: [conn(S_R)],
        S_Q: [conn(CLIP)], S_R: [conn(CLIP)],
    },
    "uidata": {
        HK_Q: {"xpos": 30, "ypos": 50}, UA_Q: {"xpos": 30, "ypos": 150},
        HK_R: {"xpos": 30, "ypos": 290}, UA_R: {"xpos": 30, "ypos": 390},
        S_Q: {"xpos": 280, "ypos": 100}, S_R: {"xpos": 280, "ypos": 340},
        CLIP: {"xpos": 540, "ypos": 220},
    },
    "userconfigurationconfig": [
        {
            "type": "textfield",
            "variable": "SCRIPT_PATH",
            "label": "paste-reflow.py path",
            "description": "Absolute path to paste-reflow.py in your flavin-tools checkout.",
            "config": {
                "default": SCRIPT_PATH_DEFAULT,
                "placeholder": "/path/to/paste-reflow.py",
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
