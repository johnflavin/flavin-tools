function pluginsync -d "Build + sync XNAT plugin jar to a dev machine. Pass machine's ssh alias as arg."
    argparse -N 1 -X 1 no-start-tomcat -- $argv
    or return 1

    set machine $argv[1]
    or return 1

    if not test -f gradlew
        echo "No gradlew found. Execute this from the repo directory." >&2
        return 1
    end

    ./gradlew :clean :xnatPluginJar
    and set jar (ls build/libs/*-xpl.jar)


    if test (count $jar) -ne 1
        echo "Found more than one plugin jar\n" (string join \n $jar) >&2
        return 1
    end

    # Find the name of the root project, i.e. the name of the jar before the version and all that
    # The string match --regex function will automatically set the value of a match to a variable named for a capture group,
    #  so this gives us a rootProject variable.
    ./gradlew properties | grep rootProject | string match --regex "'(?<rootProject>[^']+)'"
    if not set -q rootProject
        echo "Could not find root project name from gradle properties"
        return 1
    end

    rsync -azv $jar $machine:/home/johnflavin/
    or return $status

    set jar (basename $jar)
    set plugins /home/xnat/plugins
    set jarWildcardAbs "$plugins/$rootProject*.jar"
    set _command 'sh -c \'set -x && systemctl stop tomcat && rm -f '$jarWildcardAbs' && [ -z "$(ls '$jarWildcardAbs')" ] && cp /home/johnflavin/'$jar' '$plugins'/ && chown -R tomcat:tomcat '$plugins'/'
    if set -q _flag_no_start_tomcat
        set _command $_command '\''
    else
        set _command $_command ' && systemctl start tomcat\''
    end

    ssh $machine sudo $_command
    or return $status
end
