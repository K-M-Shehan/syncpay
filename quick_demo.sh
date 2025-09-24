#!/bin/bash
# quick_demo.sh - Quick 30-second demo of SyncPay

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${BLUE}🚀 SyncPay 30-Second Demo${NC}"
echo -e "${BLUE}=========================${NC}"

# Run automated demo mode with timeout
timeout 30s ./run_cluster.sh auto || {
    echo -e "\n${YELLOW}⏰ Demo completed (30s timeout)${NC}"
    ./stop_cluster.sh
}

echo -e "\n${GREEN}🎉 Quick demo finished!${NC}"
echo -e "   ${YELLOW}For interactive demo: ./run_cluster.sh${NC}"
echo -e "   ${YELLOW}For full auto demo: ./run_cluster.sh auto${NC}"