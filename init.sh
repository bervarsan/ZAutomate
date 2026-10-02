#!/bin/bash
# Sample script to start/restart zautomate

# write output as it happens, so a log shows exactly where a hang started
export PYTHONUNBUFFERED=1

killall python
# append, so restarting doesn't erase the log of what went wrong
app/za_automation.py >> za_automation.log 2>&1 &
app/za_cartmachine.py >> za_cartmachine.log 2>&1 &
app/za_studio.py >> za_studio.log 2>&1 &
