#!/bin/bash

TMPSQL=./tmp.sql
HOST=`hostname | cut -d. -f1`
export PGPASSFILE=/data/CNDA/home/.pgpass

if [ -z $1 ]; then
   echo No user id provided.
   exit 1
else
   echo "insert into xdat_r_xdat_role_type_assign_xdat_user (xdat_user_xdat_user_id,xdat_role_type_role_name) values ((select xdat_user_id from xdat_user where login = '$1'),'Administrator');" > ${TMPSQL}
   echo "update xdat_user set enabled=1, verified=1 where login = '$1';" >> ${TMPSQL}
   echo "delete from xs_item_cache where contents like '%$1%';" >> ${TMPSQL}
   psql -h ${HOST} -U ${HOST} -d ${HOST} -f ${TMPSQL}
   rm ${TMPSQL} 
fi 
