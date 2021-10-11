function urldecode -d "URL decode string"
    python -c "import sys, urllib.parse as ul; input = sys.argv[1:] if sys.argv[1:] else sys.stdin.readlines(); result=[ul.unquote_plus(s.strip()) for s in input]; print(' '.join(result))" $argv
end
