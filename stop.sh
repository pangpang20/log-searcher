#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"
PORT=5001

stop_by_pid() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "正在停止应用 (PID: $PID)..."
        kill "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        rm -f "$PID_FILE"
        echo "已停止"
        return 0
    fi
    rm -f "$PID_FILE"
    return 1
}

stop_by_port() {
    PID=$(lsof -ti :"$PORT" 2>/dev/null | head -1)
    if [ -z "$PID" ]; then
        return 1
    fi
    echo "正在停止端口 $PORT 上的进程 (PID: $PID)..."
    kill "$PID"
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID"
    fi
    rm -f "$PID_FILE"
    echo "已停止"
    return 0
}

if stop_by_pid; then
    exit 0
fi

if stop_by_port; then
    exit 0
fi

echo "应用未在运行"
exit 1
