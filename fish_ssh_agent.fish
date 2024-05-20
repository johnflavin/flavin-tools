# Copied + adapted from https://github.com/ivakyb/fish_ssh_agent/blob/master/functions/fish_ssh_agent.fish

function __ssh_agent_is_started -d "check if ssh agent is already started"
    if begin
            test -f $SSH_AGENT_ENV; and test -z "$SSH_AGENT_PID"
        end
        source $SSH_AGENT_ENV >/dev/null
    end

    if test -z "$SSH_AGENT_PID"
        return 1
    end

    pgrep ssh-agent
    return $status
end


function __ssh_agent_start -d "start a new ssh agent"
    ssh-agent -c | sed 's/^echo/#echo/' >$SSH_AGENT_ENV
    chmod 600 $SSH_AGENT_ENV
    source $SSH_AGENT_ENV >/dev/null
    true # suppress errors from setenv, i.e. set -gx
end


function fish_ssh_agent --description "Start ssh-agent if not started yet, or uses already started ssh-agent."
    if test -z "$SSH_AGENT_ENV"
        set -xg SSH_AGENT_ENV $HOME/.ssh/agentenv
    end

    if not __ssh_agent_is_started
        __ssh_agent_start
    end
end
