# SSL Certificate Fix for macOS

## Problem
The bot is experiencing `SSLCertVerificationError` when connecting to Bitget API. This is a common macOS Python issue where SSL certificates are not properly installed.

## Solution

Run this command to install Python certificates:

```bash
/Applications/Python\ */Install\ Certificates.command
```

Or for a specific Python version:

```bash
/Applications/Python\ 3.*/Install\ Certificates.command
```

## Alternative: Temporary Workaround

The code has been updated to use `ssl._create_unverified_context()` to disable SSL verification temporarily. However, this is **NOT RECOMMENDED** for production and should only be used for development.

## Permanent Fix

1. Find your Python installation:
   ```bash
   which python3
   ```

2. Navigate to the Python application directory:
   ```bash
   cd /Applications
   ls -la | grep Python
   ```

3. Run the certificate installer:
   ```bash
   /Applications/Python\ 3.*/Install\ Certificates.command
   ```

4. Restart the bot after installing certificates.

## Verification

After installing certificates, test the connection:

```bash
python3 -c "import ssl; import urllib.request; urllib.request.urlopen('https://api.bitget.com')"
```

If this succeeds without errors, the certificates are properly installed.

