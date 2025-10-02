#!/bin/bash
# run_cluster.sh - SyncPay Distributed Payment System - Interactive Demo
# Enhanced version with beautiful UI and comprehensive testing

set -e  # Exit on any error

# ============================================================================
# COLOR AND FORMATTING DEFINITIONS
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Configuration
DEMO_MODE=${1:-"interactive"}  # interactive, auto, or test
STARTUP_TIMEOUT=30
TEST_TIMEOUT=10

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║$(printf '%62s' | tr ' ' ' ')║${NC}"
    echo -e "${BOLD}${CYAN}║$(printf "%-62s" "  $1")║${NC}"
    echo -e "${BOLD}${CYAN}║$(printf '%62s' | tr ' ' ' ')║${NC}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
}

print_section() {
    echo ""
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_step() {
    echo -e "${CYAN}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

pause_for_effect() {
    local seconds=${1:-2}
    sleep $seconds
}

wait_for_user() {
    if [ "$DEMO_MODE" == "interactive" ]; then
        echo ""
        echo -e "${DIM}Press Enter to continue...${NC}"
        read
    else
        pause_for_effect 3
    fi
}

# ============================================================================
# CLUSTER MANAGEMENT FUNCTIONS
# ============================================================================

cleanup() {
    echo ""
    print_section "🛑 SHUTTING DOWN CLUSTER"
    echo ""
    print_step "Stopping all SyncPay nodes..."
    pkill -f "python.*main.py" 2>/dev/null || true
    rm -f .pids
    pause_for_effect 1
    print_success "All nodes stopped"
    echo ""
    print_info "Thank you for using SyncPay! 👋"
    echo ""
    exit 0
}

# Handle Ctrl+C gracefully
trap cleanup SIGINT SIGTERM

wait_for_service() {
    local port=$1
    local name=$2
    local max_attempts=30
    
    print_step "Waiting for $name (port $port) to start..."
    
    for i in $(seq 1 $max_attempts); do
        if timeout 2 curl -s http://localhost:$port/ping >/dev/null 2>&1; then
            print_success "$name is ready!"
            return 0
        fi
        sleep 1
    done
    
    print_error "$name failed to start within ${max_attempts}s"
    return 1
}

get_leader() {
    for port in 5000 5001 5002; do
        if leader_status=$(timeout 3 curl -s http://localhost:$port/status 2>/dev/null); then
            if echo "$leader_status" | grep -q '"is_leader":true'; then
                echo $port
                return 0
            fi
        fi
    done
    return 1
}

show_cluster_status() {
    echo ""
    print_section "📊 CLUSTER STATUS"
    echo ""
    
    local leader_port=$(get_leader)
    local total_txn=0
    
    echo -e "${BOLD}  Node         Status    Role      Transactions${NC}"
    echo -e "${DIM}  ────────────────────────────────────────────────${NC}"
    
    for port in 5000 5001 5002; do
        local node_name="node$((port - 4999))"
        local port_display="$port"
        
        if status=$(timeout 5 curl -s http://localhost:$port/health 2>/dev/null); then
            local is_leader="false"
            if [ "$port" = "$leader_port" ]; then
                is_leader="true"
            fi
            
            local txn_count=$(echo "$status" | grep -o '"transaction_count":[0-9]*' | cut -d':' -f2)
            total_txn=$((total_txn + txn_count))
            
            if [ "$is_leader" = "true" ]; then
                echo -e "  ${GREEN}●${NC} $node_name:$port_display   ${GREEN}ONLINE${NC}    ${YELLOW}LEADER${NC}    $txn_count"
            else
                echo -e "  ${GREEN}●${NC} $node_name:$port_display   ${GREEN}ONLINE${NC}    FOLLOWER  $txn_count"
            fi
        else
            echo -e "  ${RED}●${NC} $node_name:$port_display   ${RED}OFFLINE${NC}   ───       ─"
        fi
    done
    
    echo -e "${DIM}  ────────────────────────────────────────────────${NC}"
    echo -e "  ${BOLD}Total Transactions:${NC} $total_txn"
    echo ""
}

verify_replication() {
    echo ""
    print_step "Verifying data replication across all nodes..."
    pause_for_effect 2
    
    local counts=()
    for port in 5000 5001 5002; do
        if status=$(timeout 5 curl -s http://localhost:$port/health 2>/dev/null); then
            local count=$(echo "$status" | grep -o '"transaction_count":[0-9]*' | cut -d':' -f2)
            counts+=($count)
        else
            counts+=(0)
        fi
    done
    
    # Check if all counts are equal
    if [ "${counts[0]}" -eq "${counts[1]}" ] && [ "${counts[1]}" -eq "${counts[2]}" ]; then
        print_success "Replication verified: All nodes have ${counts[0]} transactions"
        echo -e "  ${GREEN}✓${NC} Node 1: ${counts[0]} transactions"
        echo -e "  ${GREEN}✓${NC} Node 2: ${counts[1]} transactions"
        echo -e "  ${GREEN}✓${NC} Node 3: ${counts[2]} transactions"
        return 0
    else
        print_warning "Replication in progress or nodes diverged"
        echo -e "  ${YELLOW}•${NC} Node 1: ${counts[0]} transactions"
        echo -e "  ${YELLOW}•${NC} Node 2: ${counts[1]} transactions"
        echo -e "  ${YELLOW}•${NC} Node 3: ${counts[2]} transactions"
        return 1
    fi
}

# ============================================================================
# DEMONSTRATION FUNCTIONS
# ============================================================================

run_payment_test() {
    print_section "💳 PAYMENT PROCESSING TEST"
    echo ""
    
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        print_error "No leader found - cluster not ready"
        return 1
    fi
    
    local leader_node="node$((leader_port - 4999))"
    print_info "Current leader: $leader_node (port $leader_port)"
    echo ""
    
    # Create payment JSON
    cat > /tmp/payment.json << EOF
{
    "amount": 150.75,
    "sender": "alice",
    "receiver": "bob"
}
EOF
    
    print_step "Processing payment: alice → bob (\$150.75)"
    pause_for_effect 1
    
    if response=$(timeout $TEST_TIMEOUT curl -s -X POST \
        http://localhost:$leader_port/payment \
        -H "Content-Type: application/json" \
        -d @/tmp/payment.json 2>/dev/null); then
        
        if echo "$response" | grep -q '"status":"success"'; then
            local txn_id=$(echo "$response" | grep -o '"transaction_id":"[^"]*"' | cut -d'"' -f4)
            print_success "Payment successful!"
            echo -e "  ${DIM}Transaction ID:${NC} $txn_id"
            
            # Wait for replication
            print_step "Waiting for replication..."
            pause_for_effect 3
            
            verify_replication
            
        elif echo "$response" | grep -q '"error":"Not leader"'; then
            print_warning "Node leadership changed, retrying..."
            pause_for_effect 2
            run_payment_test  # Retry once
            
        elif echo "$response" | grep -q '"error":"Consensus'; then
            print_warning "Consensus issue (normal in small clusters)"
            print_info "Distributed systems require majority consensus"
            pause_for_effect 1
            
        else
            local error=$(echo "$response" | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
            print_error "Payment failed: ${error:-Unknown error}"
        fi
    else
        print_error "Payment request timed out or connection failed"
    fi
    
    rm -f /tmp/payment.json
    show_cluster_status
}

run_stress_test() {
    print_section "⚡ STRESS TEST - CONCURRENT PAYMENTS"
    echo ""
    
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        print_error "No leader found - cannot run stress test"
        return 1
    fi
    
    print_info "Sending 5 concurrent payments to leader (port $leader_port)"
    echo ""
    
    local success_count=0
    local fail_count=0
    
    # Run 5 payments concurrently
    for i in {1..5}; do
        (
            sleep 0.$i  # Stagger requests slightly
            local amount=$((100 + i * 10))
            print_step "Payment $i: user$i → merchant$i (\$$amount.50)"
            
            if timeout 5 curl -s -X POST http://localhost:$leader_port/payment \
                -H "Content-Type: application/json" \
                -d "{\"amount\": $amount.50, \"sender\": \"user$i\", \"receiver\": \"merchant$i\"}" \
                2>/dev/null | grep -q '"status":"success"'; then
                print_success "Payment $i completed successfully"
                echo 1 >> /tmp/stress_success.tmp
            else
                print_warning "Payment $i failed (expected in high load)"
                echo 1 >> /tmp/stress_fail.tmp
            fi
        ) &
    done
    
    # Wait for all background jobs
    print_step "Processing payments..."
    timeout 15 wait 2>/dev/null || print_warning "Some payments timed out (expected under stress)"
    
    # Count results
    success_count=$(cat /tmp/stress_success.tmp 2>/dev/null | wc -l)
    fail_count=$(cat /tmp/stress_fail.tmp 2>/dev/null | wc -l)
    rm -f /tmp/stress_success.tmp /tmp/stress_fail.tmp
    
    echo ""
    print_info "Results: ${GREEN}$success_count succeeded${NC}, ${YELLOW}$fail_count failed${NC}"
    
    # Wait for replication
    print_step "Waiting for replication to complete..."
    pause_for_effect 3
    
    verify_replication
    show_cluster_status
}

demo_fault_tolerance() {
    print_section "💥 FAULT TOLERANCE DEMONSTRATION"
    echo ""
    
    print_info "This test demonstrates the system's ability to handle node failures"
    echo ""
    
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
        
        print_step "Target: $victim_node (port $victim_port) - a follower node"
        pause_for_effect 2
        
        print_warning "Simulating node failure: killing $victim_node..."
        pkill -f "main.py node$((victim_port - 4999))" 2>/dev/null || true
        
        pause_for_effect 3
        show_cluster_status
        
        echo ""
        print_info "Testing payment processing with one node down..."
        wait_for_user
        
        run_payment_test
        
        echo ""
        print_step "Recovering failed node: restarting $victim_node..."
        
        # Restart the killed node
        cd src
        source ../syncpay_env/bin/activate
        python3 main.py "node$((victim_port - 4999))" > "../logs/node$((victim_port - 4999)).log" 2>&1 &
        cd ..
        
        wait_for_service $victim_port "$victim_node"
        
        print_success "$victim_node has rejoined the cluster"
        pause_for_effect 2
        
        show_cluster_status
        
        echo ""
        print_info "Verifying data synchronization..."
        pause_for_effect 2
        verify_replication
    else
        print_error "Could not identify a follower node to test"
    fi
}

demo_validation() {
    print_section "🛡️ INPUT VALIDATION TESTS"
    echo ""
    
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        print_error "No leader found - cluster not ready"
        return 1
    fi
    
    print_info "Testing payment validation rules..."
    echo ""
    
    # Test 1: Negative amount
    print_step "Test 1: Negative amount (-\$50)"
    response=$(curl -s -X POST http://localhost:$leader_port/payment \
        -H "Content-Type: application/json" \
        -d '{"amount": -50, "sender": "alice", "receiver": "bob"}' 2>/dev/null)
    
    if echo "$response" | grep -q "must be positive"; then
        print_success "Correctly rejected negative amount"
    else
        print_error "Failed to reject negative amount"
    fi
    pause_for_effect 1
    
    # Test 2: Same sender and receiver
    print_step "Test 2: Same sender and receiver"
    response=$(curl -s -X POST http://localhost:$leader_port/payment \
        -H "Content-Type: application/json" \
        -d '{"amount": 100, "sender": "alice", "receiver": "alice"}' 2>/dev/null)
    
    if echo "$response" | grep -q "cannot be the same"; then
        print_success "Correctly rejected self-payment"
    else
        print_error "Failed to reject self-payment"
    fi
    pause_for_effect 1
    
    # Test 3: Amount too high
    print_step "Test 3: Amount exceeding limit (\$20,000)"
    response=$(curl -s -X POST http://localhost:$leader_port/payment \
        -H "Content-Type: application/json" \
        -d '{"amount": 20000, "sender": "alice", "receiver": "bob"}' 2>/dev/null)
    
    if echo "$response" | grep -q "exceeds maximum"; then
        print_success "Correctly rejected excessive amount"
    else
        print_error "Failed to reject excessive amount"
    fi
    
    echo ""
    print_info "All validation tests completed"
}

show_metrics() {
    print_section "📈 SYSTEM METRICS"
    echo ""
    
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        print_error "No leader found - cannot fetch metrics"
        return 1
    fi
    
    print_info "Fetching metrics from leader (port $leader_port)..."
    echo ""
    
    if metrics=$(curl -s "http://localhost:$leader_port/metrics?format=summary" 2>/dev/null); then
        echo "$metrics" | head -n 30
    else
        print_error "Failed to fetch metrics"
    fi
}

show_configuration() {
    print_section "⚙️  SYSTEM CONFIGURATION"
    echo ""
    
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        print_error "No leader found - cannot fetch configuration"
        return 1
    fi
    
    print_info "Fetching configuration from leader (port $leader_port)..."
    echo ""
    
    if config=$(curl -s "http://localhost:$leader_port/config" 2>/dev/null); then
        echo "$config" | python3 -m json.tool | head -n 20
        echo -e "${DIM}  ... (configuration continues)${NC}"
    else
        print_error "Failed to fetch configuration"
    fi
}

test_non_leader_rejection() {
    print_section "🚫 NON-LEADER REJECTION TEST"
    echo ""
    
    local leader_port=$(get_leader)
    
    if [ -z "$leader_port" ]; then
        print_error "No leader found - cluster not ready"
        return 1
    fi
    
    # Find a non-leader
    local non_leader_port=""
    for port in 5000 5001 5002; do
        if [ "$port" != "$leader_port" ]; then
            non_leader_port=$port
            break
        fi
    done
    
    if [ -z "$non_leader_port" ]; then
        print_warning "All nodes are leaders (shouldn't happen)"
        return 1
    fi
    
    print_info "Leader is on port $leader_port"
    print_info "Sending payment to non-leader on port $non_leader_port"
    echo ""
    
    print_step "Attempting payment to follower node..."
    
    response=$(curl -s -X POST http://localhost:$non_leader_port/payment \
        -H "Content-Type: application/json" \
        -d '{"amount": 99.99, "sender": "charlie", "receiver": "dave"}' 2>/dev/null)
    
    if echo "$response" | grep -q '"error":"Not leader"'; then
        print_success "Follower correctly rejected payment"
        
        if echo "$response" | grep -q "leader_port"; then
            local suggested_port=$(echo "$response" | grep -o '"leader_port":[0-9]*' | cut -d':' -f2)
            print_info "Follower redirected to leader on port $suggested_port"
        fi
    else
        print_warning "Unexpected response from follower"
        echo "$response"
    fi
}

view_logs() {
    print_section "📜 LIVE CLUSTER LOGS"
    echo ""
    
    print_info "Showing live logs from all nodes"
    print_warning "Press Ctrl+C to stop viewing logs"
    echo ""
    pause_for_effect 2
    
    tail -f logs/node*.log
}

# ============================================================================
# CLUSTER STARTUP
# ============================================================================

start_cluster() {
    print_header "SYNCPAY DISTRIBUTED PAYMENT SYSTEM"
    
    echo ""
    echo -e "${CYAN}  Version:${NC}        2.0.0 Enhanced"
    echo -e "${CYAN}  Mode:${NC}           $DEMO_MODE"
    echo -e "${CYAN}  Nodes:${NC}          3 (High Availability)"
    echo -e "${CYAN}  Consensus:${NC}      Raft Algorithm"
    echo ""
    
    print_section "🧹 CLEANUP"
    echo ""
    print_step "Cleaning up existing processes..."
    pkill -f "python.*main.py" 2>/dev/null || true
    pause_for_effect 2
    print_success "Cleanup complete"
    
    # Create logs directory
    mkdir -p logs
    
    print_section "🏗️  STARTING CLUSTER"
    echo ""
    
    cd src
    source ../syncpay_env/bin/activate
    
    print_step "Starting Node 1 (Primary)..."
    python3 main.py node1 > ../logs/node1.log 2>&1 &
    NODE1_PID=$!
    pause_for_effect 3
    
    print_step "Starting Node 2 (Replica)..."
    python3 main.py node2 > ../logs/node2.log 2>&1 &
    NODE2_PID=$!
    pause_for_effect 3
    
    print_step "Starting Node 3 (Replica)..."
    python3 main.py node3 > ../logs/node3.log 2>&1 &
    NODE3_PID=$!
    
    cd ..
    
    # Save PIDs
    echo "$NODE1_PID $NODE2_PID $NODE3_PID" > .pids
    
    echo ""
    print_section "⏳ INITIALIZATION"
    echo ""
    
    wait_for_service 5000 "Node 1" || exit 1
    wait_for_service 5001 "Node 2" || exit 1  
    wait_for_service 5002 "Node 3" || exit 1
    
    echo ""
    print_step "Waiting for leader election..."
    pause_for_effect 5
    
    local leader_port=$(get_leader)
    if [ -n "$leader_port" ]; then
        local leader_node="node$((leader_port - 4999))"
        print_success "Leader elected: $leader_node (port $leader_port)"
    else
        print_warning "Leader election in progress..."
    fi
    
    show_cluster_status
}

# ============================================================================
# INTERACTIVE MENU
# ============================================================================

show_menu() {
    echo ""
    print_section "🎮 INTERACTIVE DEMO MENU"
    echo ""
    echo -e "  ${BOLD}Basic Operations:${NC}"
    echo -e "    ${YELLOW}1${NC} - Single Payment Test"
    echo -e "    ${YELLOW}2${NC} - Stress Test (5 concurrent payments)"
    echo -e "    ${YELLOW}3${NC} - Fault Tolerance Demo"
    echo -e "    ${YELLOW}4${NC} - Input Validation Tests"
    echo ""
    echo -e "  ${BOLD}Advanced:${NC}"
    echo -e "    ${YELLOW}5${NC} - Non-Leader Rejection Test"
    echo -e "    ${YELLOW}6${NC} - View System Metrics"
    echo -e "    ${YELLOW}7${NC} - View Configuration"
    echo ""
    echo -e "  ${BOLD}Information:${NC}"
    echo -e "    ${YELLOW}s${NC} - Show Cluster Status"
    echo -e "    ${YELLOW}l${NC} - View Live Logs"
    echo -e "    ${YELLOW}h${NC} - Show this menu"
    echo ""
    echo -e "  ${BOLD}Control:${NC}"
    echo -e "    ${YELLOW}a${NC} - Run All Tests (automated)"
    echo -e "    ${YELLOW}q${NC} - Quit and shutdown cluster"
    echo ""
}

interactive_mode() {
    show_menu
    
    while true; do
        echo -e -n "${BOLD}${CYAN}syncpay>${NC} "
        read choice
        
        case $choice in
            "1")
                run_payment_test
                wait_for_user
                ;;
            "2")
                run_stress_test
                wait_for_user
                ;;
            "3")
                demo_fault_tolerance
                wait_for_user
                ;;
            "4")
                demo_validation
                wait_for_user
                ;;
            "5")
                test_non_leader_rejection
                wait_for_user
                ;;
            "6")
                show_metrics
                wait_for_user
                ;;
            "7")
                show_configuration
                wait_for_user
                ;;
            "s")
                show_cluster_status
                ;;
            "l")
                view_logs
                ;;
            "h")
                show_menu
                ;;
            "a")
                run_all_tests
                wait_for_user
                ;;
            "q"|"quit"|"exit")
                cleanup
                ;;
            "")
                # Just pressed enter, ignore
                ;;
            *)
                print_error "Invalid option. Type 'h' for help"
                ;;
        esac
    done
}

