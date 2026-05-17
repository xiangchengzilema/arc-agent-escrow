"""
AI Evaluator - 自动评估Agent提交的工作成果
支持多种评估策略：关键词匹配、长度检查、格式验证
"""

import re
import json
from typing import Dict, Optional


class AIEvaluator:
    """AI工作评估器"""

    def __init__(self, pass_threshold: float = 0.6):
        self.pass_threshold = pass_threshold

    def evaluate(self, job: Dict, submission: str) -> Dict:
        """
        评估工作提交

        Args:
            job: 任务信息（包含title, description, category等）
            submission: Worker提交的结果

        Returns:
            {"score": 0.85, "passed": True, "notes": "...", "details": {...}}
        """
        if not submission or not submission.strip():
            return {
                "score": 0.0,
                "passed": False,
                "notes": "Empty submission",
                "details": {"reason": "no_content"}
            }

        scores = {}
        category = job.get("category", "general")
        description = job.get("description", "")
        title = job.get("title", "")

        # 1. 基础质量检查（所有类别）
        scores["completeness"] = self._check_completeness(submission)
        scores["relevance"] = self._check_relevance(title, description, submission)
        scores["format"] = self._check_format(submission)

        # 2. 类别特定检查
        if category in ("translation", "translate"):
            scores["translation_quality"] = self._check_translation(description, submission)
        elif category in ("code", "programming", "review"):
            scores["code_quality"] = self._check_code(submission)
        elif category in ("analysis", "research", "data"):
            scores["depth"] = self._check_analysis(submission)
        elif category in ("writing", "content", "article"):
            scores["writing_quality"] = self._check_writing(submission)
        else:
            scores["general_quality"] = self._check_general(submission)

        # 计算加权平均分
        weights = self._get_weights(category)
        final_score = sum(scores[k] * w for k, w in weights.items() if k in scores)
        total_weight = sum(w for k, w in weights.items() if k in scores)
        if total_weight > 0:
            final_score = final_score / total_weight

        passed = final_score >= self.pass_threshold

        notes = self._generate_notes(scores, passed, category, final_score)

        return {
            "score": round(final_score, 3),
            "passed": passed,
            "notes": notes,
            "details": scores
        }

    def _check_completeness(self, submission: str) -> float:
        """检查完整性"""
        length = len(submission.strip())
        if length < 10:
            return 0.1
        elif length < 50:
            return 0.3
        elif length < 200:
            return 0.6
        elif length < 500:
            return 0.8
        else:
            return 1.0

    def _check_relevance(self, title: str, description: str, submission: str) -> float:
        """检查相关性（关键词匹配）"""
        job_text = f"{title} {description}".lower()
        sub_lower = submission.lower()

        job_words = set(re.findall(r'\b\w{3,}\b', job_text))
        sub_words = set(re.findall(r'\b\w{3,}\b', sub_lower))

        if not job_words:
            return 0.5

        overlap = len(job_words & sub_words)
        ratio = overlap / len(job_words) if job_words else 0

        if ratio >= 0.5:
            return 1.0
        elif ratio >= 0.3:
            return 0.7
        elif ratio >= 0.1:
            return 0.4
        else:
            return 0.2

    def _check_format(self, submission: str) -> float:
        """检查格式"""
        score = 0.5

        # 有结构化内容加分
        if any(c in submission for c in ['\n', '-', '*', '#', '1.', '•']):
            score += 0.2

        # 有JSON加分（仅当解析结果是 dict 或 list — 单纯的 "42"/"true" 不算结构化）
        try:
            parsed = json.loads(submission)
            if isinstance(parsed, (dict, list)):
                score += 0.3
        except (json.JSONDecodeError, ValueError):
            pass

        # 有URL加分
        if re.search(r'https?://\S+', submission):
            score += 0.1

        return min(score, 1.0)

    def _check_translation(self, original: str, translation: str) -> float:
        """检查翻译质量"""
        score = 0.5

        # 检测中文字符（如果是英译中）
        chinese_chars = len(re.findall(r'[一-鿿]', translation))
        if chinese_chars > 10:
            score += 0.3

        # 检查长度比例（翻译通常不会比原文短太多）
        if len(translation) > len(original) * 0.3:
            score += 0.2

        return min(score, 1.0)

    def _check_code(self, submission: str) -> float:
        """检查代码质量"""
        score = 0.3

        # 有代码块标记
        if '```' in submission or 'def ' in submission or 'function ' in submission:
            score += 0.3

        # 有注释
        if '#' in submission or '//' in submission:
            score += 0.1

        # 有import/require
        if 'import ' in submission or 'require(' in submission or 'from ' in submission:
            score += 0.1

        # 有错误处理
        if 'try' in submission or 'catch' in submission or 'error' in submission.lower():
            score += 0.2

        return min(score, 1.0)

    def _check_analysis(self, submission: str) -> float:
        """检查分析质量"""
        score = 0.4

        # 有数字/统计
        if re.search(r'\d+\.?\d*%?', submission):
            score += 0.2

        # 有比较/结论
        conclusion_words = ['therefore', 'conclusion', 'result', 'recommendation',
                           'summary', 'analysis', 'finding', 'suggest']
        if any(w in submission.lower() for w in conclusion_words):
            score += 0.2

        # 有多个段落
        if submission.count('\n\n') >= 2:
            score += 0.2

        return min(score, 1.0)

    def _check_writing(self, submission: str) -> float:
        """检查写作质量"""
        score = 0.4

        # 段落数
        paragraphs = [p for p in submission.split('\n\n') if p.strip()]
        if len(paragraphs) >= 3:
            score += 0.2

        # 字数
        words = len(submission.split())
        if words >= 100:
            score += 0.2

        # 有标题
        if submission.startswith('#') or '\n#' in submission:
            score += 0.1

        # 语法检查（简单的标点检查）
        if submission.count('.') >= 3 or submission.count('。') >= 3:
            score += 0.1

        return min(score, 1.0)

    def _check_general(self, submission: str) -> float:
        """通用质量检查"""
        score = 0.5
        if len(submission) > 100:
            score += 0.2
        if '\n' in submission:
            score += 0.1
        if any(c in submission for c in '-*#•'):
            score += 0.1
        if re.search(r'https?://', submission):
            score += 0.1
        return min(score, 1.0)

    def _get_weights(self, category: str) -> Dict[str, float]:
        """获取各类别权重"""
        base = {"completeness": 0.2, "relevance": 0.3, "format": 0.1}

        category_weight = {
            "translation": {"translation_quality": 0.4},
            "code": {"code_quality": 0.4},
            "analysis": {"depth": 0.4},
            "writing": {"writing_quality": 0.4},
        }

        specific = category_weight.get(category, {"general_quality": 0.4})
        return {**base, **specific}

    def _generate_notes(self, scores: Dict, passed: bool, category: str,
                        final_score: float) -> str:
        """生成评估备注"""
        status = "PASS" if passed else "FAIL"
        best = max(scores, key=scores.get)
        worst = min(scores, key=scores.get)

        return (f"[{status}] Score: {final_score:.2f}. "
                f"Strongest: {best} ({scores[best]:.2f}). "
                f"Needs improvement: {worst} ({scores[worst]:.2f}). "
                f"Category: {category}.")
