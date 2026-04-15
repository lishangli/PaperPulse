#!/bin/bash
# PaperPulse 每日自动化任务
# 运行时间: 每天 8:00
# 输出日志: logs/

set -e

# 动态获取脚本目录（不硬编码路径）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAPERPULSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 日志目录（支持环境变量覆盖）
LOG_DIR="${PAPERPULSE_LOG_DIR:-$PAPERPULSE_DIR/logs}"
DATE=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/daily_$DATE.log"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 设置环境（动态 PATH）
export PATH="${PATH}:${HOME}/.local/bin"
cd "$PAPERPULSE_DIR"

# 运行每日任务
echo "========================================" >> "$LOG_FILE"
echo "PaperPulse Daily Reading - $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "Working directory: $PAPERPULSE_DIR" >> "$LOG_FILE"

paperpulse auto-daily 2>&1 | tee -a "$LOG_FILE"

echo "" >> "$LOG_FILE"
echo "Completed at $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 发送简单通知 (可选)
# notify-send "PaperPulse" "Daily reading completed. Check logs for details."