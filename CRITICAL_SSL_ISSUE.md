# CRITICAL: SSL Certificate Issue Preventing API Connectivity

## Status: **BLOCKING - Bot Cannot Connect to Bitget API**

### Problem
All API requests are failing with `SSLCertVerificationError: certificate verify failed: unable to get local issuer certificate`. This is preventing the bot from:
- Fetching market data (candles)
- Placing orders
- Checking account balance
- Managing positions

### Root Cause
macOS Python installations often have missing or improperly configured SSL certificates. The bot has been configured with an unverified SSL context, but aiohttp is still attempting certificate verification at a lower level.

### Attempted Fixes (All Failed)
1. ✅ Created unverified SSL context (`ssl.CERT_NONE`)
2. ✅ Used persistent connector in `BitgetRestClient.__init__`
3. ✅ Installed `certifi` package
4. ✅ Ran Python certificate installer script
5. ❌ **All fixes failed - aiohttp still shows "ssl:True" in errors**

### Required Action: Install System Certificates

**You MUST run this command to fix the SSL issue:**

```bash
/Applications/Python\ 3.13/Install\ Certificates.command
```

**OR if using a different Python version:**

```bash
find /Applications -name "Install Certificates.command" -exec bash {} \;
```

### After Installing Certificates

1. **Restart the bot:**
   ```bash
   pkill -9 -f "python.*launch_institutional_live"
   python3 launch_institutional_live.py > /tmp/live_bot.log 2>&1 &
   ```

2. **Verify connection:**
   ```bash
   tail -100 /tmp/live_bot.log | grep -E "(✅.*fetched|Account|Balance)" -i
   ```

### Current Bot Status
- **Process:** Running (but cannot connect to API)
- **Data Fetching:** 0% success (53/53 symbols failing)
- **Signals:** 0 (cannot generate without data)
- **Trades:** 0 (cannot place orders)

### Impact
**The bot is completely non-functional until SSL certificates are properly installed.**

The code has been updated to use unverified SSL contexts, but macOS's Python SSL library requires proper certificate installation at the system level.

