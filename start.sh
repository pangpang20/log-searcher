#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"
LOG_FILE="$SCRIPT_DIR/logs/app.log"

check_and_install_deps() {
    echo "检查依赖..."
    bash "$SCRIPT_DIR/libs/install.sh"
    if [ $? -ne 0 ]; then
        echo "依赖检查失败，请先安装依赖"
        return 1
    fi
    return 0
}

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "应用已在运行中 (PID: $PID)"
            return 1
        fi
    fi

    echo "正在启动日志搜索系统..."
    cd "$SCRIPT_DIR"

    #check_and_install_deps
    #if [ $? -ne 0 ]; then
    #    return 1
    #fi

    nohup python3 app.py > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"

    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
        echo "启动成功! (PID: $PID)"
        echo "访问地址: http://0.0.0.0:5001"
    else
        echo "启动失败，请查看日志: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    PORT=5001

    # 先尝试通过 PID 文件停止
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "正在停止应用 (PID: $PID)..."
            kill "$PID"
            sleep 2
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID"
            fi
            echo "已停止"
            rm -f "$PID_FILE"
            return 0
        fi
        rm -f "$PID_FILE"
    fi

    # PID 文件不存在或进程不在，尝试通过端口查找
    PID=$(lsof -ti :"$PORT" 2>/dev/null | head -1)
    if [ -n "$PID" ]; then
        echo "正在停止端口 $PORT 上的进程 (PID: $PID)..."
        kill "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        echo "已停止"
        return 0
    fi

    echo "应用未在运行"
    return 1
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "应用正在运行 (PID: $PID)"
            return 0
        fi
    fi
    echo "应用未在运行"
    return 1
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
