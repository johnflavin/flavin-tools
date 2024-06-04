#!/usr/bin/env python3

"""
Take in a SafeLink URL copied from Outlook, extract the target URL, and spit that out.

Intended use: 
1. Copy a URL from outlook
2. Run
    pbpaste | safelink-extractor.py | pbcopy
3. Now you have the extracted URL on the clipboard.
"""

import sys
from urllib.parse import urlparse, parse_qs

def parse_url_query(safelink_url: str) -> str:
    parsed_safelink_url = urlparse(safelink_url)
    safelink_query_params = parse_qs(parsed_safelink_url.query)

    return safelink_query_params.get('url', [''])[0]


def find_input(argv, stdin) -> str:
    if len(argv) > 1:
        return argv[1]
    else:
        return stdin.read()


def main(argv, stdin) -> int:
    safelink_url = find_input(argv, stdin)
    url = parse_url_query(safelink_url)
    print(url)
    
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv, sys.stdin))
