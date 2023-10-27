#!/bin/bash

username=${1?"Must provide username"}

cat << EOF
insert into xdat_r_xdat_role_type_assign_xdat_user (xdat_user_xdat_user_id,xdat_role_type_role_name) values ((select xdat_user_id from xdat_user where login = '$username'),'Administrator');
update xdat_user set enabled=1, verified=1 where login = '$username';
delete from xs_item_cache where contents like '%$username%';
EOF
