# Flavin Tools

Scripts and stuff

## la.fish
Creates `la` alias for `ls -lA` in fish.

## 10-keychain.py
An ipython startup script. (Named starting with `10` because
it doesn't need to be particularly early in the startup sequence.)

Defines a function for getting secrets from the keychain.

## conda-develop.sh
A replacement for the `conda develop` command that doesn't work.

Reads a `meta.yaml` for its dependency requirements and installs
them into a new environment.

This is a pretty quick, rough implementation. It doesn't have a
lot of the features one would expect from, like, an official 
`conda develop` CLI. But it works for me so I'll just run with it.

## my-ip.sh
Find external IP address.

Loads the website [ifconfig.me/ip](ifconfig.me/ip), which does nothing but returns the IP address
of your request.

My script uses the `http` command from [httpie](https://github.com/httpie)
but you can swap it with `curl` or whatever CLI you like to use for HTTP.

## window-move.py

This is a script I found on the Super User Stack Exchange site. I was trying to solve a problem that my OS had opened a window where it was "Verifying" an application I was installing, but the verifying process was stuck. I didn't know how to close this window because I didn't know what process it belonged to.

After a bit of googling I found this question and answer: [Super User - How to identify which process is running which window in Mac OS X?](https://superuser.com/questions/902869/how-to-identify-which-process-is-running-which-window-in-mac-os-x). Several of the answers conained python scripts that used the system-installed python and the `Quartz` library to get information about the open windows. The one I settled on as the easiest to use did a two-phase operation:

1. Print out a bunch of info about the open windows
2. Wait for a few seconds, during which time you need to manually move the window in question. It uses that change of window position to identify which window you're interested in and print out info specific to it.

That was enough for me to identify the window and its process. Given the process ID I was able to kill it and the window went away.

## notify.sh
Send notifications to the [Pushover](https://pushover.net) API.

I mostly use it to ping my phone at the end of some long-running process like transcoding a movie.

## homebrew-update.sh
Update everything I have installed from homebrew.

I typically run this via a launch agent, which I have also included in the `LaunchAgents` directory.
It runs every hour to keep everything up-to-date.

### Known limitations
The launch agent hard-codes the path to the script and the path to the output logs on my machine.
It is certainly not directly applicable to anyone else.
But it can easily be adapted to another environment.

Perhaps one day I'll see if I can figure out a way to make those translatable elsewhere.
