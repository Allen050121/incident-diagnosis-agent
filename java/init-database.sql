-- ============================================================
-- Incident Diagnosis Agent - Database Schema
-- Version: 1.0.0
-- Database: incident_db
-- ============================================================

-- Create database
CREATE DATABASE IF NOT EXISTS incident_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE incident_db;

-- ============================================================
-- 1. INCIDENTS - 告警事件表
-- ============================================================
CREATE TABLE IF NOT EXISTS incidents
(
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 业务唯一标识（幂等键，告警可能重复发送）
    incident_id       VARCHAR(50)  NOT NULL,

    -- 告警来源信息
    service           VARCHAR(100) NOT NULL COMMENT '告警服务名',
    endpoint          VARCHAR(200) COMMENT '告警接口路径',

    -- 告警类型与数值
    alert_type        VARCHAR(50)  NOT NULL COMMENT 'P95_LATENCY_HIGH, ERROR_RATE_HIGH, etc.',
    alert_value       DECIMAL(10, 2) COMMENT '告警阈值当前值',
    threshold         DECIMAL(10, 2) COMMENT '告警阈值设定值',

    -- 解析后的分类信息
    incident_type     VARCHAR(30) COMMENT 'LATENCY, ERROR, THROUGHPUT, MQ_LAG',
    scope             VARCHAR(30) COMMENT 'SINGLE_ENDPOINT, MULTI_ENDPOINT, SERVICE_WIDE',

    -- 时间窗口
    started_at        DATETIME     NOT NULL COMMENT '告警开始时间',
    ended_at          DATETIME COMMENT '告警结束时间',
    time_window_start DATETIME COMMENT '调查窗口开始',
    time_window_end   DATETIME COMMENT '调查窗口结束',

    -- Trace ID 关联
    trace_id          VARCHAR(50) COMMENT '分布式追踪ID',

    -- 状态流转: OPEN -> QUEUED -> INVESTIGATING -> DIAGNOSED/INCONCLUSIVE/FAILED/CANCELLED
    status            VARCHAR(20)  NOT NULL DEFAULT 'OPEN',

    -- 元数据
    source_system     VARCHAR(50) COMMENT '告警来源系统',
    severity          VARCHAR(20) COMMENT '告警级别: P0/P1/P2/P3',
    labels            JSON COMMENT '附加标签',

    -- 时间戳
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 唯一索引（幂等性）
    CONSTRAINT uk_incident_id UNIQUE (incident_id)
) ENGINE = InnoDB COMMENT ='告警事件表';

-- 索引
CREATE INDEX idx_incidents_service ON incidents (service);
CREATE INDEX idx_incidents_status ON incidents (status);
CREATE INDEX idx_incidents_started_at ON incidents (started_at);
CREATE INDEX idx_incidents_service_status ON incidents (service, status);
CREATE INDEX idx_incidents_trace_id ON incidents (trace_id);

