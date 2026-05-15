"""
Circle钱包服务 - arc-agent-escrow用
管理Arc链上的托管钱包
"""

import os
import json
import urllib.request
import hashlib
import time
from typing import Dict, Optional

ARC_BLOCKCHAIN = "ARC-TESTNET"
ARC_USDC_TOKEN_ID = "15dc2b5d-0994-58b0-bf8c-3a0501148ee8"
CIRCLE_API_BASE = "https://api.circle.com/v1/w3s"


class CircleWalletService:
    """Circle钱包服务"""

    def __init__(self):
        self.api_key = os.getenv("CIRCLE_API_KEY", "")
        self.entity_secret = os.getenv("CIRCLE_ENTITY_SECRET", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.entity_secret)

    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        url = f"{CIRCLE_API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req)
            return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            raise Exception(f"Circle API Error: {e}")

    def create_wallet(self, wallet_set_id: str = None) -> Dict:
        """创建Arc钱包"""
        if not self.is_configured:
            addr = "0x" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:40]
            return {"id": f"sim_{int(time.time())}", "address": addr,
                    "blockchain": ARC_BLOCKCHAIN, "state": "LIVE"}

        if not wallet_set_id:
            # 创建wallet set
            resp = self._request("POST", "walletSets", {"name": "Agent Escrow"})
            wallet_set_id = resp["data"]["walletSet"]["id"]

        resp = self._request("POST", "wallets", {
            "walletSetId": wallet_set_id,
            "blockchains": [ARC_BLOCKCHAIN],
            "count": 1, "accountType": "EOA"
        })
        w = resp["data"]["wallets"][0]
        return {"id": w["id"], "address": w["address"],
                "blockchain": w["blockchain"], "state": w["state"]}

    def send_usdc(self, from_wallet_id: str, to_address: str, amount: str) -> Dict:
        """发送USDC"""
        if not self.is_configured:
            tx_hash = "0x" + hashlib.sha256(f"{from_wallet_id}{to_address}{amount}{time.time()}".encode()).hexdigest()[:64]
            return {"state": "COMPLETE", "tx_hash": tx_hash, "amounts": [amount]}

        resp = self._request("POST", "transactions/transfer", {
            "walletId": from_wallet_id,
            "tokenId": ARC_USDC_TOKEN_ID,
            "destinationAddress": to_address,
            "amounts": [str(amount)],
            "feeLevel": "MEDIUM"
        })
        tx = resp["data"]["transaction"]
        return {"state": tx["state"], "tx_hash": tx.get("txHash", ""),
                "amounts": tx.get("amounts", [])}

    def get_balance(self, wallet_id: str) -> Dict:
        """查询余额"""
        if not self.is_configured:
            return {"id": wallet_id, "balances": [{"token": "USDC", "amount": "100.00"}]}

        resp = self._request("GET", f"wallets/{wallet_id}")
        return {"id": resp["data"]["wallet"]["id"],
                "balances": resp["data"]["wallet"].get("balances", [])}

    @staticmethod
    def validate_address(addr: str) -> bool:
        return addr.startswith("0x") and len(addr) == 42
