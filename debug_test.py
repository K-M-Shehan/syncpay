#!/usr/bin/env python3
# debug_test.py - Debug test to see what's happening

import requests
import json
import time
import subprocess
import signal
import os
import sys

def debug_single_node():
    """Debug a single SyncPay node"""
    print("🔍 Debugging SyncPay Single Node")
    print("=" * 50)
    
    # Start node1 in background
    print("🚀 Starting node1...")
    src_dir = os.path.join(os.path.dirname(__file__), 'src')
    venv_python = os.path.join(os.path.dirname(__file__), 'syncpay_env', 'bin', 'python3')
    
    process = subprocess.Popen(
        [venv_python, 'main.py', 'node1'],
        cwd=src_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid  # Create new process group
    )
    
    try:
        # Wait for node to start
        print("⏳ Waiting for node to start...")
        time.sleep(10)
        
        # Test health endpoint
        print("🔍 Testing health endpoint...")
        response = requests.get('http://localhost:5000/health', timeout=5)
        print(f"Health response: {response.status_code}")
        if response.status_code == 200:
            print(json.dumps(response.json(), indent=2))
        
        # Test status endpoint
        print("\n🔍 Testing status endpoint...")
        response = requests.get('http://localhost:5000/status', timeout=5)
        print(f"Status response: {response.status_code}")
        if response.status_code == 200:
            print(json.dumps(response.json(), indent=2))
        
        # Test payment transaction with detailed error info
        print("\n🔍 Testing payment transaction...")
        payment_data = {
            'amount': 100.0,
            'sender': 'alice',
            'receiver': 'bob'
        }
        
        response = requests.post(
            'http://localhost:5000/payment',
            json=payment_data,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        
        print(f"Payment response: {response.status_code}")
        print(f"Response content: {response.text}")
        
        # Get server output
        print("\n📝 Server output:")
        output, _ = process.communicate(timeout=2)
        print(output.decode())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        # Try to get server output on error
        try:
            output, _ = process.communicate(timeout=1)
            print(f"Server output on error: {output.decode()}")
        except:
            pass
        
    finally:
        # Stop the node
        print("🛑 Stopping node...")
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=2)
        except:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except:
                pass

if __name__ == '__main__':
    debug_single_node()