-- ============================================================
-- 2. DIAGNOSIS_TASKS - 诊断任务表
-- ============================================================
CREATE TABLE IF NOT EXISTS diagnosis_tasks
(
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 业务唯一标识（幂等键，任务可能重复创建）
    task_id                 VARCHAR(50) NOT NULL,

    -- 关联告警
    incident_id             VARCHAR(50) NOT NULL,

    -- Redis Streams 消息信息
    message_id              VARCHAR(100) COMMENT 'Redis Streams消息ID',
    schema_version          INT                  DEFAULT 1,

    -- 任务状态: QUEUED -> INVESTIGATING -> DIAGNOSED/INCONCLUSIVE/FAILED/CANCELLED
    status                  VARCHAR(20) NOT NULL DEFAULT 'QUEUED',

    -- 调查计划
    investigation_plan      JSON COMMENT '调查步骤计划',
    plan_steps_count        INT                  DEFAULT 0 COMMENT '计划步骤数',

    -- 预算与限制
    deadline_at             DATETIME COMMENT '任务截止时间',
    max_tool_calls          INT                  DEFAULT 10 COMMENT '最大工具调用次数',
    max_verification_rounds INT                  DEFAULT 3 COMMENT '最大验证轮次',
    max_tokens              INT                  DEFAULT 50000 COMMENT '最大Token数',

    -- 实际消耗统计
    tool_calls_count        INT                  DEFAULT 0 COMMENT '实际工具调用次数',
    verification_rounds     INT                  DEFAULT 0 COMMENT '实际验证轮次',
    token_input_count       INT                  DEFAULT 0 COMMENT '输入Token消耗',
    token_output_count      INT                  DEFAULT 0 COMMENT '输出Token消耗',
    total_cost_usd          DECIMAL(10, 4)       DEFAULT 0 COMMENT '模型调用成本(美元)',

    -- 时间统计
    queue_wait_seconds      INT                  DEFAULT 0 COMMENT '排队等待秒数',
    investigation_seconds   INT                  DEFAULT 0 COMMENT '调查耗时秒数',

    -- 错误信息
    error_type              VARCHAR(50) COMMENT '错误类型: TIMEOUT, TOOL_FAILURE, MODEL_ERROR, etc.',
    error_message           TEXT COMMENT '错误详情',

    -- 取消标记
    cancelled_at            DATETIME COMMENT '取消时间',
    cancelled_by            VARCHAR(50) COMMENT '取消人/系统',
    cancel_reason           VARCHAR(200) COMMENT '取消原因',

    -- 时间戳
    created_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at              DATETIME COMMENT '开始执行时间',
    completed_at            DATETIME COMMENT '完成时间',
    updated_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 唯一索引（幂等性）
    CONSTRAINT uk_task_id UNIQUE (task_id),

    -- 外键关联
    CONSTRAINT fk_task_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE RESTRICT
) ENGINE = InnoDB COMMENT ='诊断任务表';

-- 索引
CREATE INDEX idx_tasks_incident_id ON diagnosis_tasks (incident_id);
CREATE INDEX idx_tasks_status ON diagnosis_tasks (status);
CREATE INDEX idx_tasks_created_at ON diagnosis_tasks (created_at);
CREATE INDEX idx_tasks_deadline_at ON diagnosis_tasks (deadline_at);
CREATE INDEX idx_tasks_status_created ON diagnosis_tasks (status, created_at);

-- ============================================================
-- 3. EVIDENCE - 证据表
-- ============================================================
CREATE TABLE IF NOT EXISTS evidence
(
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 业务唯一标识（幂等键，证据需要唯一ID引用）
    evidence_id             VARCHAR(50) NOT NULL,

    -- 关联任务
    task_id                 VARCHAR(50) NOT NULL,

    -- 证据来源: logs, metrics, deployments, runbooks
    source                  VARCHAR(30) NOT NULL,

    -- 查询信息
    query_service           VARCHAR(100) COMMENT '查询的服务名',
    query_time_window_start DATETIME COMMENT '查询时间窗口开始',
    query_time_window_end   DATETIME COMMENT '查询时间窗口结束',
    query_keywords          VARCHAR(500) COMMENT '查询关键词',

    -- 证据内容
    content_type            VARCHAR(30) COMMENT 'LOG_SUMMARY, METRIC_TREND, DEPLOYMENT_INFO, RUNBOOK_SECTION',
    content_summary         TEXT COMMENT '证据摘要（用于模型）',
    content_raw             JSON COMMENT '原始证据数据',

    -- 截断与去重标记
    is_truncated            BOOLEAN              DEFAULT FALSE COMMENT '是否截断',
    truncated_reason        VARCHAR(100) COMMENT '截断原因',
    original_count          INT COMMENT '原始数据条数',
    returned_count          INT COMMENT '返回数据条数',
    is_deduplicated         BOOLEAN              DEFAULT FALSE COMMENT '是否去重',

    -- 证据有效性
    is_valid                BOOLEAN              DEFAULT TRUE COMMENT '证据是否有效',
    validity_note           VARCHAR(200) COMMENT '有效性说明',

    -- 时间戳
    evidence_timestamp      DATETIME COMMENT '证据发生时间',
    created_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 唯一索引（幂等性）
    CONSTRAINT uk_evidence_id UNIQUE (evidence_id),

    -- 外键关联
    CONSTRAINT fk_evidence_task FOREIGN KEY (task_id)
        REFERENCES diagnosis_tasks (task_id) ON DELETE CASCADE
) ENGINE = InnoDB COMMENT ='证据表';

