#!/bin/bash
# ============================================================
# SSDP Relay 运维管理脚本
# ============================================================
# 用法: ./ssdp_relay_manage.sh
# 功能: 启动/停止/重启/检查 SSDP 发现中继服务
# 语言: 交互式中英双语菜单
# ============================================================

set -e

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RELAY_SCRIPT="${SCRIPT_DIR}/ssdp_relay.py"
PID_FILE="${SCRIPT_DIR}/ssdp_relay.pid"
LOG_FILE="${SCRIPT_DIR}/ssdp_relay.log"
DEFAULT_PORT=1901
DEFAULT_BIND="0.0.0.0"

# ============================================================
# 多语言文本
# ============================================================
declare -A TEXTS_ZH
TEXTS_ZH=(
    ["title"]="╔══════════════════════════════════════╗"
    ["title2"]="║    SSDP 发现中继 - 运维管理工具      ║"
    ["title3"]="╚══════════════════════════════════════╝"
    ["menu_lang"]="请选择语言 / Select Language:"
    ["lang_zh"]="1) 中文"
    ["lang_en"]="2) English"
    ["lang_prompt"]="输入选项 [1-2]: "
    ["invalid_choice"]="无效选项,请重试"
    ["menu_action"]="请选择操作:"
    ["action_start"]="1) 启动服务 (Start)"
    ["action_stop"]="2) 停止服务 (Stop)"
    ["action_restart"]="3) 重启服务 (Restart)"
    ["action_status"]="4) 查看状态 (Status)"
    ["action_exit"]="0) 退出 (Exit)"
    ["action_prompt"]="输入选项 [0-4]: "
    ["checking"]="正在检查服务状态..."
    ["running"]="服务正在运行 (PID: "
    ["not_running"]="服务未运行"
    ["starting"]="正在启动 SSDP 中继服务..."
    ["started"]="服务已启动 (PID: "
    ["start_failed"]="启动失败,请检查日志: "
    ["stopping"]="正在停止服务..."
    ["stopped"]="服务已停止"
    ["stop_failed"]="停止失败,尝试强制终止..."
    ["force_kill"]="强制终止进程..."
    ["not_found"]="未找到运行中的服务"
    ["restarting"]="正在重启服务..."
    ["restarted"]="服务已重启"
    ["select_iface"]="检测到以下网络接口:"
    ["iface_prompt"]="选择接口编号 [回车自动选择]: "
    ["no_iface"]="未找到可用网络接口"
    ["auto_iface"]="自动选择接口"
    ["selected_iface"]="已选择接口: "
    ["port_prompt"]="输入 HTTP 端口 [默认 ${DEFAULT_PORT}]: "
    ["selected_port"]="已设置端口: "
    ["log_tail"]="最新日志:"
    ["healthy"]="健康检查: 正常"
    ["unhealthy"]="健康检查: 异常"
    ["devices_found"]="已发现设备数: "
    ["bye"]="再见!"
    ["hint_background"]="提示: 服务在后台运行。按 Enter 返回菜单，或 Ctrl+C 退出。"
    ["hint_start_done"]="服务已启动并在后台运行，您现在可以安全关闭此终端窗口。"
    ["wait_prompt"]="按 Enter 键继续..."
    ["go_menu"]="返回主菜单"
    ["go_exit"]="退出 (服务继续在后台运行)"
    ["choose_next"]="接下来您想做什么？"
    ["error_no_python"]="错误: 未找到 python3,请先安装 Python 3"
    ["error_no_relay"]="错误: 未找到 ssdp_relay.py"
    ["error_no_pid"]="PID 文件不存在"
)

declare -A TEXTS_EN
TEXTS_EN=(
    ["title"]="╔══════════════════════════════════════╗"
    ["title2"]="║    SSDP Relay - Management Tool     ║"
    ["title3"]="╚══════════════════════════════════════╝"
    ["menu_lang"]="Select Language:"
    ["lang_zh"]="1) 中文"
    ["lang_en"]="2) English"
    ["lang_prompt"]="Enter choice [1-2]: "
    ["invalid_choice"]="Invalid choice, please retry"
    ["menu_action"]="Select action:"
    ["action_start"]="1) Start service"
    ["action_stop"]="2) Stop service"
    ["action_restart"]="3) Restart service"
    ["action_status"]="4) Check status"
    ["action_exit"]="0) Exit"
    ["action_prompt"]="Enter choice [0-4]: "
    ["checking"]="Checking service status..."
    ["running"]="Service is running (PID: "
    ["not_running"]="Service is not running"
    ["starting"]="Starting SSDP relay service..."
    ["started"]="Service started (PID: "
    ["start_failed"]="Start failed, check log: "
    ["stopping"]="Stopping service..."
    ["stopped"]="Service stopped"
    ["stop_failed"]="Stop failed, trying force kill..."
    ["force_kill"]="Force killing process..."
    ["not_found"]="No running service found"
    ["restarting"]="Restarting service..."
    ["restarted"]="Service restarted"
    ["select_iface"]="Detected network interfaces:"
    ["iface_prompt"]="Select interface number [Enter for auto]: "
    ["no_iface"]="No usable network interface found"
    ["auto_iface"]="Auto-select interface"
    ["selected_iface"]="Selected interface: "
    ["port_prompt"]="Enter HTTP port [default ${DEFAULT_PORT}]: "
    ["selected_port"]="Port set: "
    ["log_tail"]="Recent logs:"
    ["healthy"]="Health check: OK"
    ["unhealthy"]="Health check: FAIL"
    ["devices_found"]="Discovered devices: "
    ["bye"]="Bye!"
    ["hint_background"]="HINT: Service runs in background. Press Enter to return to menu, or Ctrl+C to exit."
    ["hint_start_done"]="Service is now running. You can safely close this terminal window if you started it in background mode."
    ["wait_prompt"]="Press Enter to continue..."
    ["go_menu"]="Return to main menu"
    ["go_exit"]="Exit (service keeps running in background)"
    ["choose_next"]="What would you like to do next?"
    ["error_no_python"]="Error: python3 not found, please install Python 3"
    ["error_no_relay"]="Error: ssdp_relay.py not found"
    ["error_no_pid"]="PID file does not exist"
)

