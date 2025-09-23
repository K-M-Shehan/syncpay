#!/usr/bin/env python3
# simple_test.py - Simple functional test of SyncPay node

import requests
import json
import time
import subprocess
import signal
import os
import sys

def test_single_node():
    """Test a single SyncPay node functionality"""
    print("🧪 Testing SyncPay Single Node")
    print("=" * 50)
    
    # Start node1 in background
    print("🚀 Starting node1...")
    src_dir = os.path.join(os.path.dirname(__file__), 'src')
    venv_python = os.path.join(os.path.dirname(__file__), 'syncpay_env', 'bin', 'python3')
    
    process = subprocess.Popen(
        [venv_python, 'main.py', 'node1'],
        cwd=src_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid  # Create new process group
    )
    
    try:
        # Wait for node to start
        print("⏳ Waiting for node to start...")
        time.sleep(8)
        
        # Test health endpoint
        print("🔍 Testing health endpoint...")
        response = requests.get('http://localhost:5000/health', timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Health check passed: {health_data['node_id']} - {health_data['status']}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
        
        # Test status endpoint
        print("🔍 Testing status endpoint...")
        response = requests.get('http://localhost:5000/status', timeout=5)
        if response.status_code == 200:
            status_data = response.json()
            print(f"✅ Status check passed: Leader={status_data['is_leader']}")
        else:
            print(f"❌ Status check failed: {response.status_code}")
            return False
        
        # Test payment transaction
        print("🔍 Testing payment transaction...")
        payment_data = {
            'amount': 123.45,
            'sender': 'alice_test',
            'receiver': 'bob_test'
        }
        
        response = requests.post(
            'http://localhost:5000/payment',
            json=payment_data,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        
        if response.status_code == 200:
            txn_data = response.json()
            print(f"✅ Payment processed: {txn_data['transaction_id']}")
            
            # Test transactions endpoint
            time.sleep(2)
            response = requests.get('http://localhost:5000/transactions', timeout=5)
            if response.status_code == 200:
                txns = response.json()['transactions']
                if len(txns) > 0:
                    print(f"✅ Transaction stored: Found {len(txns)} transactions")
                else:
                    print("⚠️  No transactions found in storage")
            else:
                print(f"❌ Failed to retrieve transactions: {response.status_code}")
        else:
            print(f"❌ Payment failed: {response.status_code}")
            return False
        
        print("\n🎉 All tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
        
    finally:
        # Stop the node
        print("🛑 Stopping node...")
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
        except:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except:
                pass

if __name__ == '__main__':
    success = test_single_node()
    sys.exit(0 if success else 1)