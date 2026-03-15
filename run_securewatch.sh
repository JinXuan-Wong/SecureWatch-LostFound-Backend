#!/usr/bin/env bash

RESTART_SEC=3600   # restart interval (1 hour)

echo "=========================================="
echo "SecureWatch backend launcher starting..."
date
echo "=========================================="

while true
do
    echo "Starting Lost & Found backend..."
    date

    # start backend
    uvicorn backend.backend:app --host 0.0.0.0 --port $PORT &

    BACKEND_PID=$!
    echo "Backend PID: $BACKEND_PID"

    START_TIME=$(date +%s)

    while true
    do
        sleep 1

        # check if backend exited
        if ! kill -0 $BACKEND_PID 2>/dev/null
        then
            echo "Backend process exited unexpectedly."
            break
        fi

        NOW=$(date +%s)
        ELAPSED=$((NOW - START_TIME))

        if [ $ELAPSED -ge $RESTART_SEC ]
        then
            echo "Restart interval reached. Restarting backend..."
            kill -9 $BACKEND_PID
            break
        fi
    done

    echo "Restarting backend in 3 seconds..."
    sleep 3
done