-- 索引
CREATE INDEX idx_evidence_task_id ON evidence (task_id);
CREATE INDEX idx_evidence_source ON evidence (source);
CREATE INDEX idx_evidence_timestamp ON evidence (evidence_timestamp);
CREATE INDEX idx_evidence_task_source ON evidence (task_id, source);

-- ============================================================
-- 4. HYPOTHESES - 根因假设表（一个任务最多3个假设，自增主键即可）
-- ============================================================
CREATE TABLE IF NOT EXISTS hypotheses
(
    id                           BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 关联任务
    task_id                      VARCHAR(50)  NOT NULL,

    -- 根因编码（如 DATABASE_CONNECTION_POOL_EXHAUSTED）
    cause_code                   VARCHAR(100) NOT NULL,

    -- 根因分类（DATABASE, REDIS, DOWNSTREAM, APPLICATION, CONFIG, etc.）
    cause_category               VARCHAR(50) COMMENT '根因大类',

    -- 置信度: HIGH, MEDIUM, LOW, INSUFFICIENT
    confidence                   VARCHAR(20)  NOT NULL DEFAULT 'MEDIUM',
    confidence_calibration       TEXT COMMENT '置信度校准说明',

    -- 排名（Top-3）
    cause_rank                   INT                   DEFAULT 0 COMMENT '排名 1-3, 0表示未排序',

    -- 支持证据ID列表
    supporting_evidence_ids      JSON COMMENT '支持证据ID数组 ["METRIC-102", "LOG-883"]',
    supporting_evidence_count    INT                   DEFAULT 0,

    -- 反证证据ID列表
    contradicting_evidence_ids   JSON COMMENT '反证证据ID数组 ["DEPLOY-EMPTY"]',
    contradicting_evidence_count INT                   DEFAULT 0,

    -- 推理摘要
    reasoning_summary            TEXT COMMENT '推理过程摘要',

    -- 验证信息
    verification_tool            VARCHAR(50) COMMENT '下一步验证工具',
    verification_params          JSON COMMENT '验证参数',
    verification_status          VARCHAR(20) COMMENT 'PENDING, VERIFIED, REFUTED, SKIPPED',
    verification_result          TEXT COMMENT '验证结果',

    -- 验证轮次
    verification_round           INT                   DEFAULT 0 COMMENT '在第几轮验证中生成',

    -- 是否为症状而非根因
    is_symptom                   BOOLEAN               DEFAULT FALSE COMMENT '标记为症状而非根因',

    -- 时间戳
    created_at                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 外键关联
    CONSTRAINT fk_hypothesis_task FOREIGN KEY (task_id)
        REFERENCES diagnosis_tasks (task_id) ON DELETE CASCADE
) ENGINE = InnoDB COMMENT ='根因假设表';

-- 索引
CREATE INDEX idx_hypotheses_task_id ON hypotheses (task_id);
CREATE INDEX idx_hypotheses_cause_code ON hypotheses (cause_code);
CREATE INDEX idx_hypotheses_cause_rank ON hypotheses (cause_rank);
CREATE INDEX idx_hypotheses_task_rank ON hypotheses (task_id, cause_rank);

