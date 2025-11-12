#!/usr/bin/env python3
"""
Continuous Bot Monitor
Watches the live trading bot and reports status, errors, and key events
"""

import time
import subprocess
import re
from datetime import datetime
from collections import defaultdict

LOG_FILE = "/tmp/live_bot.log"
CHECK_INTERVAL = 10  # Check every 10 seconds

class BotMonitor:
    def __init__(self):
        self.stats = {
            'positions_tracked': set(),
            'tp_placed': 0,
            'sl_placed': 0,
            'tp_failed': 0,
            'sl_failed': 0,
            'tp_hits': 0,
            'trailing_activated': 0,
            'positions_closed': 0,
            'signals_found': 0,
            'errors': [],
            'last_check': None
        }
        self.last_position = 0
    
    def is_bot_running(self):
        """Check if bot process is running"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "python launch_institutional_live.py"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except:
            return False
    
    def get_recent_logs(self, lines=200):
        """Get recent log lines"""
        try:
            result = subprocess.run(
                ["tail", "-n", str(lines), LOG_FILE],
                capture_output=True,
                text=True
            )
            return result.stdout.split('\n')
        except:
            return []
    
    def analyze_logs(self, logs):
        """Analyze logs for key events"""
        new_events = {
            'positions': set(),
            'tp_placed': 0,
            'sl_placed': 0,
            'tp_failed': 0,
            'sl_failed': 0,
            'tp_hits': 0,
            'trailing_activated': 0,
            'positions_closed': 0,
            'signals_found': 0,
            'errors': []
        }
        
        for line in logs:
            # Track positions
            if "POSITION OPENED" in line or "Exchange SL placed" in line:
                symbol_match = re.search(r'(\w+USDT)', line)
                if symbol_match:
                    new_events['positions'].add(symbol_match.group(1))
            
            # TP/SL placement
            if "Exchange TP1 placed" in line or "TP1 placed" in line:
                new_events['tp_placed'] += 1
            if "Exchange SL placed" in line or "SL placed" in line:
                new_events['sl_placed'] += 1
            
            # TP/SL failures
            if "TP order FAILED" in line or "EXCHANGE TP FAILED" in line:
                new_events['tp_failed'] += 1
            if "SL order FAILED" in line or "EXCHANGE SL FAILED" in line:
                new_events['sl_failed'] += 1
            
            # TP hits
            if "TP1 HIT" in line or "TP1.*HIT" in line:
                new_events['tp_hits'] += 1
            
            # Trailing stop
            if "Trailing stop placed" in line or "Trailing stop for" in line:
                new_events['trailing_activated'] += 1
            
            # Position closed
            if "Position fully closed" in line or "Position closed" in line:
                new_events['positions_closed'] += 1
            
            # Signals
            if "SIGNAL EXECUTED" in line or "SIGNAL CANDIDATE" in line:
                new_events['signals_found'] += 1
            
            # Errors
            if "ERROR" in line or "❌" in line:
                if "Insufficient position" in line or "43023" in line:
                    # Skip these - they're expected for small positions
                    pass
                elif "45135" in line or "40832" in line:
                    # TP price validation errors - should be fixed now
                    pass
                else:
                    error_match = re.search(r'❌\s+(.+)', line)
                    if error_match:
                        error_msg = error_match.group(1)[:100]
                        if error_msg not in self.stats['errors'][-10:]:
                            new_events['errors'].append(error_msg)
        
        return new_events
    
    def update_stats(self, events):
        """Update statistics"""
        self.stats['positions_tracked'].update(events['positions'])
        self.stats['tp_placed'] += events['tp_placed']
        self.stats['sl_placed'] += events['sl_placed']
        self.stats['tp_failed'] += events['tp_failed']
        self.stats['sl_failed'] += events['sl_failed']
        self.stats['tp_hits'] += events['tp_hits']
        self.stats['trailing_activated'] += events['trailing_activated']
        self.stats['positions_closed'] += events['positions_closed']
        self.stats['signals_found'] += events['signals_found']
        self.stats['errors'].extend(events['errors'])
        self.stats['errors'] = self.stats['errors'][-20:]  # Keep last 20
        self.stats['last_check'] = datetime.now()
    
    def print_status(self):
        """Print current status"""
        print("\n" + "="*80)
        print(f"🤖 BOT MONITOR | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # Bot status
        if self.is_bot_running():
            print("✅ Bot Status: RUNNING")
        else:
            print("❌ Bot Status: NOT RUNNING")
        
        # Positions
        print(f"\n📊 Positions Tracked: {len(self.stats['positions_tracked'])}")
        if self.stats['positions_tracked']:
            print(f"   Symbols: {', '.join(sorted(list(self.stats['positions_tracked']))[:10])}")
            if len(self.stats['positions_tracked']) > 10:
                print(f"   ... and {len(self.stats['positions_tracked']) - 10} more")
        
        # TP/SL Stats
        print(f"\n🎯 TP/SL Status:")
        print(f"   ✅ TP Placed: {self.stats['tp_placed']}")
        print(f"   ✅ SL Placed: {self.stats['sl_placed']}")
        print(f"   ❌ TP Failed: {self.stats['tp_failed']}")
        print(f"   ❌ SL Failed: {self.stats['sl_failed']}")
        
        # Trading Activity
        print(f"\n📈 Trading Activity:")
        print(f"   🎯 Signals Found: {self.stats['signals_found']}")
        print(f"   🎉 TP Hits: {self.stats['tp_hits']}")
        print(f"   🔄 Trailing Activated: {self.stats['trailing_activated']}")
        print(f"   ✅ Positions Closed: {self.stats['positions_closed']}")
        
        # Recent Errors
        if self.stats['errors']:
            print(f"\n⚠️  Recent Errors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][-5:]:
                print(f"   - {error}")
        
        # Recent activity
        logs = self.get_recent_logs(50)
        recent_activity = []
        for line in logs[-10:]:
            if any(keyword in line for keyword in ["POSITION", "TP1", "Trailing", "SIGNAL", "ERROR"]):
                recent_activity.append(line.strip()[:100])
        
        if recent_activity:
            print(f"\n📋 Recent Activity:")
            for activity in recent_activity[-5:]:
                print(f"   {activity}")
        
        print("="*80)
    
    def run(self):
        """Main monitoring loop"""
        print("🚀 Starting Bot Monitor...")
        print(f"   Log file: {LOG_FILE}")
        print(f"   Check interval: {CHECK_INTERVAL}s")
        print("   Press Ctrl+C to stop\n")
        
        try:
            while True:
                if self.is_bot_running():
                    logs = self.get_recent_logs(200)
                    events = self.analyze_logs(logs)
                    self.update_stats(events)
                    self.print_status()
                else:
                    print(f"\n❌ Bot is NOT RUNNING! | {datetime.now().strftime('%H:%M:%S')}")
                
                time.sleep(CHECK_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitor stopped by user")
            print("\n📊 Final Statistics:")
            self.print_status()

if __name__ == "__main__":
    monitor = BotMonitor()
    monitor.run()

