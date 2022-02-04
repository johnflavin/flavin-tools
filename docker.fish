function docker --wraps='lima nerdctl' --description 'alias docker=lima nerdctl'
  lima nerdctl $argv; 
end
