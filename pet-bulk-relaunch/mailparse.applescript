tell application "Mail"
    set messagelist to messages of mailbox "PET Bulk Relaunch" of account "NRG Exchange"
    set argstring to ""
    repeat with m in messagelist
        if not read status of m then
            set s to subject of m as rich text
            if s contains "64 bit PET Build complete" then
                set argstring to argstring & "OK " & item 3 of words of s & linefeed
            else if s contains "Processing failed for" then
                set argstring to argstring & "NO " & item 6 of words of s & linefeed
            end if
        end if
    end repeat
    return argstring
end tell

--run this in terminal
--osascript -e 'tell application "Mail"' -e 'set messagelist to messages of mailbox "PET Bulk Relaunch" of account "NRG Exchange"' -e 'set argstring to ""' -e 'repeat with m in messagelist' -e 'if not read status of m then' -e 'set s to subject of m as rich text' -e 'if s contains "64 bit PET Build complete" then' -e 'set argstring to argstring & "OK " & item 3 of words of s & linefeed' -e 'else if s contains "Processing failed for" then' -e 'set argstring to argstring & "NO " & item 6 of words of s & linefeed' -e 'end if' -e 'end if' -e 'end repeat' -e 'return argstring' -e 'end tell' | xargs -L 1 python pet-fill.py