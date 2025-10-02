# src/utils/metrics.py
# Monitoring and Metrics Collection

import time
import threading
from typing import Dict, List, Optional
from collections import defaultdict, deque
from datetime import datetime
import json


class MetricsCollector:
    """Centralized metrics collection for monitoring system performance"""
    
    def __init__(self, node_id: str, max_history: int = 1000):
        self.node_id = node_id
        self.max_history = max_history
        
        # Metrics storage
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)
        self.histograms = defaultdict(lambda: deque(maxlen=max_history))
        self.timers = {}  # active timers
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Timestamps
        self.start_time = time.time()
        self.last_reset = time.time()
        
    def increment(self, metric_name: str, value: int = 1):
        """Increment a counter metric"""
        with self.lock:
            self.counters[metric_name] += value
    
    def decrement(self, metric_name: str, value: int = 1):
        """Decrement a counter metric"""
        with self.lock:
            self.counters[metric_name] -= value
    
    def set_gauge(self, metric_name: str, value: float):
        """Set a gauge metric to a specific value"""
        with self.lock:
            self.gauges[metric_name] = value
    
    def record_value(self, metric_name: str, value: float):
        """Record a value in a histogram"""
        with self.lock:
            self.histograms[metric_name].append({
                'value': value,
                'timestamp': time.time()
            })
    
    def start_timer(self, timer_name: str) -> str:
        """Start a timer and return a timer ID"""
        timer_id = f"{timer_name}_{time.time()}_{id(threading.current_thread())}"
        with self.lock:
            self.timers[timer_id] = {
                'name': timer_name,
                'start_time': time.time()
            }
        return timer_id
    
    def stop_timer(self, timer_id: str) -> Optional[float]:
        """Stop a timer and record the duration"""
        with self.lock:
            if timer_id not in self.timers:
                return None
            
            timer = self.timers.pop(timer_id)
            duration = time.time() - timer['start_time']
            
            # Record duration in histogram
            self.record_value(f"{timer['name']}_duration", duration)
            
            return duration
    
    def get_counter(self, metric_name: str) -> int:
        """Get current counter value"""
        with self.lock:
            return self.counters.get(metric_name, 0)
    
    def get_gauge(self, metric_name: str) -> float:
        """Get current gauge value"""
        with self.lock:
            return self.gauges.get(metric_name, 0.0)
    
    def get_histogram_stats(self, metric_name: str) -> Dict:
        """Get statistics for a histogram"""
        with self.lock:
            values = [entry['value'] for entry in self.histograms.get(metric_name, [])]
            
            if not values:
                return {
                    'count': 0,
                    'min': 0,
                    'max': 0,
                    'avg': 0,
                    'p50': 0,
                    'p95': 0,
                    'p99': 0
                }
            
            values_sorted = sorted(values)
            count = len(values_sorted)
            
            return {
                'count': count,
                'min': min(values_sorted),
                'max': max(values_sorted),
                'avg': sum(values_sorted) / count,
                'p50': self._percentile(values_sorted, 50),
                'p95': self._percentile(values_sorted, 95),
                'p99': self._percentile(values_sorted, 99)
            }
    
    def _percentile(self, sorted_values: List[float], percentile: int) -> float:
        """Calculate percentile from sorted values"""
        if not sorted_values:
            return 0.0
        
        index = int((percentile / 100.0) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]
    
    def get_all_metrics(self) -> Dict:
        """Get all metrics in a structured format"""
        with self.lock:
            uptime = time.time() - self.start_time
            
            metrics = {
                'node_id': self.node_id,
                'timestamp': time.time(),
                'uptime_seconds': uptime,
                'counters': dict(self.counters),
                'gauges': dict(self.gauges),
                'histograms': {}
            }
            
            # Add histogram statistics
            for hist_name in self.histograms.keys():
                metrics['histograms'][hist_name] = self.get_histogram_stats(hist_name)
            
            return metrics
    
    def reset(self):
        """Reset all metrics"""
        with self.lock:
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()
            self.timers.clear()
            self.last_reset = time.time()
    
    def export_json(self) -> str:
        """Export metrics as JSON string"""
        return json.dumps(self.get_all_metrics(), indent=2)
    
    def get_summary(self) -> str:
        """Get a human-readable summary of metrics"""
        metrics = self.get_all_metrics()
        
        lines = [
            f"=== Metrics for {self.node_id} ===",
            f"Uptime: {metrics['uptime_seconds']:.2f}s",
            "",
            "Counters:",
        ]
        
        for name, value in sorted(metrics['counters'].items()):
            lines.append(f"  {name}: {value}")
        
        lines.append("")
        lines.append("Gauges:")
        for name, value in sorted(metrics['gauges'].items()):
            lines.append(f"  {name}: {value:.4f}")
        
        lines.append("")
        lines.append("Histograms:")
        for name, stats in sorted(metrics['histograms'].items()):
            lines.append(f"  {name}:")
            lines.append(f"    count: {stats['count']}")
            lines.append(f"    avg: {stats['avg']:.4f}")
            lines.append(f"    p50: {stats['p50']:.4f}")
            lines.append(f"    p95: {stats['p95']:.4f}")
            lines.append(f"    p99: {stats['p99']:.4f}")
        
        return "\n".join(lines)
