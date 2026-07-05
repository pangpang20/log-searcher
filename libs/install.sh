#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_platform() {
    ARCH=$(uname -m)
    OS=$(cat /etc/os-release 2>/dev/null | grep "^NAME=" | cut -d'"' -f2)
    
    log_info "系统架构: $ARCH"
    log_info "操作系统: $OS"
    
    if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
        log_warn "检测到ARM架构，离线包可能不兼容"
        log_warn "如安装失败，请在ARM服务器上重新生成离线包"
    fi
    return 0
}

check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
        
        if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 7 ]; then
            log_info "Python版本检查通过: $PYTHON_VERSION"
            return 0
        else
            log_error "Python版本过低: $PYTHON_VERSION，需要 >= 3.7"
            return 1
        fi
    else
        log_error "未找到Python3，请先安装Python 3.7+"
        return 1
    fi
}

check_pip() {
    if command -v pip3 &>/dev/null; then
        log_info "pip3 已安装"
        return 0
    else
        log_error "未找到pip3，请先安装pip3"
        return 1
    fi
}

check_flask() {
    python3 -c "import flask" 2>/dev/null
    if [ $? -eq 0 ]; then
        FLASK_VERSION=$(python3 -c "import flask; print(flask.__version__)" 2>/dev/null)
        log_info "Flask 已安装: $FLASK_VERSION"
        return 0
    else
        log_warn "Flask 未安装"
        return 1
    fi
}

check_paramiko() {
    python3 -c "import paramiko" 2>/dev/null
    if [ $? -eq 0 ]; then
        PARAMIKO_VERSION=$(python3 -c "import paramiko; print(paramiko.__version__)" 2>/dev/null)
        log_info "Paramiko 已安装: $PARAMIKO_VERSION"
        return 0
    else
        log_warn "Paramiko 未安装"
        return 1
    fi
}

install_offline() {
    log_info "开始安装离线依赖..."
    
    if [ ! -d "$SCRIPT_DIR" ] || [ -z "$(ls -A $SCRIPT_DIR/*.whl 2>/dev/null)" ]; then
        log_error "离线依赖包不存在，请确保 libs 目录下有 .whl 文件"
        exit 1
    fi
    
    pip3 install --no-index --find-links="$SCRIPT_DIR" flask paramiko
    
    if [ $? -eq 0 ]; then
        log_info "离线依赖安装成功"
        return 0
    else
        log_error "离线依赖安装失败"
        return 1
    fi
}

main() {
    echo "=========================================="
    echo "     日志搜索系统 - 依赖检查与安装"
    echo "=========================================="
    echo ""
    
    check_platform
    
    echo ""
    log_info "检查Python环境..."
    check_python
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    log_info "检查pip环境..."
    check_pip
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    log_info "检查依赖包..."
    
    FLASK_OK=0
    PARAMIKO_OK=0
    
    check_flask && FLASK_OK=1
    check_paramiko && PARAMIKO_OK=1
    
    if [ $FLASK_OK -eq 1 ] && [ $PARAMIKO_OK -eq 1 ]; then
        echo ""
        log_info "=========================================="
        log_info "所有依赖已满足，无需安装"
        log_info "=========================================="
        exit 0
    fi
    
    echo ""
    log_warn "部分依赖缺失，开始安装离线依赖包..."
    echo ""
    
    install_offline
    
    if [ $? -eq 0 ]; then
        echo ""
        log_info "=========================================="
        log_info "依赖安装完成"
        log_info "=========================================="
    else
        echo ""
        log_error "=========================================="
        log_error "依赖安装失败，请检查错误信息"
        log_error "=========================================="
        exit 1
    fi
}

main "$@"