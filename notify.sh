#!/bin/bash

usage_msg="Usage: notify \"title\" \"message\""

# Get title and message from input args
title="${1:?$usage_msg}"
message="${2:?$usage_msg}"

# Get API and user tokens from keychain
API_TOKEN=$(security find-generic-password -s pushover -a "api token" -w)
: ${API_TOKEN:?Add pushover API token to keychain with 'security add-generic-password -s pushover -a "api token" -w <api token>'}
USER_TOKEN=$(security find-generic-password -s pushover -a "user token" -w)
: ${USER_TOKEN:?Add pushover user token to keychain with 'security add-generic-password -s pushover -a "user token" -w <user token>'}

# POST to send notification
req=$(http --form POST https://api.pushover.net/1/messages.json token=${API_TOKEN} user=${USER_TOKEN} title="${title}" message="${message}")

# Check if it worked and exit
status=$(jq .status <<< $req)
if ((status==1)); then
    exit 0
else
    echo >&2 "Failed to send notification: ${req}"
    exit 1
fi
