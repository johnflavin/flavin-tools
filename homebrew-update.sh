#!/bin/bash
export PATH=/usr/local/bin:/usr/local/sbin:$PATH
DATE=$(date)
echo $DATE
echo $DATE >&2
ping -o github.com > /dev/null || exit 1
brew update
brew doctor
brew upgrade
brew cleanup -s
echo ""