function xnatsync -d "Build + sync XNAT war to a dev machine. Pass machine's ssh alias as arg."
    test (count $argv) -eq 1
    or return 1

    set machine $argv[1]
    or return 1

    if not test -f gradlew
        echo "No gradlew found. Execute this from the xnat-web repo directory." >&2
        return 1
    end

    ./gradlew :war
    and set war (ls build/libs/xnat-web-*.war)


    if test (count $war) -ne 1
        echo "Found more than one war\n" (string join \n $war) >&2
        return 1
    end

    rsync -Pazv $war $machine:/home/johnflavin/
    and set war (basename $war)
    and ssh $machine "sudo systemctl stop tomcat && sudo rm -rf /home/xnat/tomcat/webapps/ROOT* && sudo cp /home/johnflavin/$war /home/xnat/tomcat/webapps/ROOT.war && sudo chown -R tomcat:tomcat /home/xnat/tomcat/webapps/ && sudo systemctl start tomcat"
    or return $status
end
