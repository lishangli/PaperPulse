#!/bin/bash
# PaperPulse + AutoResearchClaw 每日研究自动化
# 流程: collect → download → convert → synthesis → ideas → feasibility → experiment

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAPERPULSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AUTORESEARCH_DIR="${AUTORESEARCH_DIR:-$HOME/repos/AutoResearchClaw}"

LOG_DIR="${PAPERPULSE_LOG_DIR:-$PAPERPULSE_DIR/logs}"
DATE=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/research_$DATE.log"

mkdir -p "$LOG_DIR"
export PATH="${PATH}:${HOME}/.local/bin"

cd "$PAPERPULSE_DIR"

echo "========================================" >> "$LOG_FILE"
echo "PaperPulse + AutoResearchClaw Daily Research" >> "$LOG_FILE"
echo "Date: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# ========================================
# Phase 1: Paper Collection & Analysis
# ========================================
echo "" >> "$LOG_FILE"
echo "[Phase 1] Paper Collection & Analysis" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

paperpulse auto-daily 2>&1 | tee -a "$LOG_FILE"

# ========================================
# Phase 2: Synthesis Reports to Notion
# ========================================
echo "" >> "$LOG_FILE"
echo "[Phase 2] Sync to Notion" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

paperpulse notion sync ./reports/synthesis/ 2>&1 | tee -a "$LOG_FILE"

# ========================================
# Phase 3: Generate Research Ideas
# ========================================
echo "" >> "$LOG_FILE"
echo "[Phase 3] Generate Research Ideas" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Get recent synthesis reports
REPORTS_DIR="$PAPERPULSE_DIR/reports/synthesis"
IDEAS_DIR="$PAPERPULSE_DIR/reports/ideas"
mkdir -p "$IDEAS_DIR"

# Generate ideas from recent papers (last 3 days)
paperpulse ideas generate --days 3 --num 5 --output "$IDEAS_DIR/ideas_$DATE.json" 2>&1 | tee -a "$LOG_FILE"

# ========================================
# Phase 4: Feasibility Check
# ========================================
echo "" >> "$LOG_FILE"
echo "[Phase 4] Feasibility Check" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Check local environment
echo "Checking environment..." | tee -a "$LOG_FILE"

# GPU check
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "No GPU")
    echo "  GPU: $GPU_INFO" | tee -a "$LOG_FILE"
else
    echo "  GPU: Not available" | tee -a "$LOG_FILE"
fi

# Check AutoResearchClaw
if [ -d "$AUTORESEARCH_DIR" ]; then
    echo "  AutoResearchClaw: Available at $AUTORESEARCH_DIR" | tee -a "$LOG_FILE"
else
    echo "  AutoResearchClaw: Not found" | tee -a "$LOG_FILE"
fi

# ========================================
# Phase 5: Run AutoResearchClaw (if feasible idea found)
# ========================================
IDEAS_FILE="$IDEAS_DIR/ideas_$DATE.json"

if [ -f "$IDEAS_FILE" ]; then
    echo "" >> "$LOG_FILE"
    echo "[Phase 5] AutoResearchClaw Experiment" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    
    # Select top idea (highest score)
    TOP_IDEA=$(python3 -c "
import json
with open('$IDEAS_FILE') as f:
    ideas = json.load(f)
if ideas:
    # Sort by score if available, else take first
    sorted_ideas = sorted(ideas, key=lambda x: x.get('score', 0), reverse=True)
    top = sorted_ideas[0]
    print(top.get('title', 'Unknown'))
")
    
    if [ -n "$TOP_IDEA" ] && [ "$TOP_IDEA" != "Unknown" ]; then
        echo "  Top Idea: $TOP_IDEA" | tee -a "$LOG_FILE"
        
        # Run AutoResearchClaw with the idea
        cd "$AUTORESEARCH_DIR"
        
        # Check if researchclaw is available
        if command -v researchclaw &> /dev/null; then
            echo "  Starting AutoResearchClaw pipeline..." | tee -a "$LOG_FILE"
            
            # Run in full-auto mode for automation
            researchclaw run --topic "$TOP_IDEA" --auto-approve --output "$AUTORESEARCH_DIR/artifacts/daily_$DATE" 2>&1 | tee -a "$LOG_FILE" || true
            
            echo "  AutoResearchClaw completed" | tee -a "$LOG_FILE"
        else
            echo "  researchclaw CLI not found, skipping experiment" | tee -a "$LOG_FILE"
        fi
        
        cd "$PAPERPULSE_DIR"
    else
        echo "  No feasible idea found, skipping experiment" | tee -a "$LOG_FILE"
    fi
else
    echo "  No ideas generated, skipping experiment" | tee -a "$LOG_FILE"
fi

# ========================================
# Summary
# ========================================
echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "Daily Research Complete - $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "Logs: $LOG_FILE" >> "$LOG_FILE"

# Optional notification
# notify-send "PaperPulse Research" "Daily research pipeline completed."
