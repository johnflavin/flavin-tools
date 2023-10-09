function dropdb -d "Drop the database and delete all the data from a dev machine. Pass machine's ssh alias as arg."
    test (count $argv) -eq 1
    or return 1

    set machine $argv[1]
    or return 1

    set remoteDir /home/johnflavin
    set localDir "$HOME/repos/flavin-tools"
    set script "dropdb.sh"

    rsync -azv $localDir/$script $machine:$remoteDir
    and ssh $machine "sudo chmod a+x $remoteDir/$script && sudo $remoteDir/$script"
    or return $status
end
