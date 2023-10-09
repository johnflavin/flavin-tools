function urlencode -d "URL encode string"
    python3 -c "import sys, urllib.parse as ul; input = sys.argv[1:] if sys.argv[1:] else (l.strip() for l in sys.stdin.readlines()); result=(ul.quote_plus(s) for s in input); print(' '.join(result))" $argv
end
