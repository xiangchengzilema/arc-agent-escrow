"""单元测试 - Escrow SDK"""

import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from escrow_sdk import AgentEscrow


class TestSDKInit:
    def test_init(self):
        sdk = AgentEscrow(base_url="http://localhost:5001", agent_address="0xTest")
        assert sdk.agent_address == "0xTest"
        assert sdk.base_url == "http://localhost:5001"

    def test_init_default(self):
        sdk = AgentEscrow()
        assert sdk.base_url == "http://localhost:5000"


class TestSDKMethods:
    """Test SDK method signatures (not actual API calls)"""

    def test_has_employer_methods(self):
        sdk = AgentEscrow()
        assert hasattr(sdk, "post_job")
        assert hasattr(sdk, "fund_job")
        assert hasattr(sdk, "cancel_job")
        assert callable(sdk.post_job)

    def test_has_worker_methods(self):
        sdk = AgentEscrow()
        assert hasattr(sdk, "list_open_jobs")
        assert hasattr(sdk, "accept_job")
        assert hasattr(sdk, "submit_work")
        assert callable(sdk.accept_job)

    def test_has_evaluator_methods(self):
        sdk = AgentEscrow()
        assert hasattr(sdk, "verify_job")
        assert callable(sdk.verify_job)

    def test_has_query_methods(self):
        sdk = AgentEscrow()
        assert hasattr(sdk, "get_job")
        assert hasattr(sdk, "my_jobs")
        assert hasattr(sdk, "get_stats")

    def test_has_quick_methods(self):
        sdk = AgentEscrow()
        assert hasattr(sdk, "quick_hire")
        assert hasattr(sdk, "quick_work")
