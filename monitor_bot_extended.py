#!/usr/bin/env python3
"""
Extended Bot Monitor - Long-term monitoring with detailed reporting
"""

import time
import subprocess
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque

LOG_FILE = "/tmp/live_bot.log"
CHECK_INTERVAL = 30  # Check every 30 seconds
REPORT_INTERVAL = 300  # Full report every 5 minutes
STATUS_INTERVAL = 60  # Quick status every 1 minute

class ExtendedBotMonitor:
    def __init__(self):
        self.stats = {
            'start_time': datetime.now(),
            'positions_tracked': set(),
            'position_history': deque(maxlen=100),  # Last 100 position events
            'tp_placed': 0,
            'sl_placed': 0,
            'tp_failed': 0,
            'sl_failed': 0,
            'tp_hits': [],
            'trailing_activated': [],
            'positions_closed': [],
            'signals_found': 0,
            'signals_executed': 0,
            'errors': deque(maxlen=50),
            'warnings': deque(maxlen=50),
            'last_check': None,
            'last_report': None,
            'check_count': 0
        }
        self.position_details = {}  # symbol -> {entry_time, side, strategy, pnl, etc}
        self.last_log_position = 0
    
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
    
    def get_recent_logs(self, lines=500):
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
    
    def get_new_logs(self):
        """Get only new log lines since last check"""
        try:
            # Get total lines in file
            result = subprocess.run(
                ["wc", "-l", LOG_FILE],
                capture_output=True,
                text=True
            )
            total_lines = int(result.stdout.split()[0])
            
            # Get new lines
            new_lines = total_lines - self.last_log_position
            if new_lines > 0:
                result = subprocess.run(
                    ["tail", "-n", str(new_lines), LOG_FILE],
                    capture_output=True,
                    text=True
                )
                self.last_log_position = total_lines
                return result.stdout.split('\n')
            return []
        except:
            return []
    
    def analyze_logs(self, logs):
        """Analyze logs for key events"""
        events = {
            'positions': set(),
            'tp_placed': 0,
            'sl_placed': 0,
            'tp_failed': 0,
            'sl_failed': 0,
            'tp_hits': [],
            'trailing_activated': [],
            'positions_closed': [],
            'signals_found': 0,
            'signals_executed': 0,
            'errors': [],
            'warnings': []
        }
        
        for line in logs:
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            timestamp = timestamp_match.group(1) if timestamp_match else None
            
            # Track positions
            if "POSITION OPENED" in line or "Exchange SL placed" in line:
                symbol_match = re.search(r'(\w+USDT)', line)
                if symbol_match:
                    symbol = symbol_match.group(1)
                    events['positions'].add(symbol)
                    if symbol not in self.position_details:
                        self.position_details[symbol] = {
                            'entry_time': timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'side': 'unknown',
                            'strategy': 'unknown'
                        }
            
            # Extract position details
            if "POSITION OPENED" in line:
                symbol_match = re.search(r'(\w+USDT)', line)
                side_match = re.search(r'(LONG|SHORT)', line)
                strategy_match = re.search(r'Strategy: (\w+)', line)
                if symbol_match:
                    symbol = symbol_match.group(1)
                    if symbol in self.position_details:
                        if side_match:
                            self.position_details[symbol]['side'] = side_match.group(1).lower()
                        if strategy_match:
                            self.position_details[symbol]['strategy'] = strategy_match.group(1)
            
            # TP/SL placement
            if "Exchange TP1 placed" in line or "TP1 placed" in line:
                events['tp_placed'] += 1
                symbol_match = re.search(r'(\w+USDT)', line)
                if symbol_match and timestamp:
                    events['position_history'].append({
                        'time': timestamp,
                        'event': 'TP_PLACED',
                        'symbol': symbol_match.group(1)
                    })
            
            if "Exchange SL placed" in line or "SL placed" in line:
                events['sl_placed'] += 1
            
            # TP/SL failures (only log non-expected ones)
            if "TP order FAILED" in line and "43023" not in line:  # Skip "Insufficient position"
                events['tp_failed'] += 1
                if timestamp:
                    events['errors'].append(f"{timestamp}: TP placement failed")
            
            if "SL order FAILED" in line:
                events['sl_failed'] += 1
                if timestamp:
                    events['errors'].append(f"{timestamp}: SL placement failed")
            
            # TP hits
            if "TP1 HIT" in line:
                symbol_match = re.search(r'(\w+USDT)', line)
                if symbol_match and timestamp:
                    events['tp_hits'].append({
                        'time': timestamp,
                        'symbol': symbol_match.group(1)
                    })
            
            # Trailing stop
            if "Trailing stop placed" in line or "Trailing stop for" in line:
                symbol_match = re.search(r'(\w+USDT)', line)
                if symbol_match and timestamp:
                    events['trailing_activated'].append({
                        'time': timestamp,
                        'symbol': symbol_match.group(1)
                    })
            
            # Position closed
            if "Position fully closed" in line or "Position closed" in line:
                symbol_match = re.search(r'(\w+USDT)', line)
                if symbol_match and timestamp:
                    events['positions_closed'].append({
                        'time': timestamp,
                        'symbol': symbol_match.group(1)
                    })
                    # Remove from tracking
                    if symbol_match.group(1) in self.position_details:
                        del self.position_details[symbol_match.group(1)]
            
            # Signals
            if "SIGNAL EXECUTED" in line:
                events['signals_executed'] += 1
            if "SIGNAL CANDIDATE" in line:
                events['signals_found'] += 1
            
            # Errors (filter out expected ones)
            if "ERROR" in line or "❌" in line:
                if "43023" not in line and "45135" not in line and "40832" not in line:
                    error_match = re.search(r'❌\s+(.+)', line)
                    if error_match:
                        error_msg = error_match.group(1)[:150]
                        if timestamp:
                            events['errors'].append(f"{timestamp}: {error_msg}")
            
            # Warnings
            if "WARNING" in line or "⚠️" in line:
                if "Insufficient position" not in line:
                    warning_match = re.search(r'⚠️\s+(.+)', line)
                    if warning_match:
                        warning_msg = warning_match.group(1)[:150]
                        if timestamp:
                            events['warnings'].append(f"{timestamp}: {warning_msg}")
        
        return events
    
    def update_stats(self, events):
        """Update statistics"""
        self.stats['positions_tracked'].update(events['positions'])
        self.stats['tp_placed'] += events['tp_placed']
        self.stats['sl_placed'] += events['sl_placed']
        self.stats['tp_failed'] += events['tp_failed']
        self.stats['sl_failed'] += events['sl_failed']
        self.stats['tp_hits'].extend(events['tp_hits'])
        self.stats['trailing_activated'].extend(events['trailing_activated'])
        self.stats['positions_closed'].extend(events['positions_closed'])
        self.stats['signals_found'] += events['signals_found']
        self.stats['signals_executed'] += events['signals_executed']
        
        for error in events['errors']:
            if error not in self.stats['errors']:
                self.stats['errors'].append(error)
        
        for warning in events['warnings']:
            if warning not in self.stats['warnings']:
                self.stats['warnings'].append(warning)
        
        self.stats['last_check'] = datetime.now()
        self.stats['check_count'] += 1
    
    def print_quick_status(self):
        """Print quick status update"""
        runtime = datetime.now() - self.stats['start_time']
        runtime_str = str(runtime).split('.')[0]  # Remove microseconds
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
              f"Runtime: {runtime_str} | "
              f"Positions: {len(self.stats['positions_tracked'])} | "
              f"TP Hits: {len(self.stats['tp_hits'])} | "
              f"Signals: {self.stats['signals_executed']} | "
              f"Errors: {len(self.stats['errors'])}")
    
    def print_full_report(self):
        """Print comprehensive status report"""
        runtime = datetime.now() - self.stats['start_time']
        runtime_str = str(runtime).split('.')[0]
        
        print("\n" + "="*80)
        print(f"📊 EXTENDED BOT MONITOR REPORT | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # Bot status
        if self.is_bot_running():
            print("✅ Bot Status: RUNNING")
        else:
            print("❌ Bot Status: NOT RUNNING - ACTION REQUIRED!")
        
        print(f"⏱️  Runtime: {runtime_str}")
        print(f"🔄 Checks Performed: {self.stats['check_count']}")
        
        # Positions
        print(f"\n📊 Position Tracking:")
        print(f"   Active Positions: {len(self.stats['positions_tracked'])}")
        if self.stats['positions_tracked']:
            print(f"   Symbols: {', '.join(sorted(list(self.stats['positions_tracked'])))}")
        
        # Position details
        if self.position_details:
            print(f"\n   Position Details:")
            for symbol, details in sorted(self.position_details.items()):
                print(f"      {symbol}: {details.get('side', 'unknown').upper()} | "
                      f"{details.get('strategy', 'unknown')} | "
                      f"Entry: {details.get('entry_time', 'unknown')}")
        
        # TP/SL Stats
        print(f"\n🎯 TP/SL Statistics:")
        print(f"   ✅ TP Orders Placed: {self.stats['tp_placed']}")
        print(f"   ✅ SL Orders Placed: {self.stats['sl_placed']}")
        print(f"   ❌ TP Orders Failed: {self.stats['tp_failed']} (excluding 'Insufficient position')")
        print(f"   ❌ SL Orders Failed: {self.stats['sl_failed']}")
        
        # Trading Activity
        print(f"\n📈 Trading Activity:")
        print(f"   🎯 Signals Found: {self.stats['signals_found']}")
        print(f"   ✅ Signals Executed: {self.stats['signals_executed']}")
        print(f"   🎉 TP Hits: {len(self.stats['tp_hits'])}")
        if self.stats['tp_hits']:
            print(f"      Recent TP Hits:")
            for hit in self.stats['tp_hits'][-5:]:
                print(f"         {hit['time']}: {hit['symbol']}")
        
        print(f"   🔄 Trailing Stops Activated: {len(self.stats['trailing_activated'])}")
        if self.stats['trailing_activated']:
            print(f"      Recent Activations:")
            for trail in self.stats['trailing_activated'][-5:]:
                print(f"         {trail['time']}: {trail['symbol']}")
        
        print(f"   ✅ Positions Closed: {len(self.stats['positions_closed'])}")
        if self.stats['positions_closed']:
            print(f"      Recent Closes:")
            for close in self.stats['positions_closed'][-5:]:
                print(f"         {close['time']}: {close['symbol']}")
        
        # Recent Activity
        logs = self.get_recent_logs(100)
        recent_activity = []
        for line in logs[-20:]:
            if any(keyword in line for keyword in ["POSITION", "TP1 HIT", "Trailing", "SIGNAL EXECUTED", "Position closed"]):
                timestamp_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else ""
                activity = line.strip()[:120]
                recent_activity.append(f"{timestamp}: {activity}")
        
        if recent_activity:
            print(f"\n📋 Recent Activity (Last 5):")
            for activity in recent_activity[-5:]:
                print(f"   {activity}")
        
        # Errors & Warnings
        if self.stats['errors']:
            print(f"\n⚠️  Recent Errors ({len(self.stats['errors'])}):")
            for error in list(self.stats['errors'])[-5:]:
                print(f"   {error}")
        
        if self.stats['warnings']:
            print(f"\n⚠️  Recent Warnings ({len(self.stats['warnings'])}):")
            for warning in list(self.stats['warnings'])[-5:]:
                print(f"   {warning}")
        
        # Performance Summary
        if self.stats['check_count'] > 0:
            avg_check_interval = runtime.total_seconds() / self.stats['check_count']
            print(f"\n⚡ Performance:")
            print(f"   Average Check Interval: {avg_check_interval:.1f}s")
            print(f"   Signals/Hour: {(self.stats['signals_executed'] / max(runtime.total_seconds() / 3600, 0.1)):.1f}")
            if len(self.stats['tp_hits']) > 0:
                print(f"   TP Hit Rate: {(len(self.stats['tp_hits']) / max(self.stats['signals_executed'], 1) * 100):.1f}%")
        
        print("="*80)
        self.stats['last_report'] = datetime.now()
    
    def run(self):
        """Main monitoring loop"""
        print("🚀 Starting Extended Bot Monitor...")
        print(f"   Log file: {LOG_FILE}")
        print(f"   Check interval: {CHECK_INTERVAL}s")
        print(f"   Quick status: every {STATUS_INTERVAL}s")
        print(f"   Full report: every {REPORT_INTERVAL}s")
        print("   Press Ctrl+C to stop\n")
        
        # Initial full report
        self.print_full_report()
        
        last_status = datetime.now()
        last_report = datetime.now()
        
        try:
            while True:
                if self.is_bot_running():
                    # Get new logs since last check
                    logs = self.get_new_logs()
                    if logs:
                        events = self.analyze_logs(logs)
                        self.update_stats(events)
                    
                    # Quick status every STATUS_INTERVAL
                    if (datetime.now() - last_status).total_seconds() >= STATUS_INTERVAL:
                        self.print_quick_status()
                        last_status = datetime.now()
                    
                    # Full report every REPORT_INTERVAL
                    if (datetime.now() - last_report).total_seconds() >= REPORT_INTERVAL:
                        self.print_full_report()
                        last_report = datetime.now()
                else:
                    print(f"\n❌ Bot is NOT RUNNING! | {datetime.now().strftime('%H:%M:%S')}")
                    print("   Waiting for bot to restart...")
                
                time.sleep(CHECK_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitor stopped by user")
            print("\n📊 Final Statistics:")
            self.print_full_report()
            print("\n✅ Monitoring session ended")

if __name__ == "__main__":
    monitor = ExtendedBotMonitor()
    monitor.run()

