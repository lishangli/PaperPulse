#!/bin/bash
# PaperPulse 快速启动脚本

set -e

cd "$(dirname "$0")"

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 检查配置
if [ ! -f "config.yaml" ]; then
    if [ -f "config.example.yaml" ]; then
        echo "⚠️  配置文件不存在，从示例创建..."
        cp config.example.yaml config.yaml
        echo "✅ 已创建 config.yaml，请编辑并设置 API key"
        echo ""
    else
        echo "❌ 配置文件不存在"
        exit 1
    fi
fi

# 检查 API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY 未设置"
    echo "   export OPENAI_API_KEY='sk-...'"
    echo ""
fi

# 执行命令
case "${1:-monitor}" in
    monitor)
        shift
        python -m paperpulse.cli monitor "$@"
        ;;
    collect)
        shift
        python -m paperpulse.cli collect "$@"
        ;;
    download)
        shift
        python -m paperpulse.cli download "$@"
        ;;
    convert)
        shift
        python -m paperpulse.cli convert "$@"
        ;;
    analyze)
        shift
        python -m paperpulse.cli analyze "$@"
        ;;
    ideas)
        shift
        python -m paperpulse.cli ideas "$@"
        ;;
    trends)
        shift
        python -m paperpulse.cli trends "$@"
        ;;
    report)
        shift
        python -m paperpulse.cli report "$@"
        ;;
    obsidian)
        shift
        python -m paperpulse.cli obsidian "$@"
        ;;
    research)
        shift
        python -m paperpulse.cli research "$@"
        ;;
    db)
        python -m paperpulse.cli db
        ;;
    doctor)
        python -m paperpulse.cli doctor
        ;;
    daemon)
        python -m paperpulse.cli daemon-cmd --daemon
        ;;
    help|--help|-h)
        echo "PaperPulse - 论文监控与 IDEA 推荐系统"
        echo ""
        echo "用法: ./run.sh <command> [options]"
        echo ""
        echo "命令:"
        echo "  monitor     运行完整监控流程"
        echo "  collect     收集论文"
        echo "  download    下载文档 (PDF/LaTeX)"
        echo "  convert     转换 PDF → Markdown"
        echo "  analyze     分析论文"
        echo "  ideas       生成 IDEA"
        echo "  trends      查看趋势"
        echo "  report      生成报告"
        echo "  obsidian    同步到 Obsidian"
        echo "  research    启动研究"
        echo "  db          数据库统计"
        echo "  doctor      环境检查"
        echo "  daemon      启动守护进程"
        ;;
    *)
        python -m paperpulse.cli "$@"
        ;;
esac