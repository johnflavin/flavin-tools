# Flavin Tools

Scripts and stuff

A lot of this is pretty old, from my previous job at WashU with the CNDA. I should probably organize that stuff.

## my-ip.sh
Find external IP address.

Loads the website [ifconfig.me/ip](ifconfig.me/ip), which does nothing but returns the IP address
of your request.

My script uses the `http` command from [httpie](https://github.com/httpie)
but you can swap it with `curl` or whatever CLI you like to use for HTTP.

## window-move.py

This is a script I found on the Super User Stack Echange site. I was trying to solve a problem that my OS had opened a window where it was "Verifying" an application I was installing, but the verifying process was stuck. I didn't know how to close this window because I didn't know what process it belonged to.

After a bit of googling I found this question and answer: [Super User - How to identify which process is running which window in Mac OS X?](https://superuser.com/questions/902869/how-to-identify-which-process-is-running-which-window-in-mac-os-x). Several of the answers conained python scripts that used the system-installed python and the `Quartz` library to get information about the open windows. The one I settled on as the easiest to use did a two-phase operation:

1. Print out a bunch of info about the open windows
2. Wait for a few seconds, during which time you need to manually move the window in question. It uses that change of window position to identify which window you're interested in and print out info specific to it.

That was enough for me to identify the window and its process. Given the process ID I was able to kill it and the window went away.