-- ============================================================
-- 5. DIAGNOSIS_REPORTS - 诊断报告表（一个任务只有一个报告）
-- ============================================================
CREATE TABLE IF NOT EXISTS diagnosis_reports
(
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 关联任务和告警
    task_id                 VARCHAR(50) NOT NULL,
    incident_id             VARCHAR(50) NOT NULL,

    -- 最终状态: DIAGNOSED, INCONCLUSIVE, FAILED, CANCELLED
    final_status            VARCHAR(20) NOT NULL,

    -- Top-3 根因摘要
    top_causes              JSON COMMENT 'Top-3根因JSON数组',
    top_cause_count         INT                  DEFAULT 0,

    -- 根因命中标记（用于评测）
    expected_root_cause     VARCHAR(100) COMMENT '期望根因（测试用）',
    top1_hit                BOOLEAN COMMENT 'Top-1是否命中',
    top3_hit                BOOLEAN COMMENT 'Top-3是否命中',

    -- 推荐动作
    recommended_actions     JSON COMMENT '推荐动作JSON数组',

    -- 缺失证据
    missing_evidence        JSON COMMENT '缺失证据列表',
    missing_evidence_reason TEXT COMMENT '缺失原因说明',

    -- 工具失败记录
    tool_failures           JSON COMMENT '工具失败列表',

    -- 评测指标
    evidence_precision      DECIMAL(5, 4) COMMENT '证据精确率',
    evidence_coverage       DECIMAL(5, 4) COMMENT '证据覆盖率',
    tool_selection_accuracy DECIMAL(5, 4) COMMENT '工具选择准确率',

    -- 时间戳
    created_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 任务唯一约束
    CONSTRAINT uk_report_task UNIQUE (task_id),

    -- 外键关联
    CONSTRAINT fk_report_task FOREIGN KEY (task_id)
        REFERENCES diagnosis_tasks (task_id) ON DELETE CASCADE,
    CONSTRAINT fk_report_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id) ON DELETE RESTRICT
) ENGINE = InnoDB COMMENT ='诊断报告表';

-- 索引
CREATE INDEX idx_reports_incident_id ON diagnosis_reports (incident_id);
CREATE INDEX idx_reports_final_status ON diagnosis_reports (final_status);

-- ============================================================
-- 6. TOOL_CALLS - 工具调用审计表（按调用序号生成）
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_calls
(
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 关联任务和证据
    task_id           VARCHAR(50) NOT NULL,
    evidence_id       VARCHAR(50) COMMENT '产生的证据ID',

    -- 工具信息
    tool_name         VARCHAR(50) NOT NULL COMMENT 'query_logs, query_metrics, query_deployments, search_runbooks',
    tool_purpose      VARCHAR(200) COMMENT '调用目的',

    -- 调用参数
    parameters        JSON COMMENT '调用参数JSON',

    -- 调用状态: SUCCESS, TIMEOUT, NO_DATA, PERMISSION_DENIED, SERVICE_UNAVAILABLE, TRUNCATED, ERROR
    result_status     VARCHAR(30) NOT NULL,
    result_message    TEXT COMMENT '结果消息',

    -- 执行统计
    execution_time_ms INT COMMENT '执行耗时(毫秒)',
    retry_count       INT                  DEFAULT 0 COMMENT '重试次数',

    -- 调用轮次
    call_round        INT                  DEFAULT 0 COMMENT '调用轮次',
    call_sequence     INT                  DEFAULT 0 COMMENT '调用序号',

    -- 时间戳
    started_at        DATETIME COMMENT '调用开始时间',
    completed_at      DATETIME COMMENT '调用完成时间',
    created_at        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 外键关联
    CONSTRAINT fk_toolcall_task FOREIGN KEY (task_id)
        REFERENCES diagnosis_tasks (task_id) ON DELETE CASCADE
) ENGINE = InnoDB COMMENT ='工具调用审计表';

