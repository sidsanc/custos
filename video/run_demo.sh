#!/bin/bash
# Fresh end-to-end run, plain-text output captured for the video.
cd /d/Projects/custos
export PYTHONUNBUFFERED=1 COLUMNS=100 NO_COLOR=1 TERM=dumb
python seed.py > video/out_seed.txt 2>&1
python referee.py > video/out_referee.txt 2>&1 &
REF=$!
until grep -q "watching" video/out_referee.txt; do sleep 2; done
python redteam.py > video/out_redteam.txt 2>&1
python agent.py 5 > video/out_agent.txt 2>&1
python retire.py > video/out_retire.txt 2>&1
kill $REF
echo DONE > video/done.txt
