#!/bin/bash

# Find external address from ifconfig.me/ip
# Uses http command from httpie https://github.com/httpie
#  but you can swap it with curl or whatever you want to use for HTTP.

http -b ifconfig.me/ip