-- 索引
CREATE INDEX idx_toolcalls_task_id ON tool_calls (task_id);
CREATE INDEX idx_toolcalls_tool_name ON tool_calls (tool_name);
CREATE INDEX idx_toolcalls_status ON tool_calls (result_status);
CREATE INDEX idx_toolcalls_task_tool ON tool_calls (task_id, tool_name);
CREATE INDEX idx_toolcalls_evidence_id ON tool_calls (evidence_id);

-- ============================================================
-- 7. AGENT_TRACES - Agent执行轨迹表（按节点执行顺序生成）
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_traces
(
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 关联任务
    task_id                 VARCHAR(50) NOT NULL,

    -- 节点信息
    node_name               VARCHAR(50) NOT NULL COMMENT 'load_incident, classify_incident, create_plan, etc.',
    node_type               VARCHAR(30) COMMENT 'ACTION, DECISION, LOOP, OUTPUT',
    parent_node             VARCHAR(50) COMMENT '父节点名称',

    -- 模型调用信息
    model_call_id           VARCHAR(50) COMMENT '模型调用ID',
    model_name              VARCHAR(50) COMMENT '使用的模型名称',
    model_prompt_tokens     INT                  DEFAULT 0 COMMENT 'Prompt Token数',
    model_completion_tokens INT                  DEFAULT 0 COMMENT 'Completion Token数',
    model_total_tokens      INT                  DEFAULT 0 COMMENT '总Token数',

    -- 执行统计
    started_at              DATETIME COMMENT '节点开始时间',
    completed_at            DATETIME COMMENT '节点完成时间',
    duration_ms             INT COMMENT '节点耗时(毫秒)',

    -- 状态
    status                  VARCHAR(20) COMMENT 'SUCCESS, FAILED, SKIPPED, PENDING',
    error_message           TEXT COMMENT '错误信息',

    -- 输入输出摘要
    input_summary           TEXT COMMENT '输入摘要',
    output_summary          TEXT COMMENT '输出摘要',

    -- 时间戳
    created_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 外键关联
    CONSTRAINT fk_trace_task FOREIGN KEY (task_id)
        REFERENCES diagnosis_tasks (task_id) ON DELETE CASCADE
) ENGINE = InnoDB COMMENT ='Agent执行轨迹表';

-- 索引
CREATE INDEX idx_traces_task_id ON agent_traces (task_id);
CREATE INDEX idx_traces_node_name ON agent_traces (node_name);
CREATE INDEX idx_traces_status ON agent_traces (status);
CREATE INDEX idx_traces_task_node ON agent_traces (task_id, node_name);

-- ============================================================
-- 8. FAULT_SCENARIOS - 故障场景模板表（故障模板唯一标识）
-- ============================================================
CREATE TABLE IF NOT EXISTS fault_scenarios
(
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 业务唯一标识（幂等键）
    fault_id              VARCHAR(50)  NOT NULL COMMENT 'mysql-slow-query-001',

    -- 故障分类
    category              VARCHAR(50)  NOT NULL COMMENT 'DATABASE, REDIS, DOWNSTREAM, APPLICATION, CONFIG, MQ',

    -- 根因信息
    root_cause            VARCHAR(100) NOT NULL COMMENT 'MISSING_INDEX, CONNECTION_POOL_EXHAUSTED, etc.',
    symptoms              JSON COMMENT '症状列表',
    contributing_factors  JSON COMMENT '放大因素',
    affected_components   JSON COMMENT '受影响组件',

    -- 受影响服务
    affected_service      VARCHAR(100) NOT NULL COMMENT 'order-service, inventory-service, payment-mock-service',

    -- 触发配置
    trigger_type          VARCHAR(50) COMMENT 'feature_toggle, api_call, config_change',
    trigger_params        JSON COMMENT '触发参数',

    -- 期望信号
    expected_logs         JSON COMMENT '期望日志信号',
    expected_metrics      JSON COMMENT '期望指标信号',
    expected_deployments  JSON COMMENT '期望部署记录',

    -- 期望工具调用
    expected_tools        JSON COMMENT '期望Agent调用的工具列表',

    -- 禁止结论
    forbidden_conclusions JSON COMMENT 'Agent不应得出的结论列表',

    -- 状态
    is_active             BOOLEAN               DEFAULT TRUE COMMENT '是否启用',

    -- 版本信息
    version               INT                   DEFAULT 1,

    -- 时间戳
    created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 唯一索引（幂等性）
    CONSTRAINT uk_fault_id UNIQUE (fault_id)
) ENGINE = InnoDB COMMENT ='故障场景模板表';

