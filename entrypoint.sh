#!/bin/bash
set -e
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
sleep 1
export DISPLAY=:99
exec uvicorn main:app --host 0.0.0.0 --port 8080
