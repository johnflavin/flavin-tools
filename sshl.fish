function sshl -d "ssh for a login shell (runs different args than I would want for automated ssh)"
    ssh -o RequestTTY=yes -o RemoteCommand="/usr/bin/fish -l" $argv
end
