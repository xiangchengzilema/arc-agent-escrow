"""Arc Agent Escrow - Flask Application"""

from flask import Flask, request, jsonify, render_template
from escrow_engine import EscrowEngine
from evaluator import AIEvaluator
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
_threshold = float(os.getenv("EVAL_PASS_THRESHOLD", "0.6"))
engine = EscrowEngine(os.getenv("DATABASE_PATH", "escrow.db"), pass_threshold=_threshold)
evaluator = AIEvaluator(pass_threshold=_threshold)


# ==================== Pages ====================

@app.route("/")
def index():
    stats = engine.get_stats()
    jobs = engine.list_jobs(limit=10)
    return render_template("index.html", stats=stats, jobs=jobs)


@app.route("/job/<int:job_id>")
def job_detail(job_id):
    job = engine.get_job(job_id)
    if not job:
        return "Job not found", 404
    return render_template("job.html", job=job)


# ==================== Job API ====================

@app.route("/api/job", methods=["POST"])
def api_create_job():
    """Create a new escrow job"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data"}), 400

    required = ["title", "employer_address", "reward_usdc"]
    for field in required:
        if not data.get(field):
            return jsonify({"success": False, "error": f"{field} required"}), 400

    try:
        result = engine.create_job(
            employer_address=data["employer_address"],
            title=data["title"],
            description=data.get("description", ""),
            reward_usdc=float(data["reward_usdc"]),
            deadline_hours=int(data.get("deadline_hours", 24)),
            evaluator_type=data.get("evaluator_type", "ai"),
            category=data.get("category", "general")
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/job/<int:job_id>")
def api_get_job(job_id):
    job = engine.get_job(job_id)
    if job:
        return jsonify({"success": True, "job": job})
    return jsonify({"success": False, "error": "Job not found"}), 404


@app.route("/api/job/<int:job_id>/fund", methods=["POST"])
def api_fund_job(job_id):
    data = request.get_json()
    amount = data.get("amount") if data else None
    job = engine.get_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Job not found"}), 404
    amount = amount or job["reward_usdc"]
    result = engine.fund_job(job_id, float(amount), data.get("tx_hash", ""))
    return jsonify(result)


@app.route("/api/job/<int:job_id>/accept", methods=["POST"])
def api_accept_job(job_id):
    data = request.get_json()
    if not data or not data.get("worker_address"):
        return jsonify({"success": False, "error": "worker_address required"}), 400
    result = engine.assign_job(job_id, data["worker_address"])
    return jsonify(result)


@app.route("/api/job/<int:job_id>/submit", methods=["POST"])
def api_submit_work(job_id):
    data = request.get_json()
    if not data or not data.get("result_data"):
        return jsonify({"success": False, "error": "result_data required"}), 400
    result = engine.submit_work(job_id, data["result_data"])
    return jsonify(result)


@app.route("/api/job/<int:job_id>/verify", methods=["POST"])
def api_verify_job(job_id):
    """Verify job with AI evaluator and settle"""
    job = engine.get_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Job not found"}), 404

    if job["status"] != "submitted":
        return jsonify({"success": False, "error": f"Job is {job['status']}, expected submitted"}), 400

    # Run AI evaluation
    evaluation = evaluator.evaluate(job, job.get("result_data", ""))

    data = request.get_json() or {}
    evaluator_addr = data.get("evaluator_address", "ai_evaluator_v1")

    result = engine.verify_and_settle(
        job_id,
        score=evaluation["score"],
        notes=evaluation["notes"],
        evaluator_address=evaluator_addr
    )

    return jsonify({**result, "evaluation": evaluation})


@app.route("/api/job/<int:job_id>/cancel", methods=["POST"])
def api_cancel_job(job_id):
    result = engine.cancel_job(job_id)
    return jsonify(result)


# ==================== List API ====================

@app.route("/api/jobs/open")
def api_open_jobs():
    limit = request.args.get("limit", 20, type=int)
    jobs = engine.list_jobs(status="open", limit=limit)
    funded = engine.list_jobs(status="funded", limit=limit)
    return jsonify({"success": True, "jobs": jobs + funded})


@app.route("/api/jobs/agent/<address>")
def api_agent_jobs(address):
    jobs = engine.get_agent_jobs(address)
    return jsonify({"success": True, "jobs": jobs})


# ==================== Stats ====================

@app.route("/api/stats")
def api_stats():
    stats = engine.get_stats()
    return jsonify({"success": True, "stats": stats})


# ==================== Run ====================

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    print()
    print("=" * 50)
    print("  Arc Agent Escrow (ERC-8183)")
    print("=" * 50)
    print(f"  Network: Arc Testnet")
    print(f"  Standard: ERC-8183 Agent Commerce")
    print(f"  Eval threshold: {evaluator.pass_threshold}")
    print(f"  Listening: http://localhost:{port}")
    print("=" * 50)
    print()

    app.run(host="0.0.0.0", port=port, debug=debug)
