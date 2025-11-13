"""
Comprehensive Trade Tracker for Institutional Live Trading
Tracks every trade with full details for later analysis
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Complete trade record for analysis"""
    
    # Trade identification
    trade_id: str
    symbol: str
    side: str  # "long" or "short"
    strategy: str  # "LSVR", "VWAP-MR", "Trend"
    regime: str  # "Range" or "Trend"
    
    # Entry details
    entry_time: str  # ISO format
    entry_price: float
    entry_size: float  # contracts
    entry_notional: float  # USD
    entry_equity: float  # Account equity at entry
    
    # Risk parameters
    stop_price: float
    tp1_price: Optional[float] = None
    tp2_price: Optional[float] = None
    tp3_price: Optional[float] = None
    leverage: int = 25
    margin_fraction: float = 0.10
    
    # Market conditions at entry
    entry_adx: Optional[float] = None
    entry_rsi: Optional[float] = None
    entry_bb_width_pct: Optional[float] = None
    entry_vwap_slope: Optional[float] = None
    entry_volume_ratio: Optional[float] = None
    entry_atr: Optional[float] = None
    
    # Exit details
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "TP1", "TP2", "TP3", "SL", "Trailing", "Time-Stop", "Manual"
    exit_size: Optional[float] = None  # Size at exit
    
    # Performance metrics
    duration_seconds: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None  # % of entry price
    pnl_pct_capital: Optional[float] = None  # % of capital (leveraged)
    fees_entry: Optional[float] = None
    fees_exit: Optional[float] = None
    net_pnl: Optional[float] = None
    
    # Peak performance
    peak_pnl_usd: Optional[float] = None
    peak_pnl_pct: Optional[float] = None
    peak_price: Optional[float] = None
    drawdown_from_peak: Optional[float] = None
    
    # TP/SL behavior
    tp1_hit: bool = False
    tp1_hit_time: Optional[str] = None
    tp2_hit: bool = False
    tp2_hit_time: Optional[str] = None
    tp3_hit: bool = False
    tp3_hit_time: Optional[str] = None
    trailing_stop_activated: bool = False
    trailing_stop_trigger_price: Optional[float] = None
    moved_to_breakeven: bool = False
    breakeven_time: Optional[str] = None
    
    # Market conditions at exit
    exit_adx: Optional[float] = None
    exit_rsi: Optional[float] = None
    exit_bb_width_pct: Optional[float] = None
    exit_vwap_slope: Optional[float] = None
    
    # Additional metadata
    bucket: Optional[str] = None  # "Majors", "Mid-caps", "Micros"
    sweep_level: Optional[float] = None  # For LSVR
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        return data
    
    def to_csv_row(self) -> List:
        """Convert to CSV row"""
        return [
            self.trade_id,
            self.symbol,
            self.side,
            self.strategy,
            self.regime,
            self.entry_time,
            self.entry_price,
            self.entry_size,
            self.entry_notional,
            self.entry_equity,
            self.stop_price,
            self.tp1_price,
            self.tp2_price,
            self.tp3_price,
            self.leverage,
            self.margin_fraction,
            self.entry_adx,
            self.entry_rsi,
            self.entry_bb_width_pct,
            self.entry_vwap_slope,
            self.entry_volume_ratio,
            self.entry_atr,
            self.exit_time,
            self.exit_price,
            self.exit_reason,
            self.exit_size,
            self.duration_seconds,
            self.pnl_usd,
            self.pnl_pct,
            self.pnl_pct_capital,
            self.fees_entry,
            self.fees_exit,
            self.net_pnl,
            self.peak_pnl_usd,
            self.peak_pnl_pct,
            self.peak_price,
            self.drawdown_from_peak,
            self.tp1_hit,
            self.tp1_hit_time,
            self.tp2_hit,
            self.tp2_hit_time,
            self.tp3_hit,
            self.tp3_hit_time,
            self.trailing_stop_activated,
            self.trailing_stop_trigger_price,
            self.moved_to_breakeven,
            self.breakeven_time,
            self.exit_adx,
            self.exit_rsi,
            self.exit_bb_width_pct,
            self.exit_vwap_slope,
            self.bucket,
            self.sweep_level,
            json.dumps(self.metadata) if self.metadata else "",
        ]


