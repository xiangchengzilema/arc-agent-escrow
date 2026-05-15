"""
Escrow Engine - 核心托管逻辑
实现ERC-8183标准的Job生命周期状态机
"""

import sqlite3
import hashlib
import time
from typing import Dict, Optional, List
from datetime import datetime


# ERC-8183 Job States
STATE_OPEN = "open"
STATE_FUNDED = "funded"
STATE_ASSIGNED = "assigned"
STATE_SUBMITTED = "submitted"
STATE_VERIFIED = "verified"
STATE_SETTLED = "settled"
STATE_REJECTED = "rejected"
STATE_DISPUTED = "disputed"
STATE_RESOLVED = "resolved"
STATE_CANCELLED = "cancelled"
STATE_EXPIRED = "expired"

# Valid state transitions (ERC-8183)
TRANSITIONS = {
    STATE_OPEN: [STATE_FUNDED, STATE_CANCELLED, STATE_EXPIRED],
    STATE_FUNDED: [STATE_ASSIGNED, STATE_CANCELLED, STATE_EXPIRED],
    STATE_ASSIGNED: [STATE_SUBMITTED, STATE_CANCELLED, STATE_DISPUTED, STATE_EXPIRED],
    STATE_SUBMITTED: [STATE_VERIFIED, STATE_REJECTED, STATE_DISPUTED],
    STATE_VERIFIED: [STATE_SETTLED],
    STATE_REJECTED: [STATE_DISPUTED, STATE_SETTLED],  # settled = refund employer
    STATE_DISPUTED: [STATE_RESOLVED],
    STATE_RESOLVED: [STATE_SETTLED],
}

TERMINAL_STATES = {STATE_SETTLED, STATE_CANCELLED, STATE_EXPIRED}


