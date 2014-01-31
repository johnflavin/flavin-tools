#!/bin/bash

N=$1

echo "source batch${N}.sourceme | tee -a batch${N}.log" | tee batch${N}.log
source batch${N}.sourceme | tee -a batch${N}.log
