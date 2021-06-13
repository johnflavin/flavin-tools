#!/bin/bash

die(){
    echo >&2 "$@"
    exit 1
}

# Get title and message
title="$1"
message="$2"

if [[ -z "${title}" || -z "${message}" ]]; then
    die "Usage: notify \"title\" \"message\""
fi

# Get API and user tokens
if [ ! -e ~/.notify ]; then
    die "Set Pushover API_TOKEN and USER_TOKEN in ~/.notify"
fi

source ~/.notify

if [[ -z "${API_TOKEN}" || -z "${USER_TOKEN}" ]]; then
    die "Set Pushover API_TOKEN and USER_TOKEN in ~/.notify"
fi

# POST to send notification
req=$(curl -s -X POST --form token=${API_TOKEN} --form user=${USER_TOKEN} --form title="${title}" --form message="${message}" https://api.pushover.net/1/messages.json)

# Check if it worked and exit
status=$(jq .status <<< $req)
if ((status==1)); then
    exit 0
else
    die "Failed to send notification: ${req}"
fi