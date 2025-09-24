#!/bin/bash
# run_cluster.sh - SyncPay Distributed Payment System Demo

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
DEMO_MODE=${1:-"interactive"}  # interactive, auto, or test
STARTUP_TIMEOUT=30
TEST_TIMEOUT=10

echo -e "${BLUE}🚀 SyncPay Distributed Payment System Demo${NC}"
echo -e "${BLUE}================================================${NC}"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Stopping SyncPay cluster...${NC}"
    pkill -f "python.*main.py" 2>/dev/null || true
    rm -f .pids
    exit 0
}

# Handle Ctrl+C gracefully
trap cleanup SIGINT SIGTERM

# Function to check if a service is ready
wait_for_service() {
    local port=$1
    local name=$2
    local max_attempts=30
    
    echo -e "   ${YELLOW}⏳ Waiting for $name to start...${NC}"
    
    for i in $(seq 1 $max_attempts); do
        if curl -s http://localhost:$port/health >/dev/null 2>&1; then
            echo -e "   ${GREEN}✅ $name is ready!${NC}"
            return 0
        fi
        sleep 1
    done
    
    echo -e "   ${RED}❌ $name failed to start within ${max_attempts}s${NC}"
    return 1
}

# Function to get leader node
get_leader() {
    for port in 5000 5001 5002; do
        if leader_status=$(curl -s http://localhost:$port/status 2>/dev/null); then
            if echo "$leader_status" | grep -q '"is_leader":true'; then
                echo $port
                return 0
            fi
        fi
    done
    return 1
}

# Function to display cluster status
show_cluster_status() {
    echo -e "\n${CYAN}📊 CLUSTER STATUS:${NC}"
    echo -e "${CYAN}==================${NC}"
    
    local leader_port=$(get_leader)
    
    for port in 5000 5001 5002; do
        local node_name="node$((port - 4999))"
        if status=$(curl -s http://localhost:$port/health 2>/dev/null); then
            local is_leader="false"
            if [ "$port" = "$leader_port" ]; then
                is_leader="true"
            fi
            
            local txn_count=$(echo "$status" | grep -o '"transaction_count":[0-9]*' | cut -d':' -f2)
            local status_icon="✅"
            local leader_icon=""
            
            if [ "$is_leader" = "true" ]; then
                leader_icon=" 👑 LEADER"
                status_icon="🏆"
            fi
            
            echo -e "   $status_icon $node_name (port $port)$leader_icon - Transactions: $txn_count"
        else
            echo -e "   ❌ $node_name (port $port) - OFFLINE"
        fi
    done
}

# Function to run payment test
run_payment_test() {
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        echo -e "   ${RED}❌ No leader found - cluster not ready${NC}"
        return 1
    fi
    
    echo -e "\n${PURPLE}💳 PROCESSING TEST PAYMENT:${NC}"
    echo -e "${PURPLE}=============================${NC}"
    
    # Create payment JSON file for cleaner curl
    cat > /tmp/payment.json << EOF
{
    "amount": 150.75,
    "sender": "alice",
    "receiver": "bob"
}
EOF
    
    echo -e "   ${YELLOW}💰 Sending \$150.75 from alice to bob...${NC}"
    
    if response=$(timeout $TEST_TIMEOUT curl -s -X POST \
        http://localhost:$leader_port/payment \
        -H "Content-Type: application/json" \
        -d @/tmp/payment.json 2>/dev/null); then
        
        if echo "$response" | grep -q '"status":"success"'; then
            local txn_id=$(echo "$response" | grep -o '"transaction_id":"[^"]*"' | cut -d'"' -f4)
            echo -e "   ${GREEN}✅ Payment successful! Transaction ID: $txn_id${NC}"
            
            # Wait for replication
            sleep 2
            show_cluster_status
            
        else
            local error=$(echo "$response" | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
            echo -e "   ${YELLOW}⚠️  Payment response: $error${NC}"
        fi
    else
        echo -e "   ${RED}❌ Payment request timed out or failed${NC}"
    fi
    
    rm -f /tmp/payment.json
}

# Function to run stress test
run_stress_test() {
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        echo -e "   ${RED}❌ No leader found - cannot run stress test${NC}"
        return 1
    fi
    
    echo -e "\n${PURPLE}⚡ STRESS TEST (5 concurrent payments):${NC}"
    echo -e "${PURPLE}======================================${NC}"
    
    # Run 5 payments concurrently
    for i in {1..5}; do
        (
            sleep 0.$i  # Stagger requests slightly
            curl -s -X POST http://localhost:$leader_port/payment \
                -H "Content-Type: application/json" \
                -d "{\"amount\": $((100 + i * 10)).50, \"sender\": \"user$i\", \"receiver\": \"merchant$i\"}" \
                2>/dev/null | grep -q '"status":"success"' && echo -e "   ${GREEN}✅ Payment $i succeeded${NC}" || echo -e "   ${RED}❌ Payment $i failed${NC}"
        ) &
    done
    
    wait  # Wait for all background jobs
    
    # Show final status
    sleep 2
    show_cluster_status
}

# Function to demonstrate fault tolerance
demo_fault_tolerance() {
    echo -e "\n${RED}💥 FAULT TOLERANCE TEST:${NC}"
    echo -e "${RED}=========================${NC}"
    
    # Find a non-leader node to kill
    local leader_port=$(get_leader)
    local victim_port=""
    
    for port in 5000 5001 5002; do
        if [ "$port" != "$leader_port" ]; then
            victim_port=$port
            break
        fi
    done
    
    if [ -n "$victim_port" ]; then
        local victim_node="node$((victim_port - 4999))"
        echo -e "   ${YELLOW}🔪 Killing $victim_node (port $victim_port)...${NC}"
        
        # Kill the specific node process
        pkill -f "main.py node$((victim_port - 4999))" 2>/dev/null || true
        
        sleep 3
        show_cluster_status
        
        echo -e "   ${CYAN}🧪 Testing payment processing with one node down...${NC}"
        run_payment_test
        
        # Restart the killed node
        echo -e "   ${GREEN}🔄 Restarting $victim_node...${NC}"
        cd src
        source ../syncpay_env/bin/activate
        python3 main.py "node$((victim_port - 4999))" > "../logs/node$((victim_port - 4999)).log" 2>&1 &
        cd ..
        
        wait_for_service $victim_port "$victim_node"
        sleep 3
        show_cluster_status
    fi
}

# Kill any existing processes
echo -e "${YELLOW}🧹 Cleaning up existing processes...${NC}"
pkill -f "python.*main.py" 2>/dev/null || true
sleep 2

# Create logs directory
mkdir -p logs

# Start the cluster
echo -e "\n${GREEN}🏗️  Starting 3-node SyncPay cluster...${NC}"
cd src

echo -e "   ${BLUE}🟦 Starting Node 1 (Primary)...${NC}"
source ../syncpay_env/bin/activate
python3 main.py node1 > ../logs/node1.log 2>&1 &
NODE1_PID=$!

sleep 3

echo -e "   ${BLUE}🟩 Starting Node 2 (Replica)...${NC}"
source ../syncpay_env/bin/activate
python3 main.py node2 > ../logs/node2.log 2>&1 &
NODE2_PID=$!

sleep 3

echo -e "   ${BLUE}🟪 Starting Node 3 (Replica)...${NC}"
source ../syncpay_env/bin/activate
python3 main.py node3 > ../logs/node3.log 2>&1 &
NODE3_PID=$!

cd ..

# Save PIDs
echo "$NODE1_PID $NODE2_PID $NODE3_PID" > .pids

# Wait for all services to be ready
echo -e "\n${YELLOW}⏳ Waiting for cluster initialization...${NC}"
wait_for_service 5000 "Node 1" || exit 1
wait_for_service 5001 "Node 2" || exit 1  
wait_for_service 5002 "Node 3" || exit 1

# Wait for leader election
echo -e "   ${YELLOW}⏳ Waiting for leader election...${NC}"
sleep 5

# Show initial status
show_cluster_status

# Demo modes
case $DEMO_MODE in
    "auto")
        echo -e "\n${CYAN}🎬 Running automated demo...${NC}"
        run_payment_test
        run_stress_test
        demo_fault_tolerance
        echo -e "\n${GREEN}🎉 Demo completed! Press Ctrl+C to stop cluster.${NC}"
        wait
        ;;
    "test")
        run_payment_test
        cleanup
        ;;
    "interactive"|*)
        echo -e "\n${CYAN}🎮 INTERACTIVE DEMO MODE${NC}"
        echo -e "${CYAN}========================${NC}"
        echo -e "Available commands:"
        echo -e "   ${YELLOW}1${NC} - Run payment test"
        echo -e "   ${YELLOW}2${NC} - Run stress test"
        echo -e "   ${YELLOW}3${NC} - Demo fault tolerance"
        echo -e "   ${YELLOW}s${NC} - Show cluster status"
        echo -e "   ${YELLOW}l${NC} - Show live logs"
        echo -e "   ${YELLOW}q${NC} - Quit"
        echo ""
        
        while true; do
            echo -e -n "${CYAN}syncpay-demo>${NC} "
            read choice
            
            case $choice in
                "1")
                    run_payment_test
                    ;;
                "2")
                    run_stress_test
                    ;;
                "3")
                    demo_fault_tolerance
                    ;;
                "s")
                    show_cluster_status
                    ;;
                "l")
                    echo -e "${YELLOW}Press Ctrl+C to stop viewing logs${NC}"
                    tail -f logs/node*.log
                    ;;
                "q"|"quit"|"exit")
                    cleanup
                    ;;
                *)
                    echo -e "${YELLOW}Invalid option. Use 1, 2, 3, s, l, or q${NC}"
                    ;;
            esac
            echo ""
        done
        ;;
esac
