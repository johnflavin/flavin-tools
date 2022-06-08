# Homebrew update

Notes on updating homebrew installed tools

## 2022-06-06 refactor

Currently I'm not updating in the background on my FW M1 MBP. I need to start doing this.
Because of the sophos antivirus, any operations which modify lots of files take about 5-10x
longer than they otherwise would. And updating the awscli install is one of those opeartions!

Currently I have a bash script do the update. Which is... fine. Maybe I'll keep that. I don't know.

Issue is that updating docker requires a password. So I will need to work out a way to do that noninteractively.

I found a discussion around this issue: https://github.com/orgs/Homebrew/discussions/3199.
The OP is quite unpleasant! I do not like reading the thread. But there is good information nonetheless.
Set `NONINTERACTIVE=1` to tell homebrew it's in noninteractive mode.
Then set `SUDO_ASKPASS=<some command>` to a command that will produce the password.
See this SO question [How to setup a SUDO_ASKPASS environment variable?](https://stackoverflow.com/q/12608293)
for more discussion about that environment variable and how it works.

The plan is to store the password in the keychain. Set it with this:

    security add-generic-password -a johnflavin -s homebrew-update -w

and have `SUDO_ASKPASS` retrieve it with this:

    security find-generic-password -a johnflavin -s homebrew-update -w

...

Actually I need to put that into a script and set `SUDO_ASKPASS` to the path to that script. It can't be an arbitrary command in a string.