-- 紁引
CREATE INDEX idx_faultscenarios_category ON fault_scenarios (category);
CREATE INDEX idx_faultscenarios_service ON fault_scenarios (affected_service);
CREATE INDEX idx_faultscenarios_root_cause ON fault_scenarios (root_cause);
CREATE INDEX idx_faultscenarios_active ON fault_scenarios (is_active);

-- ============================================================
-- 9. FAULT_EXECUTIONS - 故障执行记录表（按执行记录生成）
-- ============================================================
CREATE TABLE IF NOT EXISTS fault_executions
(
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 关联故障模板
    fault_id       VARCHAR(50) NOT NULL,

    -- 关联诊断任务
    task_id        VARCHAR(50) COMMENT '触发的诊断任务',

    -- 执行参数（实际使用的参数）
    actual_params  JSON COMMENT '实际触发参数',

    -- 执行状态
    trigger_status VARCHAR(20) COMMENT 'TRIGGERED, ACTIVE, CLEANED, FAILED',
    cleanup_status VARCHAR(20) COMMENT 'PENDING, COMPLETED, FAILED',

    -- 时间戳
    triggered_at   DATETIME COMMENT '触发时间',
    detected_at    DATETIME COMMENT '检测时间',
    cleaned_at     DATETIME COMMENT '清理时间',
    created_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 外键关联
    CONSTRAINT fk_execution_fault FOREIGN KEY (fault_id)
        REFERENCES fault_scenarios (fault_id) ON DELETE RESTRICT
) ENGINE = InnoDB COMMENT ='故障执行记录表';

-- 紁引
CREATE INDEX idx_faultexecutions_fault_id ON fault_executions (fault_id);
CREATE INDEX idx_faultexecutions_task_id ON fault_executions (task_id);
CREATE INDEX idx_faultexecutions_trigger_status ON fault_executions (trigger_status);

-- ============================================================
-- 10. SERVICE_TOPOLOGY - 服务拓扑表（服务名唯一）
-- ============================================================
CREATE TABLE IF NOT EXISTS service_topology
(
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 业务唯一标识（幂等键）
    service_name     VARCHAR(100) NOT NULL,

    -- 依赖关系
    depends_on       JSON COMMENT '依赖的服务列表',

    -- 组件信息
    components       JSON COMMENT '包含的组件: mysql, redis, rocketmq, etc.',

    -- 接口信息
    endpoints        JSON COMMENT '暴露的接口列表',

    -- 版本信息
    current_version  VARCHAR(50) COMMENT '当前版本',
    previous_version VARCHAR(50) COMMENT '上一版本',

    -- 状态
    is_active        BOOLEAN               DEFAULT TRUE,

    -- 时间戳
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 唯一索引（幂等性）
    CONSTRAINT uk_service_name UNIQUE (service_name)
) ENGINE = InnoDB COMMENT ='服务拓扑表';

