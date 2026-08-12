import { useEffect, useState } from "react";
import { Card, Table, Tag, Alert, Empty, Tabs, Button, Select, Input, Space, Modal, Descriptions, Spin } from "antd";
import { SearchOutlined, EyeOutlined } from "@ant-design/icons";
import { api, DECISION_META, AssessmentItem, ModelEval } from "../api";

const LEVEL_COLOR: Record<string, string> = {
  低: "success",
  中: "warning",
  高: "orange",
  极高: "red",
};

const EVENT_LABEL: Record<string, string> = {
  transfer: "转账", loan_apply: "贷款申请", card_txn: "卡片交易", repay: "还款", login: "登录",
};

export default function AssessmentBoard() {
  return (
    <Tabs
      defaultActiveKey="history"
      items={[
        { key: "history", label: "评估历史", children: <AssessmentHistory /> },
        { key: "eval", label: "模型评估", children: <ModelEvalView /> },
        { key: "features", label: "特征工程", children: <FeatureView /> },
      ]}
    />
  );
}

// ============================================================
// 评估历史 (对齐 AI_Risk 源项目)
// ============================================================
function AssessmentHistory() {
  const [items, setItems] = useState<AssessmentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [filters, setFilters] = useState({
    decision: "",
    risk_level: "",
    event_type: "",
    user_id: "",
  });

  const load = async (p = page, ps = pageSize) => {
    setLoading(true);
    try {
      const res = await api.assessments({
        page: p, page_size: ps,
        decision: filters.decision || undefined,
        risk_level: filters.risk_level || undefined,
        event_type: filters.event_type || undefined,
        user_id: filters.user_id || undefined,
      });
      setItems(res.items);
      setTotal(res.total);
      setPage(res.page);
      setPageSize(res.page_size);
    } catch (e: any) {
      // 简单提示，不阻塞
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(1, pageSize); }, []);

  const onSearch = () => load(1, pageSize);

  const openDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      const d = await api.assessmentDetail(id);
      setDetail(d);
    } finally {
      setDetailLoading(false);
    }
  };

  const formatTime = (v: string | null) => {
    if (!v) return "-";
    const d = new Date(v);
    return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  };

  const columns = [
    {
      title: "评估ID", dataIndex: "assessment_id", width: 170,
      render: (v: string) => (
        <span className="font-mono text-[13px] text-[#d46b08] cursor-pointer hover:underline" onClick={() => openDetail(v)}>
          {v.length > 18 ? v.slice(0, 18) + "..." : v}
        </span>
      ),
    },
    { title: "用户", dataIndex: "user_id", width: 120 },
    { title: "事件", dataIndex: "event_type", width: 100, render: (v: string) => <Tag bordered={false}>{EVENT_LABEL[v] || v}</Tag> },
    { title: "评分", dataIndex: "final_score", width: 70, align: "center" as const, render: (v: number) => <span className="font-semibold">{v}</span> },
    { title: "等级", dataIndex: "risk_level", width: 80, align: "center" as const, render: (v: string) => <Tag color={LEVEL_COLOR[v] || "default"}>{v}</Tag> },
    { title: "决策", dataIndex: "decision", width: 90, align: "center" as const, render: (v: string) => { const dm = DECISION_META[v]; return <Tag color={dm?.color}>{dm?.label}</Tag>; } },
    { title: "命中", dataIndex: "rule_count", width: 70, align: "center" as const },
    { title: "ML分（P拒绝）", dataIndex: "ml_score", width: 110, align: "center" as const, render: (v: number | null) => v == null ? "-" : v.toFixed(3) },
    { title: "风险分（sigmoid）", dataIndex: "final_score", width: 120, align: "center" as const, render: (v: number) => v },
    { title: "时间", dataIndex: "create_time", width: 140, render: (v: string) => <span className="text-[12px]">{formatTime(v)}</span> },
    {
      title: "操作", key: "action", width: 80, align: "center" as const,
      render: (_: any, r: AssessmentItem) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(r.assessment_id)}>详情</Button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <Card size="small">
        <div className="flex items-center justify-between mb-3">
          <div>
            <span className="text-[18px] font-semibold">评估历史</span>
            <span className="ml-3 text-[13px] text-[#8c8c8c]">全量评估，含已结案+通过/标记（案件工作台只看待办）</span>
          </div>
        </div>
        <Space wrap className="mb-4">
          <Select
            placeholder="全部决策" allowClear style={{ width: 120 }}
            value={filters.decision || undefined}
            onChange={(v) => setFilters({ ...filters, decision: v || "" })}
            options={[{ value: "pass", label: "通过" }, { value: "review", label: "复核" }, { value: "reject", label: "拒绝" }, { value: "freeze", label: "冻结" }, { value: "report", label: "报送" }]}
          />
          <Select
            placeholder="全部等级" allowClear style={{ width: 120 }}
            value={filters.risk_level || undefined}
            onChange={(v) => setFilters({ ...filters, risk_level: v || "" })}
            options={[{ value: "低", label: "低" }, { value: "中", label: "中" }, { value: "高", label: "高" }, { value: "极高", label: "极高" }]}
          />
          <Select
            placeholder="全部事件" allowClear style={{ width: 130 }}
            value={filters.event_type || undefined}
            onChange={(v) => setFilters({ ...filters, event_type: v || "" })}
            options={[{ value: "transfer", label: "转账" }, { value: "loan_apply", label: "贷款申请" }, { value: "card_txn", label: "卡片交易" }, { value: "repay", label: "还款" }, { value: "login", label: "登录" }]}
          />
          <Input placeholder="用户ID" style={{ width: 160 }} value={filters.user_id} onChange={(e) => setFilters({ ...filters, user_id: e.target.value })} />
          <Select
            value={pageSize} style={{ width: 110 }}
            onChange={(v) => { setPageSize(v); load(1, v); }}
            options={[{ value: 10, label: "10 条" }, { value: 20, label: "20 条" }, { value: 50, label: "50 条" }]}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={onSearch}>查询</Button>
        </Space>
        <div className="text-[13px] text-[#8c8c8c] mb-3">共 {total} 条，当前 {pageSize} 条/页</div>
        <Table
          loading={loading}
          rowKey="assessment_id"
          dataSource={items}
          columns={columns}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: false,
            onChange: (p) => load(p, pageSize),
          }}
          scroll={{ x: 1100 }}
          size="small"
        />
      </Card>

      <Modal title="评估详情" open={!!detail} onCancel={() => setDetail(null)} footer={null} width={720}>
        {detailLoading ? <Spin /> : detail ? (
          <div className="space-y-4">
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="评估ID">{detail.assessment_id}</Descriptions.Item>
              <Descriptions.Item label="用户">{detail.user_id}</Descriptions.Item>
              <Descriptions.Item label="事件">{EVENT_LABEL[detail.event_type] || detail.event_type}</Descriptions.Item>
              <Descriptions.Item label="业务单号">{detail.event_source_id}</Descriptions.Item>
              <Descriptions.Item label="评分">{detail.final_score}</Descriptions.Item>
              <Descriptions.Item label="等级"><Tag color={LEVEL_COLOR[detail.risk_level]}>{detail.risk_level}</Tag></Descriptions.Item>
              <Descriptions.Item label="决策">{(() => { const dm = DECISION_META[detail.decision]; return <Tag color={dm?.color}>{dm?.label}</Tag>; })()}</Descriptions.Item>
              <Descriptions.Item label="ML分">{detail.ml_score?.toFixed(3) ?? "-"}</Descriptions.Item>
            </Descriptions>
            <div>
              <div className="text-[13px] font-medium mb-2">命中规则</div>
              <div className="flex flex-wrap gap-2">
                {detail.triggered_rules?.map((r: any, i: number) => (
                  <Tag key={i} color={DECISION_META[r.action]?.color}>{r.rule_name}</Tag>
                )) || <span className="text-[#8c8c8c]">无</span>}
              </div>
            </div>
            {detail.event_data && (
              <div>
                <div className="text-[13px] font-medium mb-2">事件数据</div>
                <pre className="bg-[#f5f5f5] p-3 rounded text-[12px] overflow-auto">{typeof detail.event_data === "string" ? detail.event_data : JSON.stringify(detail.event_data, null, 2)}</pre>
              </div>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

// ============================================================
// 模型评估
// ============================================================
function ModelEvalView() {
  const [evalData, setEvalData] = useState<ModelEval | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.modelEval().then(setEvalData).catch((e) => setErr(e.message));
  }, []);

  if (err) return <Alert type="error" showIcon message={err} />;
  if (!evalData) return <Card loading />;
  if (!evalData.base && !evalData.hard) return <Empty description="暂无评估记录，请先运行训练" />;
  const m = evalData.hard || evalData.base;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {["train_auc", "val_auc", "val_f1"].map((k) => (
          <Card key={k} size="small" title={k.toUpperCase()}>
            <div className="text-3xl font-semibold text-[#1677FF]">{(m as any)[k].toFixed(3)}</div>
            <div className="text-[12px] text-[#8c8c8c]">runs: {(m as any).n_runs}</div>
          </Card>
        ))}
      </div>
      <Card title="特征重要性 Top" size="small">
        <div className="space-y-2">
          {evalData.feature_importance.map((f, idx) => {
            const max = evalData!.feature_importance[0].gain || 1;
            return (
              <div key={idx} className="flex items-center gap-3">
                <div className="w-44 text-[12px] font-mono">{f.feature}</div>
                <div className="flex-1 h-4 bg-[#f0f0f0] rounded">
                  <div className="h-full bg-[#722ED1] rounded" style={{ width: `${(f.gain / max) * 100}%` }} />
                </div>
                <div className="w-16 text-right text-[12px]">{f.gain.toFixed(3)}</div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

// ============================================================
// 特征工程
// ============================================================
function FeatureView() {
  const [features, setFeatures] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.features().then(setFeatures).catch((e) => setErr(e.message));
  }, []);

  if (err) return <Alert type="error" showIcon message={err} />;
  if (!features) return <Card loading />;
  return (
    <div className="space-y-4">
      {Object.entries(features.families).map(([fid, fam]: any) => (
        <Card key={fid} size="small" title={fam.name}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {fam.features.map((f: any) => (
              <div key={f.key} className="border rounded p-3">
                <div className="flex justify-between items-center">
                  <span className="font-medium text-[13px]">{f.name}</span>
                  <Tag>{f.range}</Tag>
                </div>
                <div className="text-[11px] text-[#bfbfbf] font-mono mb-1">{f.key}</div>
                <div className="text-[12px] text-[#8c8c8c]">{f.desc}</div>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
