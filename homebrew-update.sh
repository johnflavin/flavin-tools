#!/bin/sh

ping -o github.com > /dev/null || exit 1

/opt/homebrew/bin/brew update && \
/opt/homebrew/bin/brew upgrade && \
/opt/homebrew/bin/brew upgrade --cask --greedy
