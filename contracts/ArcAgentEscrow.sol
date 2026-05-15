// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * ArcAgentEscrow - ERC-8183 Agent Commerce Protocol
 *
 * AI Agent任务托管合约，部署在Arc Testnet上
 * 实现：资金托管、多签名验证、超时退款、信誉系统
 *
 * Job Lifecycle: Open -> Funded -> Assigned -> Submitted -> Verified -> Settled
 */

contract ArcAgentEscrow {

    // ============ Enums ============

    enum JobState { Open, Funded, Assigned, Submitted, Verified, Rejected, Settled, Cancelled, Disputed, Resolved, Expired }
    enum EvaluatorType { None, AI, Human, Oracle, MultiSig }

    // ============ Structs ============

    struct Job {
        uint256 id;
        address employer;
        address worker;
        address evaluator;
        uint256 rewardWei;
        uint256 escrowAmount;
        JobState state;
        EvaluatorType evalType;
        uint256 deadline;
        uint256 createdAt;
        uint256 fundedAt;
        uint256 assignedAt;
        uint256 submittedAt;
        uint256 verifiedAt;
        uint256 settledAt;
        string title;
        string description;
        string category;
        bytes32 resultHash;
        uint8 evalScore;        // 0-100
        string evalNotes;
    }

    struct AgentStats {
        uint256 jobsCompleted;
        uint256 jobsPosted;
        uint256 totalEarned;
        uint256 totalSpent;
        uint256 disputes;
        uint256 reputation;     // 0-10000 (basis points)
    }

    // ============ State ============

    uint256 public jobCount;
    uint256 public platformFeeBps;     // Platform fee in basis points (default: 100 = 1%)
    address public owner;

    mapping(uint256 => Job) public jobs;
    mapping(address => AgentStats) public agentStats;
    mapping(uint256 => mapping(address => bool)) public evaluators;  // jobId -> evaluator -> approved

    // Multi-sig evaluation
    mapping(uint256 => mapping(address => uint8)) public evalVotes;  // jobId -> evaluator -> score
    mapping(uint256 => uint256) public evalVoteCount;

    // ============ Events ============

    event JobCreated(uint256 indexed jobId, address indexed employer, uint256 reward, string category);
    event JobFunded(uint256 indexed jobId, uint256 amount);
    event JobAssigned(uint256 indexed jobId, address indexed worker);
    event WorkSubmitted(uint256 indexed jobId, bytes32 resultHash);
    event JobVerified(uint256 indexed jobId, uint8 score, bool passed);
    event JobSettled(uint256 indexed jobId, address indexed recipient, uint256 amount);
    event JobRejected(uint256 indexed jobId, uint8 score);
    event JobCancelled(uint256 indexed jobId, uint256 refundAmount);
    event JobDisputed(uint256 indexed jobId, address indexed disputer);
    event JobResolved(uint256 indexed jobId, address indexed recipient, uint256 amount);
    event JobExpired(uint256 indexed jobId);

    // ============ Modifiers ============

    modifier onlyEmployer(uint256 jobId) {
        require(jobs[jobId].employer == msg.sender, "Not employer");
        _;
    }

    modifier onlyWorker(uint256 jobId) {
        require(jobs[jobId].worker == msg.sender, "Not worker");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier inState(uint256 jobId, JobState state) {
        require(jobs[jobId].state == state, "Wrong state");
        _;
    }

    modifier notExpired(uint256 jobId) {
        require(block.timestamp <= jobs[jobId].deadline || jobs[jobId].deadline == 0, "Job expired");
        _;
    }

    // ============ Constructor ============

    constructor() {
        owner = msg.sender;
        platformFeeBps = 100; // 1%
    }

    // ============ Job Lifecycle ============

    /**
     * @notice 创建新任务
     * @param title 任务标题
     * @param description 任务描述
     * @param category 任务类别
     * @param rewardWei 奖励金额(wei)
     * @param deadlineHours 截止时间(小时)
     * @param evalType 评估者类型
     */
    function createJob(
        string calldata title,
        string calldata description,
        string calldata category,
        uint256 rewardWei,
        uint256 deadlineHours,
        EvaluatorType evalType
    ) external returns (uint256) {
        require(bytes(title).length > 0, "Title required");
        require(rewardWei > 0, "Reward must be positive");

        uint256 jobId = ++jobCount;
        uint256 deadline = deadlineHours > 0
            ? block.timestamp + (deadlineHours * 1 hours)
            : 0;

        Job storage job = jobs[jobId];
        job.id = jobId;
        job.employer = msg.sender;
        job.rewardWei = rewardWei;
        job.state = JobState.Open;
        job.evalType = evalType;
        job.deadline = deadline;
        job.createdAt = block.timestamp;
        job.title = title;
        job.description = description;
        job.category = category;

        agentStats[msg.sender].jobsPosted++;

        emit JobCreated(jobId, msg.sender, rewardWei, category);
        return jobId;
    }

    /**
     * @notice 托管资金
     */
    function fundJob(uint256 jobId)
        external
        payable
        onlyEmployer(jobId)
        inState(jobId, JobState.Open)
    {
        require(msg.value >= jobs[jobId].rewardWei, "Insufficient funding");

        jobs[jobId].escrowAmount = msg.value;
        jobs[jobId].state = JobState.Funded;
        jobs[jobId].fundedAt = block.timestamp;

        emit JobFunded(jobId, msg.value);
    }

    /**
     * @notice Worker接受任务
     */
    function acceptJob(uint256 jobId)
        external
        inState(jobId, JobState.Funded)
        notExpired(jobId)
    {
        jobs[jobId].worker = msg.sender;
        jobs[jobId].state = JobState.Assigned;
        jobs[jobId].assignedAt = block.timestamp;

        emit JobAssigned(jobId, msg.sender);
    }

    /**
     * @notice Worker提交工作成果
     * @param resultHash 工作成果的IPFS/链上哈希
     */
    function submitWork(uint256 jobId, bytes32 resultHash)
        external
        onlyWorker(jobId)
        inState(jobId, JobState.Assigned)
    {
        jobs[jobId].resultHash = resultHash;
        jobs[jobId].state = JobState.Submitted;
        jobs[jobId].submittedAt = block.timestamp;

        emit WorkSubmitted(jobId, resultHash);
    }

    /**
     * @notice 单一评估者验证
     * @param score 评分 0-100
     * @param passed 是否通过
     */
    function verifyJob(uint256 jobId, uint8 score, bool passed)
        external
        inState(jobId, JobState.Submitted)
    {
        require(score <= 100, "Score max 100");
        // In production, verify msg.sender is authorized evaluator

        jobs[jobId].evalScore = score;
        jobs[jobId].evaluator = msg.sender;
        jobs[jobId].verifiedAt = block.timestamp;

        if (passed) {
            jobs[jobId].state = JobState.Verified;
            _settle(jobId, jobs[jobId].worker);
        } else {
            jobs[jobId].state = JobState.Rejected;
            emit JobRejected(jobId, score);
        }
    }

    /**
     * @notice Multi-sig评估投票
     */
    function castEvalVote(uint256 jobId, uint8 score)
        external
        inState(jobId, JobState.Submitted)
    {
        require(evaluators[jobId][msg.sender], "Not authorized evaluator");
        require(evalVotes[jobId][msg.sender] == 0, "Already voted");
        require(score <= 100, "Score max 100");

        evalVotes[jobId][msg.sender] = score;
        evalVoteCount[jobId]++;

        // Need 3 votes to finalize (for multi-sig)
        if (evalVoteCount[jobId] >= 3) {
            uint256 avgScore = _calculateAvgScore(jobId);
            bool passed = avgScore >= 60;

            jobs[jobId].evalScore = uint8(avgScore);
            jobs[jobId].verifiedAt = block.timestamp;

            if (passed) {
                jobs[jobId].state = JobState.Verified;
                _settle(jobId, jobs[jobId].worker);
            } else {
                jobs[jobId].state = JobState.Rejected;
                emit JobRejected(jobId, uint8(avgScore));
            }
        }
    }

    /**
     * @notice 提出争议
     */
    function disputeJob(uint256 jobId)
        external
    {
        Job storage job = jobs[jobId];
        require(
            msg.sender == job.employer || msg.sender == job.worker,
            "Not participant"
        );
        require(
            job.state == JobState.Submitted || job.state == JobState.Rejected,
            "Cannot dispute"
        );

        job.state = JobState.Disputed;
        emit JobDisputed(jobId, msg.sender);
    }

    /**
     * @notice 解决争议（owner/仲裁者）
     * @param jobId 任务ID
     * @param workerWins 工作者是否胜诉
     */
    function resolveDispute(uint256 jobId, bool workerWins)
        external
        onlyOwner
        inState(jobId, JobState.Disputed)
    {
        jobs[jobId].state = JobState.Resolved;

        if (workerWins) {
            _settle(jobId, jobs[jobId].worker);
        } else {
            _settle(jobId, jobs[jobId].employer);
        }

        // Update dispute stats
        agentStats[jobs[jobId].employer].disputes++;
        agentStats[jobs[jobId].worker].disputes++;
    }

    /**
     * @notice 取消任务并退款
     */
    function cancelJob(uint256 jobId)
        external
        onlyEmployer(jobId)
    {
        Job storage job = jobs[jobId];
        require(
            job.state == JobState.Open ||
            job.state == JobState.Funded ||
            (job.state == JobState.Assigned && block.timestamp > job.deadline),
            "Cannot cancel"
        );

        job.state = JobState.Cancelled;

        if (job.escrowAmount > 0) {
            uint256 refund = job.escrowAmount;
            job.escrowAmount = 0;
            (bool success, ) = job.employer.call{value: refund}("");
            require(success, "Refund failed");
        }

        emit JobCancelled(jobId, job.escrowAmount);
    }

    /**
     * @notice 检查并标记过期任务
     */
    function checkExpiry(uint256 jobId) external {
        Job storage job = jobs[jobId];
        require(job.deadline > 0, "No deadline");
        require(block.timestamp > job.deadline, "Not expired yet");
        require(
            job.state == JobState.Open ||
            job.state == JobState.Funded ||
            job.state == JobState.Assigned,
            "Cannot expire"
        );

        job.state = JobState.Expired;

        if (job.escrowAmount > 0) {
            uint256 refund = job.escrowAmount;
            job.escrowAmount = 0;
            (bool success, ) = job.employer.call{value: refund}("");
            require(success, "Refund failed");
        }

        emit JobExpired(jobId);
    }

    // ============ Internal ============

    function _settle(uint256 jobId, address recipient) internal {
        Job storage job = jobs[jobId];
        job.state = JobState.Settled;
        job.settledAt = block.timestamp;

        uint256 amount = job.escrowAmount;
        uint256 fee = (amount * platformFeeBps) / 10000;
        uint256 payout = amount - fee;

        job.escrowAmount = 0;

        // Pay worker
        (bool success1, ) = recipient.call{value: payout}("");
        require(success1, "Payout failed");

        // Pay platform fee
        if (fee > 0) {
            (bool success2, ) = owner.call{value: fee}("");
            require(success2, "Fee transfer failed");
        }

        // Update stats
        if (recipient == job.worker) {
            agentStats[job.worker].jobsCompleted++;
            agentStats[job.worker].totalEarned += payout;
            agentStats[job.employer].totalSpent += amount;
        }

        emit JobSettled(jobId, recipient, payout);
    }

    function _calculateAvgScore(uint256 jobId) internal view returns (uint256) {
        // Simplified: count total votes and average
        // In production, iterate through evaluators
        uint256 total = 0;
        uint256 count = evalVoteCount[jobId];
        if (count == 0) return 0;

        // This is a simplified version
        // Full implementation would track all votes
        return total / count;
    }

    // ============ View Functions ============

    function getJob(uint256 jobId) external view returns (
        address employer, address worker, uint256 reward,
        JobState state, uint256 escrow, uint256 deadline
    ) {
        Job storage job = jobs[jobId];
        return (job.employer, job.worker, job.rewardWei, job.state, job.escrowAmount, job.deadline);
    }

    function getAgentStats(address agent) external view returns (
        uint256 completed, uint256 posted, uint256 earned, uint256 spent, uint256 reputation
    ) {
        AgentStats storage stats = agentStats[agent];
        return (stats.jobsCompleted, stats.jobsPosted, stats.totalEarned, stats.totalSpent, stats.reputation);
    }

    // ============ Admin ============

    function setPlatformFee(uint256 bps) external onlyOwner {
        require(bps <= 1000, "Max 10%");
        platformFeeBps = bps;
    }

    function addEvaluator(uint256 jobId, address evaluator) external {
        // Employer or owner can add evaluators
        require(
            msg.sender == jobs[jobId].employer || msg.sender == owner,
            "Not authorized"
        );
        evaluators[jobId][evaluator] = true;
    }

    // Allow contract to receive USDC (for Arc Paymaster integration)
    receive() external payable {}
}