class TradeTracker:
    """Track all trades for analysis"""
    
    CSV_HEADER = [
        "trade_id", "symbol", "side", "strategy", "regime",
        "entry_time", "entry_price", "entry_size", "entry_notional", "entry_equity",
        "stop_price", "tp1_price", "tp2_price", "tp3_price", "leverage", "margin_fraction",
        "entry_adx", "entry_rsi", "entry_bb_width_pct", "entry_vwap_slope", "entry_volume_ratio", "entry_atr",
        "exit_time", "exit_price", "exit_reason", "exit_size",
        "duration_seconds", "pnl_usd", "pnl_pct", "pnl_pct_capital", "fees_entry", "fees_exit", "net_pnl",
        "peak_pnl_usd", "peak_pnl_pct", "peak_price", "drawdown_from_peak",
        "tp1_hit", "tp1_hit_time", "tp2_hit", "tp2_hit_time", "tp3_hit", "tp3_hit_time",
        "trailing_stop_activated", "trailing_stop_trigger_price", "moved_to_breakeven", "breakeven_time",
        "exit_adx", "exit_rsi", "exit_bb_width_pct", "exit_vwap_slope",
        "bucket", "sweep_level", "metadata",
    ]
    
    def __init__(self, data_dir: str = "trades_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # Files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.json_file = self.data_dir / f"trades_{timestamp}.jsonl"
        self.csv_file = self.data_dir / f"trades_{timestamp}.csv"
        
        # Initialize CSV file
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.CSV_HEADER)
        
        # Active trades (by trade_id)
        self.active_trades: Dict[str, TradeRecord] = {}
        
        logger.info(f"✅ TradeTracker initialized")
        logger.info(f"   JSON: {self.json_file}")
        logger.info(f"   CSV: {self.csv_file}")
    
    def start_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        strategy: str,
        regime: str,
        entry_time: datetime,
        entry_price: float,
        entry_size: float,
        entry_notional: float,
        entry_equity: float,
        stop_price: float,
        tp_levels: List[tuple],
        leverage: int = 25,
        margin_fraction: float = 0.10,
        entry_indicators: Optional[Dict] = None,
        bucket: Optional[str] = None,
        sweep_level: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> TradeRecord:
        """Start tracking a new trade"""
        
        # Extract TP levels
        tp1_price = tp_levels[0][0] if len(tp_levels) > 0 else None
        tp2_price = tp_levels[1][0] if len(tp_levels) > 1 else None
        tp3_price = tp_levels[2][0] if len(tp_levels) > 2 else None
        
        # Extract indicators
        indicators = entry_indicators or {}
        
        trade = TradeRecord(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            strategy=strategy,
            regime=regime,
            entry_time=entry_time.isoformat(),
            entry_price=entry_price,
            entry_size=entry_size,
            entry_notional=entry_notional,
            entry_equity=entry_equity,
            stop_price=stop_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            tp3_price=tp3_price,
            leverage=leverage,
            margin_fraction=margin_fraction,
            entry_adx=indicators.get('adx'),
            entry_rsi=indicators.get('rsi'),
            entry_bb_width_pct=indicators.get('bb_width_pct'),
            entry_vwap_slope=indicators.get('vwap_slope'),
            entry_volume_ratio=indicators.get('volume_ratio'),
            entry_atr=indicators.get('atr'),
            bucket=bucket,
            sweep_level=sweep_level,
            metadata=metadata or {},
        )
        
        self.active_trades[trade_id] = trade
        
        logger.info(f"📊 Trade started: {trade_id} | {symbol} {side.upper()} | Strategy: {strategy} | Regime: {regime}")
        
        return trade
    
    def update_tp_hit(
        self,
        trade_id: str,
        tp_level: int,  # 1, 2, or 3
        hit_time: datetime,
    ):
        """Record TP hit"""
        if trade_id not in self.active_trades:
            return
        
        trade = self.active_trades[trade_id]
        
        if tp_level == 1:
            trade.tp1_hit = True
            trade.tp1_hit_time = hit_time.isoformat()
        elif tp_level == 2:
            trade.tp2_hit = True
            trade.tp2_hit_time = hit_time.isoformat()
        elif tp_level == 3:
            trade.tp3_hit = True
            trade.tp3_hit_time = hit_time.isoformat()
        
        logger.debug(f"📊 TP{tp_level} hit: {trade_id} | {trade.symbol}")
    
    def update_trailing_stop(
        self,
        trade_id: str,
        activated: bool,
        trigger_price: Optional[float] = None,
    ):
        """Record trailing stop activation"""
        if trade_id not in self.active_trades:
            return
        
        trade = self.active_trades[trade_id]
        trade.trailing_stop_activated = activated
        trade.trailing_stop_trigger_price = trigger_price
        
        logger.debug(f"📊 Trailing stop {'activated' if activated else 'updated'}: {trade_id} | {trade.symbol}")
    
    def update_breakeven(
        self,
        trade_id: str,
        moved: bool,
        move_time: Optional[datetime] = None,
    ):
        """Record breakeven move"""
        if trade_id not in self.active_trades:
            return
        
        trade = self.active_trades[trade_id]
        trade.moved_to_breakeven = moved
        if move_time:
            trade.breakeven_time = move_time.isoformat()
        
        logger.debug(f"📊 Breakeven moved: {trade_id} | {trade.symbol}")
    
    def update_peak(
        self,
        trade_id: str,
        peak_pnl_usd: float,
        peak_pnl_pct: float,
        peak_price: float,
    ):
        """Update peak performance"""
        if trade_id not in self.active_trades:
            return
        
        trade = self.active_trades[trade_id]
        trade.peak_pnl_usd = peak_pnl_usd
        trade.peak_pnl_pct = peak_pnl_pct
        trade.peak_price = peak_price
    
    def close_trade(
        self,
        trade_id: str,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
        exit_size: float,
        fees_entry: float = 0.0,
        fees_exit: float = 0.0,
        exit_indicators: Optional[Dict] = None,
    ):
        """Close and finalize a trade"""
        if trade_id not in self.active_trades:
            logger.warning(f"⚠️ Trade {trade_id} not found for closing")
            return
        
        trade = self.active_trades[trade_id]
        
        # Calculate duration
        entry_dt = datetime.fromisoformat(trade.entry_time)
        duration = (exit_time - entry_dt).total_seconds()
        
        # Calculate P&L
        if trade.side == "long":
            price_change = exit_price - trade.entry_price
        else:
            price_change = trade.entry_price - exit_price
        
        pnl_pct = (price_change / trade.entry_price) * 100
        pnl_usd = price_change * exit_size * trade.entry_price  # Approximate

        # Net P&L (after fees)
        net_pnl = pnl_usd - fees_entry - fees_exit

        # ROE = Return on Equity = (Net Profit / Capital Invested) * 100
        # This gives the actual percentage return on the capital invested
        pnl_pct_capital = (net_pnl / trade.capital) * 100 if trade.capital > 0 else 0
        
        # Drawdown from peak
        drawdown = 0.0
        if trade.peak_pnl_usd is not None:
            drawdown = trade.peak_pnl_usd - net_pnl
        
        # Update trade record
        trade.exit_time = exit_time.isoformat()
        trade.exit_price = exit_price
        trade.exit_reason = exit_reason
        trade.exit_size = exit_size
        trade.duration_seconds = duration
        trade.pnl_usd = pnl_usd
        trade.pnl_pct = pnl_pct
        trade.pnl_pct_capital = pnl_pct_capital
        trade.fees_entry = fees_entry
        trade.fees_exit = fees_exit
        trade.net_pnl = net_pnl
        trade.drawdown_from_peak = drawdown
        
        # Exit indicators
        if exit_indicators:
            trade.exit_adx = exit_indicators.get('adx')
            trade.exit_rsi = exit_indicators.get('rsi')
            trade.exit_bb_width_pct = exit_indicators.get('bb_width_pct')
            trade.exit_vwap_slope = exit_indicators.get('vwap_slope')
        
        # Save to files
        self._save_trade(trade)
        
        # Remove from active
        del self.active_trades[trade_id]
        
        # Log summary
        win_emoji = "✅" if net_pnl > 0 else "❌"
        logger.info(
            f"{win_emoji} TRADE CLOSED: {trade_id} | {trade.symbol} {trade.side.upper()} | "
            f"P&L: ${net_pnl:.2f} ({pnl_pct:+.2f}%) | "
            f"Reason: {exit_reason} | Duration: {duration/60:.1f}m"
        )
    
    def _save_trade(self, trade: TradeRecord):
        """Save trade to JSONL and CSV"""
        try:
            # Save to JSONL
            with open(self.json_file, 'a') as f:
                f.write(json.dumps(trade.to_dict()) + '\n')
            
            # Save to CSV
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(trade.to_csv_row())
        except Exception as e:
            logger.error(f"❌ Failed to save trade {trade.trade_id}: {e}")
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        # Read all trades from JSONL
        trades = []
        if self.json_file.exists():
            with open(self.json_file, 'r') as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        
        if not trades:
            return {"total_trades": 0}
        
        wins = [t for t in trades if t.get('net_pnl', 0) > 0]
        losses = [t for t in trades if t.get('net_pnl', 0) <= 0]
        
        total_pnl = sum(t.get('net_pnl', 0) for t in trades)
        avg_pnl = total_pnl / len(trades) if trades else 0
        
        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(trades) if trades else 0,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "best_trade": max(trades, key=lambda x: x.get('net_pnl', 0)) if trades else None,
            "worst_trade": min(trades, key=lambda x: x.get('net_pnl', 0)) if trades else None,
        }

