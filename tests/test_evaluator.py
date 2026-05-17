"""单元测试 - AI Evaluator"""

import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluator import AIEvaluator


@pytest.fixture
def evaluator():
    return AIEvaluator(pass_threshold=0.6)


class TestBasicEvaluation:
    def test_empty_submission(self, evaluator):
        job = {"title": "Test", "description": "Do something", "category": "general"}
        result = evaluator.evaluate(job, "")
        assert result["passed"] is False
        assert result["score"] == 0.0

    def test_short_submission(self, evaluator):
        job = {"title": "Test", "description": "Do something", "category": "general"}
        result = evaluator.evaluate(job, "ok")
        assert result["score"] < 0.5

    def test_good_submission(self, evaluator):
        job = {"title": "Write analysis", "description": "Write a market analysis", "category": "analysis"}
        submission = """
        Market Analysis Report

        The current market shows strong bullish trends across multiple indicators.
        Volume has increased by 45% compared to the previous quarter.

        Key findings:
        - RSI indicates overbought conditions at 72.3
        - MACD shows positive divergence
        - Support level at $42,500

        Conclusion: The market is likely to continue its upward trajectory
        in the short term, with a recommended entry point near the support level.

        Sources: CoinGecko, TradingView, DeFi Pulse
        """
        result = evaluator.evaluate(job, submission)
        assert result["score"] > 0.5
        assert "details" in result


class TestTranslationEval:
    def test_translation_with_chinese(self, evaluator):
        job = {"title": "Translate", "description": "Translate this article", "category": "translation"}
        result = evaluator.evaluate(job, "这是一篇关于区块链技术的文章。它涵盖了去中心化、智能合约和代币经济学等核心概念。翻译质量良好，内容完整。")
        assert result["score"] > 0.3


class TestCodeEval:
    def test_code_submission(self, evaluator):
        job = {"title": "Code Review", "description": "Review this contract", "category": "code"}
        submission = """
        ```python
        def transfer_usdc(from_addr, to_addr, amount):
            # Validate addresses
            assert validate_address(from_addr)
            assert validate_address(to_addr)

            try:
                tx = wallet.send(to=to_addr, amount=amount)
                return tx.hash
            except Exception as e:
                logger.error(f"Transfer failed: {e}")
                raise
        ```
        This function handles USDC transfer with address validation and error handling.
        """
        result = evaluator.evaluate(job, submission)
        assert result["score"] > 0.5


class TestWeights:
    def test_general_weights(self, evaluator):
        w = evaluator._get_weights("general")
        assert "completeness" in w
        assert "relevance" in w

    def test_code_weights(self, evaluator):
        w = evaluator._get_weights("code")
        assert "code_quality" in w
        assert w["code_quality"] == 0.4


class TestNotes:
    def test_notes_generated(self, evaluator):
        job = {"title": "Test", "description": "Test", "category": "general"}
        result = evaluator.evaluate(job, "Some reasonable submission content that is long enough")
        assert result["notes"]
        assert "PASS" in result["notes"] or "FAIL" in result["notes"]


class TestFormatScalar:
    def test_scalar_json_does_not_inflate_format_score(self, evaluator):
        """"42" / "true" parse as JSON but aren't structured — must not earn the JSON bonus."""
        for scalar in ('42', '"hi"', 'true', 'null'):
            assert evaluator._check_format(scalar) <= 0.6, (
                f"scalar {scalar!r} should not get +0.3 JSON bonus"
            )

    def test_object_json_gets_format_bonus(self, evaluator):
        assert evaluator._check_format('{"key": "value"}') >= 0.8