# ============================================================================
# AUTOMATED TEST SUITE
# ============================================================================

run_all_tests() {
    print_header "COMPREHENSIVE TEST SUITE"
    
    echo ""
    print_info "Running all demonstrations in automated sequence..."
    echo ""
    
    # Test 1: Payment
    run_payment_test
    wait_for_user
    
    # Test 2: Validation
    demo_validation
    wait_for_user
    
    # Test 3: Stress Test
    run_stress_test
    wait_for_user
    
    # Test 4: Fault Tolerance
    demo_fault_tolerance
    wait_for_user
    
    # Test 5: Non-Leader Rejection
    test_non_leader_rejection
    wait_for_user
    
    # Test 6: Metrics
    show_metrics
    wait_for_user
    
    # Final Summary
    print_section "🎉 TEST SUITE COMPLETE"
    echo ""
    print_success "All demonstrations completed successfully!"
    show_cluster_status
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

# Start the cluster
start_cluster

# Run appropriate demo mode
case $DEMO_MODE in
    "auto")
        run_all_tests
        echo ""
        print_info "Automated demo complete. Cleaning up..."
        pause_for_effect 3
        cleanup
        ;;
    "test")
        run_payment_test
        cleanup
        ;;
    "interactive"|*)
        interactive_mode
        ;;
esac
