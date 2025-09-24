#!/bin/bash
# stop_cluster.sh - Stop SyncPay cluster

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🛑 Stopping SyncPay Distributed Payment System${NC}"
echo -e "${YELLOW}===============================================${NC}"

# Kill processes by pattern
echo -e "   ${YELLOW}🔪 Killing SyncPay processes...${NC}"
pkill -f "python.*main.py" 2>/dev/null && echo -e "   ${GREEN}✅ Processes stopped${NC}" || echo -e "   ${YELLOW}⚠️  No processes found${NC}"

# Clean up PID file
if [ -f .pids ]; then
    rm .pids
    echo -e "   ${GREEN}✅ Cleaned up PID file${NC}"
fi

# Check if any processes are still running
if pgrep -f "python.*main.py" > /dev/null; then
    echo -e "   ${RED}❌ Some processes still running, force killing...${NC}"
    pkill -9 -f "python.*main.py" 2>/dev/null
else
    echo -e "   ${GREEN}✅ All SyncPay processes stopped successfully${NC}"
fi

echo -e "\n${GREEN}🎉 SyncPay cluster stopped!${NC}"