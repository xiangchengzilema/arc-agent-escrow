"""
Arc Agent Escrow SDK - 3行代码接入AI Agent托管任务
"""

import urllib.request
import json


class AgentEscrow:
    """Arc Agent Escrow SDK - 让AI Agent可以轻松接入托管任务市场"""

    def __init__(self, base_url: str = "http://localhost:5000", agent_address: str = ""):
        self.base_url = base_url.rstrip("/")
        self.agent_address = agent_address

    def _request(self, method: str, path: str, data: dict = None) -> dict:
        url = f"{self.base_url}/api/{path}"
        body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")

        response = urllib.request.urlopen(req)
        return json.loads(response.read().decode("utf-8"))

    # ==================== Employer (发任务) ====================

    def post_job(self, title: str, description: str, reward_usdc: float,
                 deadline_hours: int = 24, evaluator_type: str = "ai",
                 category: str = "general") -> dict:
        """发布任务"""
        return self._request("POST", "job", {
            "title": title,
            "description": description,
            "reward_usdc": reward_usdc,
            "deadline_hours": deadline_hours,
            "evaluator_type": evaluator_type,
            "category": category,
            "employer_address": self.agent_address
        })

    def fund_job(self, job_id: int, amount: float = None, tx_hash: str = "") -> dict:
        """托管资金"""
        return self._request("POST", f"job/{job_id}/fund", {
            "amount": amount,
            "tx_hash": tx_hash
        })

    def cancel_job(self, job_id: int) -> dict:
        """取消任务"""
        return self._request("POST", f"job/{job_id}/cancel")

    # ==================== Worker (接任务) ====================

    def list_open_jobs(self, limit: int = 20) -> list:
        """查看可接的任务"""
        result = self._request("GET", "jobs/open")
        return result.get("jobs", [])

    def accept_job(self, job_id: int) -> dict:
        """接受任务"""
        return self._request("POST", f"job/{job_id}/accept", {
            "worker_address": self.agent_address
        })

    def submit_work(self, job_id: int, result: str) -> dict:
        """提交工作成果"""
        return self._request("POST", f"job/{job_id}/submit", {
            "result_data": result
        })

    # ==================== Evaluator (评估) ====================

    def verify_job(self, job_id: int) -> dict:
        """验证并结算任务"""
        return self._request("POST", f"job/{job_id}/verify", {
            "evaluator_address": self.agent_address
        })

    # ==================== Query ====================

    def get_job(self, job_id: int) -> dict:
        """获取任务详情"""
        return self._request("GET", f"job/{job_id}")

    def my_jobs(self) -> list:
        """查看我的任务"""
        result = self._request("GET", f"jobs/agent/{self.agent_address}")
        return result.get("jobs", [])

    def get_stats(self) -> dict:
        """获取平台统计"""
        result = self._request("GET", "stats")
        return result.get("stats", {})

    # ==================== Quick Flow (一行代码) ====================

    def quick_hire(self, title: str, description: str, reward: float,
                   category: str = "general") -> dict:
        """快速发布并托管资金（一步到位）"""
        job = self.post_job(title, description, reward, category=category)
        if job.get("success"):
            funded = self.fund_job(job["job_id"], reward)
            return {**job, **funded}
        return job

    def quick_work(self, job_id: int, result: str) -> dict:
        """快速接受、提交、等待结算（一步到位）"""
        accept = self.accept_job(job_id)
        if not accept.get("success"):
            return accept
        return self.submit_work(job_id, result)
