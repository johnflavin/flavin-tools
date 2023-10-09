function sshl -d "ssh for a login shell (runs different args than I would want for automated ssh)"
    ssh -o RequestTTY=yes -o RemoteCommand='sudo sh -c "cd /home/xnat && bash"' $argv
end
