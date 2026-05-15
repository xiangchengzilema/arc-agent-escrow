"""单元测试 - Escrow Engine"""

import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from escrow_engine import EscrowEngine, STATE_OPEN, STATE_FUNDED, STATE_ASSIGNED, STATE_SUBMITTED, STATE_VERIFIED, STATE_SETTLED, STATE_REJECTED, STATE_CANCELLED

EMPLOYER = "0xAAAA000000000000000000000000000000000000"
WORKER = "0xBBBB000000000000000000000000000000000000"


@pytest.fixture
def engine(tmp_path):
    return EscrowEngine(str(tmp_path / "test_escrow.db"))


class TestCreateJob:
    def test_create_job(self, engine):
        result = engine.create_job(EMPLOYER, "Test Job", "Description", 0.10)
        assert result["status"] == STATE_OPEN
        assert result["job_id"] > 0

    def test_get_job(self, engine):
        created = engine.create_job(EMPLOYER, "Get Test", "Desc", 0.05)
        job = engine.get_job(created["job_id"])
        assert job is not None
        assert job["title"] == "Get Test"
        assert job["reward_usdc"] == 0.05
        assert job["employer_address"] == EMPLOYER

    def test_get_job_by_code(self, engine):
        created = engine.create_job(EMPLOYER, "Code Test", "Desc", 0.05)
        job = engine.get_job_by_code(created["job_code"])
        assert job is not None
        assert job["job_code"] == created["job_code"]


class TestFundJob:
    def test_fund_job(self, engine):
        created = engine.create_job(EMPLOYER, "Fund Test", "Desc", 0.10)
        result = engine.fund_job(created["job_id"], 0.10)
        assert result["success"] is True
        assert result["status"] == STATE_FUNDED

    def test_fund_wrong_state(self, engine):
        created = engine.create_job(EMPLOYER, "Test", "Desc", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        result = engine.fund_job(created["job_id"], 0.10)
        assert result["success"] is False

    def test_fund_nonexistent(self, engine):
        result = engine.fund_job(99999, 0.10)
        assert result["success"] is False


class TestAssignJob:
    def test_assign_job(self, engine):
        created = engine.create_job(EMPLOYER, "Assign Test", "Desc", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        result = engine.assign_job(created["job_id"], WORKER)
        assert result["success"] is True
        assert result["status"] == STATE_ASSIGNED

    def test_assign_unfunded(self, engine):
        created = engine.create_job(EMPLOYER, "Test", "Desc", 0.10)
        result = engine.assign_job(created["job_id"], WORKER)
        assert result["success"] is False


class TestSubmitWork:
    def test_submit_work(self, engine):
        created = engine.create_job(EMPLOYER, "Submit Test", "Desc", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        engine.assign_job(created["job_id"], WORKER)
        result = engine.submit_work(created["job_id"], "Translation result here")
        assert result["success"] is True
        assert result["status"] == STATE_SUBMITTED


class TestVerifyAndSettle:
    def test_verify_pass(self, engine):
        created = engine.create_job(EMPLOYER, "Verify Pass", "Translate article", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        engine.assign_job(created["job_id"], WORKER)
        engine.submit_work(created["job_id"], "This is a good translation result with enough content to pass the completeness check.")
        result = engine.verify_and_settle(created["job_id"], 0.85, "Good work")
        assert result["success"] is True
        assert result["status"] == STATE_SETTLED

    def test_verify_fail(self, engine):
        created = engine.create_job(EMPLOYER, "Verify Fail", "Do something", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        engine.assign_job(created["job_id"], WORKER)
        engine.submit_work(created["job_id"], "short")
        result = engine.verify_and_settle(created["job_id"], 0.2, "Too short")
        assert result["status"] == STATE_REJECTED


class TestCancelJob:
    def test_cancel_open(self, engine):
        created = engine.create_job(EMPLOYER, "Cancel Test", "Desc", 0.10)
        result = engine.cancel_job(created["job_id"])
        assert result["success"] is True
        assert result["status"] == STATE_CANCELLED

    def test_cancel_funded_refund(self, engine):
        created = engine.create_job(EMPLOYER, "Refund Test", "Desc", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        result = engine.cancel_job(created["job_id"])
        assert result["success"] is True
        assert result["status"] == STATE_CANCELLED


class TestListJobs:
    def test_list_all(self, engine):
        for i in range(5):
            engine.create_job(EMPLOYER, f"Job {i}", "Desc", 0.01 * (i + 1))
        jobs = engine.list_jobs()
        assert len(jobs) == 5

    def test_list_by_status(self, engine):
        engine.create_job(EMPLOYER, "Open", "Desc", 0.01)
        created = engine.create_job(EMPLOYER, "Funded", "Desc", 0.02)
        engine.fund_job(created["job_id"], 0.02)
        open_jobs = engine.list_jobs(status="open")
        assert len(open_jobs) == 1

    def test_agent_jobs(self, engine):
        engine.create_job(EMPLOYER, "Emp Job", "Desc", 0.01)
        engine.create_job(WORKER, "Worker Job", "Desc", 0.01)
        emp_jobs = engine.get_agent_jobs(EMPLOYER)
        assert len(emp_jobs) == 1


class TestStats:
    def test_empty_stats(self, engine):
        stats = engine.get_stats()
        assert stats["total_jobs"] == 0
        assert stats["total_volume_usdc"] == 0

    def test_stats_after_jobs(self, engine):
        created = engine.create_job(EMPLOYER, "Stats", "Desc", 0.10)
        engine.fund_job(created["job_id"], 0.10)
        engine.assign_job(created["job_id"], WORKER)
        engine.submit_work(created["job_id"], "Good result with enough content for evaluation")
        engine.verify_and_settle(created["job_id"], 0.9, "Nice")
        stats = engine.get_stats()
        assert stats["total_jobs"] == 1
        assert stats["completed_jobs"] == 1
        assert stats["total_volume_usdc"] == 0.10
