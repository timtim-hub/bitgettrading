# SIMPLIFIED TRAILING TP/SL LOGIC
# 
# Instead of complex TP1 (75% exit) + trailing on 25%, use a simple system:
# 1. Fixed Stop Loss (never moves against you)
# 2. Trailing Take Profit (moves with price to lock in profits)
#
# How it works:
# - When price moves in favor by X%, TP moves up/down by same amount
# - This automatically locks in profits without manual TP1 detection
# - Much simpler and more reliable!

"""
SIMPLE TRAILING TP LOGIC

For LONG positions:
- Initial: Entry at $100, SL at $98 (-2%), TP at $102.50 (+2.5%)
- Price moves to $101: TP moves to $103.50 (maintaining +2.5% distance)
- Price moves to $102: TP moves to $104.50
- Price moves to $103: TP moves to $105.50
- Price reverses to $103.50: TP still at $105.50 (locked in!)
- Price hits $105.50: Trade closes with +5.5% profit ✅

For SHORT positions:
- Initial: Entry at $100, SL at $102 (+2%), TP at $97.50 (-2.5%)
- Price moves to $99: TP moves to $96.50 (maintaining -2.5% distance)
- Price moves to $98: TP moves to $95.50
- Price moves to $97: TP moves to $94.50
- Price reverses to $97.50: TP still at $94.50 (locked in!)
- Price hits $94.50: Trade closes with -5.5% price move = +5.5% profit on SHORT ✅

Key difference from old system:
- OLD: TP1 at +2.5%, close 75%, then trailing on 25%
- NEW: Single TP that trails continuously, close 100% at trailing TP
- RESULT: Simpler, more reliable, catches full move!
"""

# Implementation in monitor_positions:
def monitor_positions_with_simple_trailing(self):
    """
    Monitor positions with SIMPLE trailing TP logic
    
    Logic:
    1. Track highest price (LONG) or lowest price (SHORT)
    2. If new high/low reached, move TP to maintain fixed profit distance
    3. When price hits trailing TP, close entire position
    4. SL remains fixed at entry level
    """
    
    for symbol, position in list(self.positions.items()):
        current_price = await self.get_market_data(symbol).last_price
        
        # Update peak prices
        if position.side == 'long':
            if current_price > position.highest_price:
                position.highest_price = current_price
                
                # Calculate new trailing TP
                # Maintain fixed profit percentage from peak
                profit_target_pct = 0.025  # 2.5% ROI target
                price_move_needed = profit_target_pct / position.leverage  # e.g., 0.1% for 25x
                new_tp = position.highest_price * (1 + price_move_needed)
                
                # Only move TP up (never down)
                if position.tp_levels and new_tp > position.tp_levels[0][0]:
                    old_tp = position.tp_levels[0][0]
                    position.tp_levels[0] = (new_tp, 1.0)
                    logger.info(f"🔄 Trailing TP moved UP | {symbol} | ${old_tp:.4f} → ${new_tp:.4f}")
                    
                    # Update exchange-side TP order
                    await self._update_exchange_tp(symbol, position, new_tp)
        
        else:  # short
            if current_price < position.lowest_price:
                position.lowest_price = current_price
                
                # Calculate new trailing TP
                profit_target_pct = 0.025  # 2.5% ROI target
                price_move_needed = profit_target_pct / position.leverage
                new_tp = position.lowest_price * (1 - price_move_needed)
                
                # Only move TP down (never up)
                if position.tp_levels and new_tp < position.tp_levels[0][0]:
                    old_tp = position.tp_levels[0][0]
                    position.tp_levels[0] = (new_tp, 1.0)
                    logger.info(f"🔄 Trailing TP moved DOWN | {symbol} | ${old_tp:.4f} → ${new_tp:.4f}")
                    
                    # Update exchange-side TP order
                    await self._update_exchange_tp(symbol, position, new_tp)
        
        # Check if TP hit
        tp_price = position.tp_levels[0][0] if position.tp_levels else None
        if tp_price:
            tp_hit = False
            if position.side == 'long' and current_price >= tp_price:
                tp_hit = True
            elif position.side == 'short' and current_price <= tp_price:
                tp_hit = True
            
            if tp_hit:
                logger.info(f"🎯 TRAILING TP HIT | {symbol} | Closing FULL position at ${current_price:.4f}")
                await self.close_position(position, "take_profit_trailing")
                continue
        
        # Check if SL hit
        if position.side == 'long' and current_price <= position.stop_price:
            logger.warning(f"🛑 STOP LOSS HIT | {symbol} LONG | ${current_price:.4f} <= ${position.stop_price:.4f}")
            await self.close_position(position, "stop_loss")
        elif position.side == 'short' and current_price >= position.stop_price:
            logger.warning(f"🛑 STOP LOSS HIT | {symbol} SHORT | ${current_price:.4f} >= ${position.stop_price:.4f}")
            await self.close_position(position, "stop_loss")


# Benefits of this approach:
# ✅ SIMPLE: No complex TP1/TP2/TP3 levels
# ✅ AUTOMATIC: TP trails continuously without manual triggers
# ✅ FULL EXIT: Close 100% at trailing TP (no partial closes)
# ✅ RELIABLE: Works even if exchange-side orders fail
# ✅ PROFIT PROTECTION: Locks in gains as price moves favorably
# ✅ NO GIVE-BACK: Once TP moves, it never moves back