-- ============================================================
-- 11. RUNBOOKS - Runbook文档表（文档唯一标识）
-- ============================================================
CREATE TABLE IF NOT EXISTS runbooks
(
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 业务唯一标识（幂等键）
    runbook_id          VARCHAR(50)  NOT NULL,

    -- 文档信息
    title               VARCHAR(200) NOT NULL,
    category            VARCHAR(50) COMMENT '故障类型分类',

    -- 内容
    content             TEXT COMMENT '文档内容',
    symptoms_section    TEXT COMMENT '症状描述',
    check_steps         TEXT COMMENT '检查步骤',
    key_metrics         TEXT COMMENT '关键指标',
    common_causes       TEXT COMMENT '常见根因',
    actions             TEXT COMMENT '处置建议',
    not_applicable      TEXT COMMENT '不适用条件',

    -- 关联服务
    applicable_services JSON COMMENT '适用的服务列表',

    -- 元数据
    source              VARCHAR(50) COMMENT '来源',
    version             INT                   DEFAULT 1,
    is_active           BOOLEAN               DEFAULT TRUE,

    -- 时间戳
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 唯一索引（幂等性）
    CONSTRAINT uk_runbook_id UNIQUE (runbook_id)
) ENGINE = InnoDB COMMENT ='Runbook文档表';

-- 紁引（用于BM25全文检索）
CREATE INDEX idx_runbooks_category ON runbooks (category);
CREATE INDEX idx_runbooks_source ON runbooks (source);

-- ============================================================
-- 12. EVALUATION_RESULTS - 评测结果表（一个任务只有一个评测结果）
-- ============================================================
CREATE TABLE IF NOT EXISTS evaluation_results
(
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- 关联诊断任务
    task_id                 VARCHAR(50) NOT NULL,

    -- 关联故障执行
    execution_id            INT COMMENT '故障执行ID',

    -- 核心指标
    top1_accuracy           BOOLEAN COMMENT 'Top-1命中率',
    top3_recall             BOOLEAN COMMENT 'Top-3召回率',
    symptom_as_cause_error  BOOLEAN COMMENT '症状误判为根因',

    -- 证据指标
    evidence_precision      DECIMAL(5, 4) COMMENT '证据精确率',
    evidence_coverage       DECIMAL(5, 4) COMMENT '证据覆盖率',

    -- 工具指标
    tool_selection_accuracy DECIMAL(5, 4) COMMENT '工具选择准确率',
    tool_argument_accuracy  DECIMAL(5, 4) COMMENT '工具参数准确率',

    -- 效率指标
    tool_calls_count        INT COMMENT '工具调用次数',
    diagnosis_time_seconds  INT COMMENT '诊断耗时(秒)',
    total_tokens            INT COMMENT '总Token消耗',
    total_cost_usd          DECIMAL(10, 4) COMMENT '总成本',

    -- 结论指标
    unsupported_conclusion  BOOLEAN COMMENT '是否无证据结论',
    inconclusive_precision  BOOLEAN COMMENT 'INCONCLUSIVE是否合理',

    -- 测试环境信息
    git_commit              VARCHAR(50) COMMENT '代码版本',
    prompt_version          VARCHAR(50) COMMENT 'Prompt版本',
    model_version           VARCHAR(50) COMMENT '模型版本',

    -- 评审信息
    reviewed_by             VARCHAR(50) COMMENT '评审人',
    review_notes            TEXT COMMENT '评审备注',

    -- 时间戳
    created_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 任务唯一约束
    CONSTRAINT uk_eval_task UNIQUE (task_id),

    -- 外键关联
    CONSTRAINT fk_eval_task FOREIGN KEY (task_id)
        REFERENCES diagnosis_tasks (task_id) ON DELETE CASCADE
) ENGINE = InnoDB COMMENT ='评测结果表';

-- 紁引
CREATE INDEX idx_eval_top1 ON evaluation_results (top1_accuracy);
CREATE INDEX idx_eval_created_at ON evaluation_results (created_at);

-- ============================================================
-- 完成
-- ============================================================
SHOW TABLES;

-- 验证表结构
SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'incident_db';