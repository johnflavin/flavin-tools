function gpg-kill -d "Kill gpg agent (it will restart on its own)"
    gpgconf --kill gpg-agent
end