# ============================================================
# 全局变量
# ============================================================
LANG="zh"
IFACE=""
PORT="${DEFAULT_PORT}"

# ============================================================
# 辅助函数
# ============================================================

function t() {
    local key="$1"
    if [ "${LANG}" = "zh" ]; then
        echo "${TEXTS_ZH[$key]}"
    else
        echo "${TEXTS_EN[$key]}"
    fi
}

function print_banner() {
    echo "$(t title)"
    echo "$(t title2)"
    echo "$(t title3)"
    echo ""
}

function check_prerequisites() {
    if ! command -v "${PYTHON_BIN}" &>/dev/null; then
        echo "$(t error_no_python)"
        exit 1
    fi
    if [ ! -f "${RELAY_SCRIPT}" ]; then
        echo "$(t error_no_relay)"
        exit 1
    fi
}

function detect_interfaces() {
    # 检测非回环的 IPv4 网络接口
    iface_list=()
    if command -v ip &>/dev/null; then
        while IFS= read -r line; do
            local ifname
            ifname=$(echo "$line" | awk '{print $2}')
            local ipaddr
            ipaddr=$(echo "$line" | awk '{print $4}')
            if [ -n "$ifname" ] && [ -n "$ipaddr" ]; then
                iface_list+=("${ifname}|${ipaddr}")
            fi
        done < <(ip -4 addr show 2>/dev/null | grep -E 'inet ' | grep -v '127\.')
    fi

    if [ ${#iface_list[@]} -eq 0 ] && command -v ifconfig &>/dev/null; then
        while IFS= read -r line; do
            local ifname
            ifname=$(echo "$line" | awk -F: '{print $1}')
            local ipaddr
            ipaddr=$(echo "$line" | awk '{print $2}' | awk '{print $2}')
            if [ -n "$ifname" ] && [ -n "$ipaddr" ] && [[ ! "$ipaddr" =~ ^127\. ]]; then
                iface_list+=("${ifname}|${ipaddr}")
            fi
        done < <(ifconfig 2>/dev/null | grep -E 'inet ' | grep -v '127\.')
    fi
}

function select_interface() {
    detect_interfaces

    if [ ${#iface_list[@]} -eq 0 ]; then
        echo "$(t no_iface)"
        IFACE=""
        return
    fi

    if [ ${#iface_list[@]} -eq 1 ]; then
        IFACE="${iface_list[0]%%|*}"
        echo "$(t selected_iface) ${IFACE} (${iface_list[0]##*|})"
        return
    fi

    echo "$(t select_iface)"
    local i=1
    for item in "${iface_list[@]}"; do
        local iname="${item%%|*}"
        local iaddr="${item##*|}"
        echo "  $i) ${iname} (${iaddr})"
        ((i++))
    done
    echo "  0) $(t auto_iface)"

    local choice
    read -rp "$(t iface_prompt)" choice
    if [ -n "$choice" ] && [ "$choice" != "0" ] && [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -le "${#iface_list[@]}" ]; then
        local idx=$((choice - 1))
        IFACE="${iface_list[$idx]%%|*}"
        echo "$(t selected_iface) ${IFACE}"
    else
        IFACE=""
        echo "$(t auto_iface)"
    fi
}

function select_port() {
    local input
    read -rp "$(t port_prompt)" input
    if [ -n "$input" ] && [ "$input" -gt 0 ] 2>/dev/null && [ "$input" -lt 65536 ] 2>/dev/null; then
        PORT="$input"
        echo "$(t selected_port) ${PORT}"
    fi
}

function wait_for_continue() {
    echo ""
    read -rp "$(t wait_prompt)" _
}

function after_action_prompt() {
    # 操作完成后询问下一步
    echo ""
    echo "$(t choose_next)"
    echo "  1) $(t go_menu)"
    echo "  0) $(t go_exit)"
    echo ""

    local choice
    read -rp "$(t action_prompt)" choice
    if [ "$choice" = "0" ]; then
        echo "$(t bye)"
        exit 0
    fi
    # 任何其他值返回菜单
}

function is_running() {
    if [ -f "${PID_FILE}" ]; then
        local pid
        pid=$(cat "${PID_FILE}" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # PID 文件过期,清理
        rm -f "${PID_FILE}"
    fi
    return 1
}

function do_start() {
    if is_running; then
        local pid
        pid=$(cat "${PID_FILE}")
        echo "$(t running) ${pid})"
        return
    fi

    select_interface
    select_port

    echo "$(t starting)"

    local cmd=("${PYTHON_BIN}" "${RELAY_SCRIPT}" "--port" "${PORT}" "--bind" "${DEFAULT_BIND}")
    if [ -n "${IFACE}" ]; then
        cmd+=("--interface" "${IFACE}")
    fi

    # 后台启动,日志写入文件
    nohup "${cmd[@]}" >> "${LOG_FILE}" 2>&1 &
    local pid=$!

    # 等待一下确认进程存活
    sleep 1
    if kill -0 "${pid}" 2>/dev/null; then
        echo "${pid}" > "${PID_FILE}"
        echo "$(t started) ${pid})"
        echo "  Log: ${LOG_FILE}"
        echo ""
        echo "$(t hint_background)"
        after_action_prompt
    else
        echo "$(t start_failed) ${LOG_FILE}"
        echo "--- last 5 lines ---"
        tail -5 "${LOG_FILE}" 2>/dev/null || true
        exit 1
    fi
}

function do_stop() {
    if ! is_running; then
        echo "$(t not_running)"
        return
    fi

    local pid
    pid=$(cat "${PID_FILE}")
    echo "$(t stopping) PID: ${pid}"

    # 优雅停止
    kill "${pid}" 2>/dev/null || true
    sleep 2

    if kill -0 "${pid}" 2>/dev/null; then
        echo "$(t stop_failed)"
        echo "$(t force_kill)"
        kill -9 "${pid}" 2>/dev/null || true
        sleep 1
    fi

    rm -f "${PID_FILE}"
    echo "$(t stopped)"
    after_action_prompt
}

function do_restart() {
    echo "$(t restarting)"
    if is_running; then
        do_stop
        sleep 1
    fi
    do_start
    echo "$(t restarted)"
}

function do_status() {
    echo "$(t checking)"

    if is_running; then
        local pid
        pid=$(cat "${PID_FILE}")
        echo "$(t running) ${pid})"

        # 健康检查
        local health_url="http://127.0.0.1:${PORT}/health"
        local health_resp
        health_resp=$(curl -s --max-time 3 "${health_url}" 2>/dev/null || echo "")
        if [ -n "${health_resp}" ]; then
            echo "$(t healthy)"
            local device_count
            device_count=$(echo "${health_resp}" | "${PYTHON_BIN}" -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('devices',0))" 2>/dev/null || echo "?")
            echo "$(t devices_found) ${device_count}"
        else
            echo "$(t unhealthy)"
        fi

        # 显示监听端口
        echo "  Port: ${PORT}"
        echo "  PID file: ${PID_FILE}"
        echo "  Log: ${LOG_FILE}"
        echo ""
        echo "$(t log_tail)"
        tail -5 "${LOG_FILE}" 2>/dev/null || echo "  (no logs)"
    else
        echo "$(t not_running)"
    fi
    after_action_prompt
}

# ============================================================
# 主菜单
# ============================================================

function select_language() {
    echo "$(t menu_lang)"
    echo "$(t lang_zh)"
    echo "$(t lang_en)"
    echo ""

    local choice
    read -rp "$(t lang_prompt)" choice
    case "$choice" in
        1) LANG="zh" ;;
        2) LANG="en" ;;
        *)
            echo "$(t invalid_choice)"
            select_language
            ;;
    esac
}

function main_menu() {
    print_banner
    echo "$(t menu_action)"
    echo "$(t action_start)"
    echo "$(t action_stop)"
    echo "$(t action_restart)"
    echo "$(t action_status)"
    echo "$(t action_exit)"
    echo ""

    local choice
    read -rp "$(t action_prompt)" choice
    case "$choice" in
        1) do_start ;;
        2) do_stop ;;
        3) do_restart ;;
        4) do_status ;;
        0)
            echo "$(t bye)"
            exit 0
            ;;
        *)
            echo "$(t invalid_choice)"
            ;;
    esac
    echo ""
}

# ============================================================
# 入口
# ============================================================

check_prerequisites

# 如果带命令行参数,直接执行（非交互模式）
case "${1:-}" in
    start)
        select_interface
        select_port
        do_start
        ;;
    stop)
        do_stop
        ;;
    restart)
        select_interface
        select_port
        do_restart
        ;;
    status)
        do_status
        ;;
    *)
        # 交互模式
        select_language
        while true; do
            main_menu
        done
        ;;
esac
