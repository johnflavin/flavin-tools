#!/bin/bash

systemctl stop tomcat
dropdb xnat -U xnat
createdb xnat -U xnat
rm -rf /opt/data/archive/* /opt/data/build/* /opt/data/cache/* /opt/data/prearchive/*
systemctl start tomcat
