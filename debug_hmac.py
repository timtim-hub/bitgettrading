#!/usr/bin/env python3
"""Debug HMAC signature generation for Bitget API."""

import base64
import hmac
import time
from hashlib import sha256

import aiohttp
import asyncio


def test_signature_method():
    """Test different signature generation methods."""
    api_key = "bg_e377adcce19a1c440ebb07ff0f557748"
    secret_key = "af212f98f6f11eb31a2ccbcafdffdccf06b4b95c3c969d1e286b1383765b6a9d"
    passphrase = "meinbitget"
    
    timestamp = str(int(time.time() * 1000))
    method = "GET"
    request_path = "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
    body = ""
    
    print("=" * 70)
    print("BITGET API SIGNATURE DEBUG")
    print("=" * 70)
    print(f"Timestamp: {timestamp}")
    print(f"Method: {method}")
    print(f"Request Path: {request_path}")
    print(f"Body: '{body}'")
    print("=" * 70)
    
    # Method 1: Current implementation
    print("\nMethod 1: Current Implementation")
    print("-" * 70)
    prehash1 = timestamp + method + request_path + body
    print(f"Prehash: {prehash1}")
    
    signature1 = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            prehash1.encode("utf-8"),
            sha256,
        ).digest()
    ).decode()
    
    signed_passphrase1 = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            passphrase.encode("utf-8"),
            sha256,
        ).digest()
    ).decode()
    
    print(f"Signature: {signature1}")
    print(f"Signed Passphrase: {signed_passphrase1}")
    
    # Method 2: Passphrase as plain text (no signing)
    print("\n\nMethod 2: Plain Passphrase (no signing)")
    print("-" * 70)
    print(f"Signature: {signature1} (same)")
    print(f"Passphrase: {passphrase} (plain text)")
    
    return {
        "method1": (signature1, signed_passphrase1),
        "method2": (signature1, passphrase),
        "timestamp": timestamp,
    }


async def test_both_methods():
    """Test API with both signature methods."""
    api_key = "bg_e377adcce19a1c440ebb07ff0f557748"
    secret_key = "af212f98f6f11eb31a2ccbcafdffdccf06b4b95c3c969d1e286b1383765b6a9d"
    
    sigs = test_signature_method()
    
    base_url = "https://api.bitget.com"
    endpoint = "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
    
    # Test Method 1: Signed passphrase
    print("\n\n" + "=" * 70)
    print("TESTING METHOD 1: Signed Passphrase")
    print("=" * 70)
    
    headers1 = {
        "Content-Type": "application/json",
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": sigs["method1"][0],
        "ACCESS-TIMESTAMP": sigs["timestamp"],
        "ACCESS-PASSPHRASE": sigs["method1"][1],
    }
    
    print("Headers:")
    for k, v in headers1.items():
        if k == "ACCESS-SIGN" or k == "ACCESS-PASSPHRASE":
            print(f"  {k}: {v[:30]}...")
        else:
            print(f"  {k}: {v}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(base_url + endpoint, headers=headers1) as response:
            text = await response.text()
            print(f"\nStatus: {response.status}")
            print(f"Response: {text[:200]}")
            
            if response.status == 200:
                print("\n✅ METHOD 1 WORKS!")
                return True
    
    # Test Method 2: Plain passphrase
    print("\n\n" + "=" * 70)
    print("TESTING METHOD 2: Plain Passphrase")
    print("=" * 70)
    
    headers2 = {
        "Content-Type": "application/json",
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": sigs["method2"][0],
        "ACCESS-TIMESTAMP": sigs["timestamp"],
        "ACCESS-PASSPHRASE": sigs["method2"][1],
    }
    
    print("Headers:")
    for k, v in headers2.items():
        if k == "ACCESS-SIGN":
            print(f"  {k}: {v[:30]}...")
        else:
            print(f"  {k}: {v}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(base_url + endpoint, headers=headers2) as response:
            text = await response.text()
            print(f"\nStatus: {response.status}")
            print(f"Response: {text[:200]}")
            
            if response.status == 200:
                print("\n✅ METHOD 2 WORKS!")
                return True
    
    print("\n\n❌ BOTH METHODS FAILED")
    print("Please check:")
    print("1. API key is active")
    print("2. API has Futures Trading permission")
    print("3. IP whitelist is disabled or includes your IP")
    print("4. Passphrase is exactly: meinbitget")
    return False


if __name__ == "__main__":
    asyncio.run(test_both_methods())

