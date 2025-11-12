"""
Institutional Strategy Backtesting Engine
Walk-forward optimization with realistic execution simulation
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging

from institutional_indicators import InstitutionalIndicators
from institutional_universe import UniverseFilter, RegimeClassifier, MarketData
from institutional_risk import RiskManager, PositionSize
from institutional_strategies import LSVRStrategy, VWAPMRStrategy, TrendStrategy, TradeSignal

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Individual trade record"""
    entry_time: datetime
    exit_time: Optional[datetime]
    symbol: str
    side: str
    strategy: str
    entry_price: float
    exit_price: Optional[float]
    stop_price: float
    size: float  # contracts
    notional: float  # USD
    pnl: float  # USD
    pnl_pct: float  # % of position
    mae: float  # Maximum Adverse Excursion (worst drawdown)
    mfe: float  # Maximum Favorable Excursion (best profit)
    duration_min: float  # Minutes in trade
    exit_reason: str  # 'tp1', 'tp2', 'tp3', 'sl', 'time', 'tripwire'
    tp_hit: int  # Which TP was hit (1, 2, 3) or 0
    fees_paid: float  # USD
    slippage_cost: float  # USD
    metadata: Dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Backtest results summary"""
    start_date: datetime
    end_date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    total_pnl: float
    total_return_pct: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    
    avg_mae: float
    avg_mfe: float
    avg_trade_duration_min: float
    
    tp1_hits: int
    tp2_hits: int
    tp3_hits: int
    sl_hits: int
    time_stops: int
    tripwires: int
    
    total_fees: float
    total_slippage: float
    
    trades: List[Trade]
    equity_curve: pd.DataFrame
    
    # Gate statistics
    total_signals: int
    signals_passed_gates: int
    signals_failed_liq_guards: int
    
    # Hour-of-day edge
    pnl_by_hour: Dict[int, float]


class InstitutionalBacktester:
    """Backtest engine with walk-forward optimization"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.backtest_config = config.get('backtesting', {})
        
        # Initialize components
        self.indicators = InstitutionalIndicators(config)
        self.universe_filter = UniverseFilter(config)
        self.regime_classifier = RegimeClassifier(config)
        self.risk_manager = RiskManager(config)
        
        # Fees and slippage
        self.maker_fee_bps = self.backtest_config.get('fees', {}).get('maker_bps', 2)
        self.taker_fee_bps = self.backtest_config.get('fees', {}).get('taker_bps', 6)
        self.slippage_config = self.backtest_config.get('slippage', {})
        
        logger.info("✅ Institutional Backtester initialized")
    
    def calculate_slippage(self, spread_bps: float, is_taker: bool = False) -> float:
        """
        Calculate slippage in basis points
        
        Spread-based slippage for post-only (maker) fills
        Additional slippage for taker fills
        """
        if not is_taker:
            # Maker: pay half spread
            return spread_bps / 2
        else:
            # Taker: pay full spread + additional impact
            return spread_bps + self.slippage_config.get('min_bps', 1)
    
    def simulate_fill(self, signal: TradeSignal, market_data: MarketData, 
                      bars_waited: int = 0) -> Tuple[float, bool, float, float]:
        """
        Simulate order fill
        
        Returns:
            (fill_price, is_taker, fees_bps, slippage_bps)
        """
        # Post-only first (maker)
        if bars_waited == 0:
            is_taker = False
            fill_price = signal.entry_price
            fees_bps = self.maker_fee_bps
            slippage_bps = self.calculate_slippage(market_data.spread_bps, is_taker=False)
        
        # After 2 bars, fall back to taker (size -30%)
        else:
            is_taker = True
            fill_price = market_data.last_price
            fees_bps = self.taker_fee_bps
            slippage_bps = self.calculate_slippage(market_data.spread_bps, is_taker=True)
        
        return fill_price, is_taker, fees_bps, slippage_bps
    
    def run_backtest(self, symbol: str, df: pd.DataFrame, 
                     initial_capital: float = 1000.0) -> BacktestResult:
        """
        Run backtest on single symbol
        
        Args:
            symbol: Trading symbol
            df: DataFrame with OHLCV data (5m resolution)
            initial_capital: Starting capital in USDT
        
        Returns:
            BacktestResult
        """
        logger.info(f"🚀 Running backtest for {symbol} | {len(df)} bars | ${initial_capital:.2f} capital")
        
        # Determine bucket
        bucket = self.universe_filter.get_bucket(symbol)
        
        # Calculate all indicators
        logger.info("  📊 Calculating indicators...")
        df_5m = self.indicators.calculate_all_indicators(df.copy(), timeframe='5m')
        
        # We need 15m data for regime classification
        # Resample 5m to 15m
        df_15m = self._resample_to_15m(df.copy())
        df_15m = self.indicators.calculate_all_indicators(df_15m, timeframe='15m')
        
        # Initialize strategies
        lsvr = LSVRStrategy(self.config, bucket)
        vwap_mr = VWAPMRStrategy(self.config, bucket)
        trend = TrendStrategy(self.config)
        
        # Backtest state
        capital = initial_capital
        position: Optional[Dict] = None
        trades: List[Trade] = []
        equity_curve = []
        
        # Statistics
        total_signals = 0
        signals_passed_gates = 0
        signals_failed_liq_guards = 0
        pnl_by_hour = {}
        
        logger.info("  🔄 Simulating trades...")
        
        # Iterate through bars
        for i in range(100, len(df_5m)):  # Start after warmup period
            current_time = df_5m.index[i] if isinstance(df_5m.index, pd.DatetimeIndex) else pd.to_datetime(df_5m['timestamp'].iloc[i], unit='ms')
            current_bar = df_5m.iloc[i]
            
            # Check if in position
            if position:
                # Update MAE/MFE
                current_price = current_bar['close']
                unrealized_pnl = (current_price - position['entry_price']) * position['size'] * (1 if position['side'] == 'long' else -1)
                position['mae'] = min(position['mae'], unrealized_pnl)
                position['mfe'] = max(position['mfe'], unrealized_pnl)
                
                # Check exit conditions
                exit_reason, exit_price = self._check_exits(position, current_bar, current_time)
                
                if exit_reason:
                    # Close position
                    trade = self._close_position(position, exit_price, exit_reason, current_time, capital)
                    trades.append(trade)
                    capital += trade.pnl - trade.fees_paid - trade.slippage_cost
                    position = None
                    
                    logger.debug(
                        f"  💰 Trade closed | {trade.side.upper()} {trade.symbol} | "
                        f"PnL: ${trade.pnl:.2f} ({trade.pnl_pct:.2f}%) | "
                        f"Exit: {exit_reason} | Duration: {trade.duration_min:.1f}min"
                    )
            
            # Check for new signals (if not in position)
            if not position:
                # Get regime
                regime_idx = self._find_nearest_15m_idx(df_15m, current_time)
                if regime_idx is None:
                    continue
                
                regime_data = self.regime_classifier.classify_from_indicators(df_15m, bucket, regime_idx)
                
                # Get levels
                levels_dict = self._get_levels_dict(df_5m, i)
                
                # Generate signal based on regime
                signal = None
                
                if regime_data.regime == 'Range':
                    # Try LSVR first
                    signal = lsvr.generate_signal(df_5m, levels_dict, i)
                    
                    # If no LSVR signal, try VWAP-MR
                    if not signal:
                        signal = vwap_mr.generate_signal(df_5m, i)
                
                elif regime_data.regime == 'Trend' and self.config.get('features', {}).get('enable_trend_fallback', True):
                    signal = trend.generate_signal(df_15m, regime_idx)
                
                if signal:
                    total_signals += 1
                    
                    # Check universe gates
                    market_data = self._create_market_data(symbol, current_bar, bucket)
                    passes_gates, gate_reason = self.universe_filter.passes_gates(market_data, bucket)
                    
                    if not passes_gates:
                        logger.debug(f"  ❌ Signal rejected: {gate_reason}")
                        continue
                    
                    signals_passed_gates += 1
                    
                    # Calculate position size with liq guards
                    position_size = self.risk_manager.calculate_position_size(
                        symbol=symbol,
                        side=signal.side,
                        entry_price=signal.entry_price,
                        stop_price=signal.stop_price,
                        equity_usdt=capital,
                        lot_size=0.001,
                        min_qty=0.001
                    )
                    
                    if position_size.contracts == 0 or not position_size.passed_liq_guards:
                        logger.debug(f"  ❌ Signal rejected: {position_size.reason}")
                        signals_failed_liq_guards += 1
                        continue
                    
                    # Simulate fill
                    fill_price, is_taker, fees_bps, slippage_bps = self.simulate_fill(signal, market_data)
                    
                    # Open position
                    position = {
                        'entry_time': current_time,
                        'symbol': symbol,
                        'side': signal.side,
                        'strategy': signal.strategy,
                        'entry_price': fill_price,
                        'stop_price': signal.stop_price,
                        'size': position_size.contracts,
                        'notional': position_size.notional_usd,
                        'tp_levels': signal.tp_levels,
                        'tp_hit_count': 0,
                        'remaining_size': position_size.contracts,
                        'mae': 0.0,
                        'mfe': 0.0,
                        'fees_bps': fees_bps,
                        'slippage_bps': slippage_bps,
                        'time_stop_time': current_time + timedelta(minutes=np.random.randint(signal.metadata.get('time_stop_range', [20, 30])[0], 
                                                                                             signal.metadata.get('time_stop_range', [20, 30])[1])),
                        'moved_to_be': False,
                        'metadata': signal.metadata
                    }
                    
                    logger.debug(
                        f"  📍 Position opened | {signal.strategy} {signal.side.upper()} @ ${fill_price:.4f} | "
                        f"Size: {position_size.contracts:.4f} (${position_size.notional_usd:.2f}) | "
                        f"SL: ${signal.stop_price:.4f}"
                    )
            
            # Update equity curve
            unrealized_pnl = 0
            if position:
                current_price = current_bar['close']
                unrealized_pnl = (current_price - position['entry_price']) * position['remaining_size'] * (1 if position['side'] == 'long' else -1)
            
            equity_curve.append({
                'timestamp': current_time,
                'capital': capital,
                'unrealized_pnl': unrealized_pnl,
                'equity': capital + unrealized_pnl
            })
        
        # Force close any remaining position
        if position:
            final_bar = df_5m.iloc[-1]
            final_time = df_5m.index[-1] if isinstance(df_5m.index, pd.DatetimeIndex) else pd.to_datetime(df_5m['timestamp'].iloc[-1], unit='ms')
            trade = self._close_position(position, final_bar['close'], 'end_of_data', final_time, capital)
            trades.append(trade)
            capital += trade.pnl - trade.fees_paid - trade.slippage_cost
        
        # Calculate results
        logger.info(f"  ✅ Backtest complete | {len(trades)} trades executed")
        
        return self._calculate_results(
            trades=trades,
            equity_curve=pd.DataFrame(equity_curve),
            initial_capital=initial_capital,
            final_capital=capital,
            start_date=df_5m.index[0] if isinstance(df_5m.index, pd.DatetimeIndex) else pd.to_datetime(df_5m['timestamp'].iloc[0], unit='ms'),
            end_date=df_5m.index[-1] if isinstance(df_5m.index, pd.DatetimeIndex) else pd.to_datetime(df_5m['timestamp'].iloc[-1], unit='ms'),
            total_signals=total_signals,
            signals_passed_gates=signals_passed_gates,
            signals_failed_liq_guards=signals_failed_liq_guards
        )
    
    def _check_exits(self, position: Dict, current_bar: pd.Series, 
                     current_time: datetime) -> Tuple[Optional[str], Optional[float]]:
        """Check all exit conditions"""
        current_price = current_bar['close']
        side = position['side']
        
        # 1. Check stop loss
        if side == 'long':
            if current_price <= position['stop_price']:
                return 'sl', position['stop_price']
        else:
            if current_price >= position['stop_price']:
                return 'sl', position['stop_price']
        
        # 2. Check TP levels
        for tp_idx, (tp_price, tp_size_frac) in enumerate(position['tp_levels']):
            if position['tp_hit_count'] <= tp_idx:
                hit = False
                if side == 'long':
                    hit = current_price >= tp_price
                else:
                    hit = current_price <= tp_price
                
                if hit:
                    # Hit TP
                    position['tp_hit_count'] += 1
                    
                    # Exit partial size
                    exit_size = position['size'] * tp_size_frac
                    position['remaining_size'] -= exit_size
                    
                    # Move SL to BE after TP1
                    if tp_idx == 0 and not position['moved_to_be']:
                        position['stop_price'] = position['entry_price']
                        position['moved_to_be'] = True
                    
                    # If all size exited, close position
                    if position['remaining_size'] <= 0.001:
                        return f'tp{tp_idx + 1}', tp_price
                    
                    # Continue with remaining size
                    break
        
        # 3. Check time stop
        if current_time >= position['time_stop_time']:
            return 'time', current_price
        
        # 4. Check tripwires (adverse spike)
        atr = current_bar.get('atr', 0)
        if atr > 0:
            candle_range = abs(current_bar['close'] - current_bar['open'])
            if candle_range >= (1.7 * atr):
                # Check if against position
                if side == 'long' and current_bar['close'] < current_bar['open']:
                    return 'tripwire', current_price
                elif side == 'short' and current_bar['close'] > current_bar['open']:
                    return 'tripwire', current_price
        
        return None, None
    
    def _close_position(self, position: Dict, exit_price: float, exit_reason: str, 
                        exit_time: datetime, current_capital: float) -> Trade:
        """Close position and calculate trade metrics"""
        side = position['side']
        size = position['size']
        entry_price = position['entry_price']
        
        # Calculate PnL
        price_diff = exit_price - entry_price
        if side == 'short':
            price_diff = -price_diff
        
        pnl_usd = price_diff * size
        pnl_pct = (price_diff / entry_price) * 100 * self.risk_manager.leverage
        
        # Calculate fees (entry + exit)
        fees_usd = (position['notional'] * (position['fees_bps'] + self.taker_fee_bps) / 10000)
        
        # Calculate slippage
        slippage_usd = (position['notional'] * (position['slippage_bps'] + self.slippage_config.get('min_bps', 1)) / 10000)
        
        # Duration
        duration_min = (exit_time - position['entry_time']).total_seconds() / 60
        
        # Determine TP hit
        tp_hit = 0
        if 'tp' in exit_reason:
            tp_hit = int(exit_reason.replace('tp', ''))
        
        return Trade(
            entry_time=position['entry_time'],
            exit_time=exit_time,
            symbol=position['symbol'],
            side=side,
            strategy=position['strategy'],
            entry_price=entry_price,
            exit_price=exit_price,
            stop_price=position['stop_price'],
            size=size,
            notional=position['notional'],
            pnl=pnl_usd,
            pnl_pct=pnl_pct,
            mae=position['mae'],
            mfe=position['mfe'],
            duration_min=duration_min,
            exit_reason=exit_reason,
            tp_hit=tp_hit,
            fees_paid=fees_usd,
            slippage_cost=slippage_usd,
            metadata=position['metadata']
        )
    
    def _calculate_results(self, trades: List[Trade], equity_curve: pd.DataFrame,
                           initial_capital: float, final_capital: float,
                           start_date: datetime, end_date: datetime,
                           total_signals: int, signals_passed_gates: int,
                           signals_failed_liq_guards: int) -> BacktestResult:
        """Calculate comprehensive backtest results"""
        if len(trades) == 0:
            return BacktestResult(
                start_date=start_date,
                end_date=end_date,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                total_return_pct=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                avg_mae=0.0,
                avg_mfe=0.0,
                avg_trade_duration_min=0.0,
                tp1_hits=0,
                tp2_hits=0,
                tp3_hits=0,
                sl_hits=0,
                time_stops=0,
                tripwires=0,
                total_fees=0.0,
                total_slippage=0.0,
                trades=[],
                equity_curve=equity_curve,
                total_signals=total_signals,
                signals_passed_gates=signals_passed_gates,
                signals_failed_liq_guards=signals_failed_liq_guards,
                pnl_by_hour={}
            )
        
        # Basic stats
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        total_pnl = sum(t.pnl for t in trades)
        total_return_pct = ((final_capital - initial_capital) / initial_capital) * 100
        
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0.0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0.0
        
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        
        # Sharpe ratio
        returns = equity_curve['equity'].pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252 * 288) if len(returns) > 0 and returns.std() > 0 else 0.0  # 288 5min periods per day
        
        # Max drawdown
        equity = equity_curve['equity']
        running_max = equity.expanding().max()
        drawdown = equity - running_max
        max_drawdown = drawdown.min()
        max_drawdown_pct = (max_drawdown / running_max[drawdown.idxmin()]) * 100 if len(equity) > 0 else 0.0
        
        # MAE/MFE
        avg_mae = np.mean([t.mae for t in trades])
        avg_mfe = np.mean([t.mfe for t in trades])
        
        # Duration
        avg_trade_duration_min = np.mean([t.duration_min for t in trades])
        
        # Exit reasons
        tp1_hits = sum(1 for t in trades if t.tp_hit == 1)
        tp2_hits = sum(1 for t in trades if t.tp_hit == 2)
        tp3_hits = sum(1 for t in trades if t.tp_hit == 3)
        sl_hits = sum(1 for t in trades if t.exit_reason == 'sl')
        time_stops = sum(1 for t in trades if t.exit_reason == 'time')
        tripwires = sum(1 for t in trades if t.exit_reason == 'tripwire')
        
        # Fees and slippage
        total_fees = sum(t.fees_paid for t in trades)
        total_slippage = sum(t.slippage_cost for t in trades)
        
        # PnL by hour
        pnl_by_hour = {}
        for trade in trades:
            hour = trade.entry_time.hour
            pnl_by_hour[hour] = pnl_by_hour.get(hour, 0.0) + trade.pnl
        
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=len(winning_trades) / len(trades) * 100,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            avg_mae=avg_mae,
            avg_mfe=avg_mfe,
            avg_trade_duration_min=avg_trade_duration_min,
            tp1_hits=tp1_hits,
            tp2_hits=tp2_hits,
            tp3_hits=tp3_hits,
            sl_hits=sl_hits,
            time_stops=time_stops,
            tripwires=tripwires,
            total_fees=total_fees,
            total_slippage=total_slippage,
            trades=trades,
            equity_curve=equity_curve,
            total_signals=total_signals,
            signals_passed_gates=signals_passed_gates,
            signals_failed_liq_guards=signals_failed_liq_guards,
            pnl_by_hour=pnl_by_hour
        )
    
    def _resample_to_15m(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resample 5m data to 15m"""
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'timestamp' in df.columns:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.set_index('datetime')
            else:
                df.index = pd.to_datetime(df.index)
        
        resampled = df.resample('15T').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return resampled
    
    def _find_nearest_15m_idx(self, df_15m: pd.DataFrame, target_time: datetime) -> Optional[int]:
        """Find nearest 15m bar index for a given 5m time"""
        if not isinstance(df_15m.index, pd.DatetimeIndex):
            return None
        
        # Find nearest index
        idx = df_15m.index.searchsorted(target_time)
        if idx >= len(df_15m):
            idx = len(df_15m) - 1
        elif idx > 0 and abs(df_15m.index[idx-1] - target_time) < abs(df_15m.index[idx] - target_time):
            idx -= 1
        
        return idx
    
    def _get_levels_dict(self, df: pd.DataFrame, current_idx: int) -> Dict:
        """Get price levels (PDH/PDL, Asia H/L)"""
        current_time = df.index[current_idx] if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df['timestamp'].iloc[current_idx], unit='ms')
        levels = self.indicators.calculate_levels(df, current_time)
        
        return {
            'pdh': levels.pdh,
            'pdl': levels.pdl,
            'asia_high': levels.asia_high,
            'asia_low': levels.asia_low
        }
    
    def _create_market_data(self, symbol: str, current_bar: pd.Series, bucket: str) -> MarketData:
        """Create MarketData from current bar"""
        # Estimate spread based on volatility
        volatility = current_bar.get('atr', 0) / current_bar['close'] if current_bar['close'] > 0 else 0.01
        spread_bps = max(5, min(15, volatility * 10000))
        
        # Estimate depth
        volume_usd = current_bar['volume'] * current_bar['close']
        depth_usd = volume_usd * 0.1  # Assume 10% of volume is TOB depth
        
        # Estimate 24h volume (sum of last 288 bars if available)
        quote_vol_24h = volume_usd * 288  # Rough estimate
        
        return MarketData(
            symbol=symbol,
            spread_bps=spread_bps,
            bid_depth_usd=depth_usd / 2,
            ask_depth_usd=depth_usd / 2,
            quote_vol_24h=quote_vol_24h,
            last_price=current_bar['close']
        )


def print_backtest_report(result: BacktestResult, symbol: str):
    """Print formatted backtest report"""
    print("\n" + "="*80)
    print(f"📊 BACKTEST REPORT: {symbol}")
    print("="*80)
    print(f"\n📅 Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
    print(f"⏱️  Duration: {(result.end_date - result.start_date).days} days\n")
    
    print("💰 Performance:")
    print(f"  Total PnL: ${result.total_pnl:.2f}")
    print(f"  Total Return: {result.total_return_pct:.2f}%")
    print(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: ${result.max_drawdown:.2f} ({result.max_drawdown_pct:.2f}%)\n")
    
    print("📈 Trade Statistics:")
    print(f"  Total Trades: {result.total_trades}")
    print(f"  Win Rate: {result.win_rate:.1f}% ({result.winning_trades}W / {result.losing_trades}L)")
    print(f"  Avg Win: ${result.avg_win:.2f}")
    print(f"  Avg Loss: ${result.avg_loss:.2f}")
    print(f"  Profit Factor: {result.profit_factor:.2f}\n")
    
    print("🎯 Execution Quality:")
    print(f"  Avg MAE: ${result.avg_mae:.2f}")
    print(f"  Avg MFE: ${result.avg_mfe:.2f}")
    print(f"  Avg Duration: {result.avg_trade_duration_min:.1f} min\n")
    
    print("🏁 Exit Breakdown:")
    print(f"  TP1 Hits: {result.tp1_hits}")
    print(f"  TP2 Hits: {result.tp2_hits}")
    print(f"  TP3 Hits: {result.tp3_hits}")
    print(f"  Stop Losses: {result.sl_hits}")
    print(f"  Time Stops: {result.time_stops}")
    print(f"  Tripwires: {result.tripwires}\n")
    
    print("💸 Costs:")
    print(f"  Total Fees: ${result.total_fees:.2f}")
    print(f"  Total Slippage: ${result.total_slippage:.2f}")
    print(f"  Total Costs: ${result.total_fees + result.total_slippage:.2f}\n")
    
    print("🚪 Gate Statistics:")
    print(f"  Total Signals: {result.total_signals}")
    print(f"  Passed Gates: {result.signals_passed_gates}")
    print(f"  Failed Liq Guards: {result.signals_failed_liq_guards}")
    print(f"  Gate Pass Rate: {(result.signals_passed_gates/result.total_signals*100) if result.total_signals > 0 else 0:.1f}%\n")
    
    if result.pnl_by_hour:
        print("⏰ PnL by Hour (UTC):")
        for hour in sorted(result.pnl_by_hour.keys()):
            pnl = result.pnl_by_hour[hour]
            print(f"  {hour:02d}:00 - ${pnl:.2f}")
    
    print("\n" + "="*80 + "\n")