class EscrowEngine:
    """ERC-8183托管引擎"""

    def __init__(self, db_path: str = "escrow.db"):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                employer_address TEXT NOT NULL,
                worker_address TEXT,
                evaluator_address TEXT,
                reward_usdc REAL NOT NULL,
                escrow_amount REAL DEFAULT 0,
                evaluator_type TEXT DEFAULT 'ai',
                status TEXT DEFAULT 'open',
                deadline TIMESTAMP,
                category TEXT DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                funded_at TIMESTAMP,
                assigned_at TIMESTAMP,
                submitted_at TIMESTAMP,
                verified_at TIMESTAMP,
                settled_at TIMESTAMP,
                result_data TEXT,
                evaluation_score REAL,
                evaluation_notes TEXT,
                tx_hash TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS escrow_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                amount_usdc REAL NOT NULL,
                from_address TEXT,
                to_address TEXT,
                tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS agent_reputation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                jobs_completed INTEGER DEFAULT 0,
                jobs_posted INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_spent REAL DEFAULT 0,
                avg_score REAL DEFAULT 0,
                disputes INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
        ''')

        c.execute('CREATE INDEX IF NOT EXISTS idx_job_status ON jobs(status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_job_employer ON jobs(employer_address)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_job_worker ON jobs(worker_address)')

        conn.commit()
        conn.close()

    def create_job(self, employer_address: str, title: str, description: str,
                   reward_usdc: float, deadline_hours: int = 24,
                   evaluator_type: str = "ai", category: str = "general") -> Dict:
        """创建新任务"""
        job_code = "job_" + hashlib.sha256(
            f"{employer_address}{title}{time.time()}".encode()
        ).hexdigest()[:12]

        deadline = None
        if deadline_hours > 0:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT datetime('now', '+{} hours')".format(deadline_hours))
            deadline = c.fetchone()[0]
            conn.close()

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO jobs (job_code, title, description, employer_address,
                            reward_usdc, evaluator_type, deadline, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (job_code, title, description, employer_address,
              reward_usdc, evaluator_type, deadline, category))

        job_id = c.lastrowid
        conn.commit()
        conn.close()

        return {"job_id": job_id, "job_code": job_code, "status": STATE_OPEN}

    def fund_job(self, job_id: int, amount: float, tx_hash: str = "") -> Dict:
        """托管资金"""
        job = self._get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        if job["status"] != STATE_OPEN:
            return {"success": False, "error": f"Cannot fund job in {job['status']} state"}

        self._transition(job_id, STATE_FUNDED)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE jobs SET escrow_amount = ?, funded_at = CURRENT_TIMESTAMP WHERE id = ?",
                  (amount, job_id))
        c.execute('''
            INSERT INTO escrow_ledger (job_id, action, amount_usdc, from_address, tx_hash)
            VALUES (?, 'fund', ?, ?, ?)
        ''', (job_id, amount, job["employer_address"], tx_hash))
        conn.commit()
        conn.close()

        return {"success": True, "job_id": job_id, "status": STATE_FUNDED, "escrowed": amount}

    def assign_job(self, job_id: int, worker_address: str) -> Dict:
        """分配任务给worker"""
        job = self._get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        if job["status"] != STATE_FUNDED:
            return {"success": False, "error": f"Cannot assign job in {job['status']} state"}

        self._transition(job_id, STATE_ASSIGNED)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE jobs SET worker_address = ?, assigned_at = CURRENT_TIMESTAMP WHERE id = ?",
                  (worker_address, job_id))
        conn.commit()
        conn.close()

        self._update_reputation(job["employer_address"], "job_posted")
        self._update_reputation(worker_address, None)

        return {"success": True, "job_id": job_id, "status": STATE_ASSIGNED}

    def submit_work(self, job_id: int, result_data: str) -> Dict:
        """Worker提交工作成果"""
        job = self._get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        if job["status"] != STATE_ASSIGNED:
            return {"success": False, "error": f"Cannot submit to job in {job['status']} state"}

        self._transition(job_id, STATE_SUBMITTED)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE jobs SET result_data = ?, submitted_at = CURRENT_TIMESTAMP WHERE id = ?",
                  (result_data, job_id))
        conn.commit()
        conn.close()

        return {"success": True, "job_id": job_id, "status": STATE_SUBMITTED}

    def verify_and_settle(self, job_id: int, score: float, notes: str = "",
                          evaluator_address: str = "") -> Dict:
        """验证并结算"""
        job = self._get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        if job["status"] not in (STATE_SUBMITTED, STATE_DISPUTED, STATE_RESOLVED):
            return {"success": False, "error": f"Cannot verify job in {job['status']} state"}

        if score >= 0.6:  # 60% pass threshold
            self._transition(job_id, STATE_VERIFIED)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''
                UPDATE jobs SET evaluation_score = ?, evaluation_notes = ?,
                               evaluator_address = ?, verified_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (score, notes, evaluator_address, job_id))
            conn.commit()
            conn.close()

            return self._settle(job_id, pay_worker=True)
        else:
            self._transition(job_id, STATE_REJECTED)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''
                UPDATE jobs SET evaluation_score = ?, evaluation_notes = ?,
                               evaluator_address = ?, verified_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (score, notes, evaluator_address, job_id))
            conn.commit()
            conn.close()

            return {"success": True, "job_id": job_id, "status": STATE_REJECTED, "score": score}

    def _settle(self, job_id: int, pay_worker: bool = True) -> Dict:
        """结算托管资金"""
        job = self._get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}

        self._transition(job_id, STATE_SETTLED)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        recipient = job["worker_address"] if pay_worker else job["employer_address"]
        action = "payout" if pay_worker else "refund"

        c.execute("UPDATE jobs SET settled_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        c.execute('''
            INSERT INTO escrow_ledger (job_id, action, amount_usdc, to_address)
            VALUES (?, ?, ?, ?)
        ''', (job_id, action, job["escrow_amount"], recipient))
        conn.commit()
        conn.close()

        if pay_worker:
            self._update_reputation(job["worker_address"], "job_completed", job["escrow_amount"])

        return {
            "success": True,
            "job_id": job_id,
            "status": STATE_SETTLED,
            "amount": job["escrow_amount"],
            "recipient": recipient
        }

    def cancel_job(self, job_id: int) -> Dict:
        """取消任务并退款"""
        job = self._get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
        if job["status"] in TERMINAL_STATES:
            return {"success": False, "error": "Cannot cancel job in terminal state"}

        if job["escrow_amount"] > 0:
            self._transition(job_id, STATE_CANCELLED)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''
                INSERT INTO escrow_ledger (job_id, action, amount_usdc, to_address)
                VALUES (?, 'refund', ?, ?)
            ''', (job_id, job["escrow_amount"], job["employer_address"]))
            conn.commit()
            conn.close()
        else:
            self._transition(job_id, STATE_CANCELLED)

        return {"success": True, "job_id": job_id, "status": STATE_CANCELLED}

    def _transition(self, job_id: int, new_state: str):
        """状态转换"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_state, job_id))
        conn.commit()
        conn.close()

    def _get_job(self, job_id: int) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        cols = ["id", "job_code", "title", "description", "employer_address",
                "worker_address", "evaluator_address", "reward_usdc", "escrow_amount",
                "evaluator_type", "status", "deadline", "category", "created_at",
                "funded_at", "assigned_at", "submitted_at", "verified_at", "settled_at",
                "result_data", "evaluation_score", "evaluation_notes", "tx_hash"]
        return dict(zip(cols, row))

    def get_job(self, job_id: int) -> Optional[Dict]:
        return self._get_job(job_id)

    def get_job_by_code(self, job_code: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM jobs WHERE job_code = ?", (job_code,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        cols = ["id", "job_code", "title", "description", "employer_address",
                "worker_address", "evaluator_address", "reward_usdc", "escrow_amount",
                "evaluator_type", "status", "deadline", "category", "created_at",
                "funded_at", "assigned_at", "submitted_at", "verified_at", "settled_at",
                "result_data", "evaluation_score", "evaluation_notes", "tx_hash"]
        return dict(zip(cols, row))

    def list_jobs(self, status: str = None, limit: int = 20) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if status:
            c.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                      (status, limit))
        else:
            c.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        cols = ["id", "job_code", "title", "description", "employer_address",
                "worker_address", "evaluator_address", "reward_usdc", "escrow_amount",
                "evaluator_type", "status", "deadline", "category", "created_at",
                "funded_at", "assigned_at", "submitted_at", "verified_at", "settled_at",
                "result_data", "evaluation_score", "evaluation_notes", "tx_hash"]
        return [dict(zip(cols, r)) for r in rows]

    def get_agent_jobs(self, address: str) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            SELECT * FROM jobs
            WHERE employer_address = ? OR worker_address = ?
            ORDER BY created_at DESC LIMIT 50
        ''', (address, address))
        rows = c.fetchall()
        conn.close()
        cols = ["id", "job_code", "title", "description", "employer_address",
                "worker_address", "evaluator_address", "reward_usdc", "escrow_amount",
                "evaluator_type", "status", "deadline", "category", "created_at",
                "funded_at", "assigned_at", "submitted_at", "verified_at", "settled_at",
                "result_data", "evaluation_score", "evaluation_notes", "tx_hash"]
        return [dict(zip(cols, r)) for r in rows]

    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM jobs")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'open' OR status = 'funded'")
        open_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'settled'")
        settled = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(escrow_amount), 0) FROM jobs WHERE status = 'settled'")
        total_volume = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(escrow_amount), 0) FROM jobs WHERE status NOT IN ('settled','cancelled','expired')")
        locked = c.fetchone()[0]
        conn.close()
        return {
            "total_jobs": total,
            "open_jobs": open_count,
            "completed_jobs": settled,
            "total_volume_usdc": round(total_volume, 6),
            "locked_usdc": round(locked, 6)
        }

    def _update_reputation(self, address: str, action: str, amount: float = 0):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM agent_reputation WHERE address = ?", (address,))
        exists = c.fetchone()
        if not exists:
            c.execute("INSERT INTO agent_reputation (address) VALUES (?)", (address,))

        if action == "job_posted":
            c.execute("UPDATE agent_reputation SET jobs_posted = jobs_posted + 1, total_spent = total_spent + ?, updated_at = CURRENT_TIMESTAMP WHERE address = ?",
                      (amount, address))
        elif action == "job_completed":
            c.execute("UPDATE agent_reputation SET jobs_completed = jobs_completed + 1, total_earned = total_earned + ?, updated_at = CURRENT_TIMESTAMP WHERE address = ?",
                      (amount, address))

        conn.commit()
        conn.close()
