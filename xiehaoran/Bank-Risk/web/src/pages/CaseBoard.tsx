import { useEffect, useState } from "react";
import { Card, Table, Tag, Statistic, Row, Col, Alert, Modal, Descriptions, Select, Input, Button, Space, App } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { api, CaseItem, CaseDetail, CaseStatistics, DECISION_META } from "../api";

const STATUS_META: Record<string, { color: string; label: string }> = {
  "待审核": { color: "orange", label: "待审核" },
  "审核中": { color: "blue", label: "审核中" },
  "已通过": { color: "green", label: "已通过" },
  "已拒绝": { color: "red", label: "已拒绝" },
  "已关闭": { color: "default", label: "已关闭" },
};

const FILTER_OPTIONS = [
  { value: "active_only", label: "仅待办（待审核 + 审核中）" },
  { value: "all", label: "全部状态" },
  { value: "待审核", label: "待审核" },
  { value: "审核中", label: "审核中" },
  { value: "已通过", label: "已通过" },
  { value: "已拒绝", label: "已拒绝" },
  { value: "已关闭", label: "已关闭" },
];

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

function formatTime(v: string | null | undefined): string {
  if (!v) return "-";
  const d = new Date(v);
  if (isNaN(d.getTime())) return "-";
  const p = (n: number) => String(n);
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default function CaseBoard() {
  const { message } = App.useApp();
  const [items, setItems] = useState<CaseItem[]>([]);
  const [stats, setStats] = useState<CaseStatistics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [reviewForm, setReviewForm] = useState({ decision: "已通过", reviewer: "", review_comment: "", add_to_blacklist: false });
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  const load = (currentFilter = filter, currentPage = page, currentPageSize = pageSize) => {
    setLoading(true);
    const params: { status?: string; active_only?: boolean; page: number; page_size: number } = {
      page: currentPage,
      page_size: currentPageSize,
    };
    if (currentFilter === "active_only") {
      params.active_only = true;
    } else if (currentFilter !== "all") {
      params.status = currentFilter;
    }
    Promise.all([api.cases(params), api.caseStatistics()])
      .then(([c, s]) => { setItems(c.items); setStats(s); setTotal(c.total); setErr(null); })
      .catch((e) => setErr(e.message)).finally(() => setLoading(false));
  };
  useEffect(() => { load("all", 1, 20); }, []);

  const openDetail = async (id: string) => {
    try { setDetail(await api.caseDetail(id)); } catch (e: any) { message.error(e.message); }
  };

  const submitReview = async () => {
    if (!detail) return;
    try {
      await api.reviewCase(detail.case_id, reviewForm);
      message.success("审核已提交"); setDetail(null); load(filter, 1, pageSize);
    } catch (e: any) { message.error(e.message); }
  };

  const recheck = (r: CaseItem) => {
    window.location.hash = `#/risk?event_type=${encodeURIComponent(r.event_type ?? "")}&source_id=${encodeURIComponent(r.source_id ?? "")}&user_id=${encodeURIComponent(r.user_id ?? "")}`;
  };

  if (err) return <Alert type="error" showIcon message={err} />;

  const columns = [
    {
      title: "案件ID", dataIndex: "case_id",
      render: (v: string) => <span className="font-mono text-[12px]" title={v} style={{ display: "inline-block", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", verticalAlign: "bottom" }}>{v}</span>,
    },
    { title: "用户ID", dataIndex: "user_id" },
    { title: "分类", dataIndex: "case_category", render: (v: string | null) => v || "-" },
    { title: "评分", dataIndex: "final_score", align: "center" as const, render: (v: number | null) => v ?? "-" },
    { title: "等级", dataIndex: "risk_level", render: (v: string | null) => v ? <Tag color="volcano">{v}</Tag> : "-" },
    { title: "状态", dataIndex: "case_status", render: (v: string) => { const m = STATUS_META[v]; return <Tag color={m?.color}>{m?.label}</Tag>; } },
    { title: "创建时间", dataIndex: "create_time", render: (v: string | null) => formatTime(v) },
    {
      title: "操作", key: "action", fixed: "right" as const, width: 160,
      render: (_: unknown, r: CaseItem) => (
        <Space size="small" direction="vertical" style={{ display: "flex" }}>
          <Button type="link" size="small" style={{ padding: 0 }}
            onClick={(e) => { e.stopPropagation(); openDetail(r.case_id); }}>详情</Button>
          <Button size="small" icon={<ReloadOutlined />} style={{ color: "#FAAD14", borderColor: "#FAAD14" }}
            onClick={(e) => { e.stopPropagation(); recheck(r); }}>重做检查</Button>
        </Space>
      ),
    },
  ];

  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  return (
    <div className="space-y-5">
      <Row gutter={16}>
        {stats && [
          { t: "总计", v: stats.total, c: "#1677FF" },
          { t: "待审核", v: stats.pending, c: "#FA8C16" },
          { t: "审核中", v: stats.reviewing, c: "#1677FF" },
          { t: "已通过", v: stats.approved, c: "#52C41A" },
          { t: "已拒绝", v: stats.rejected, c: "#FF4D4F" },
          { t: "已关闭", v: stats.closed, c: "#8C8C8C" },
        ].map((s) => (
          <Col xs={12} lg={4} key={s.t}>
            <Card size="small"><Statistic title={s.t} value={s.v} valueStyle={{ color: s.c }} /></Card>
          </Col>
        ))}
      </Row>

      <Card size="small" title="案件列表">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
          <div className="flex items-center gap-3 flex-wrap">
            <Select
              value={filter}
              style={{ width: 200 }}
              options={FILTER_OPTIONS}
              onChange={(v) => { setFilter(v); setPage(1); load(v, 1, pageSize); }}
            />
            <Select
              value={pageSize}
              style={{ width: 110 }}
              options={PAGE_SIZE_OPTIONS.map((n) => ({ value: n, label: `每页 ${n} 条` }))}
              onChange={(ps) => { setPageSize(ps); setPage(1); load(filter, 1, ps); }}
            />
          </div>
          <span className="text-[13px] text-gray-500">共 {total} 条，当前 {rangeStart}-{rangeEnd} 条/页</span>
        </div>
        <Table
          loading={loading}
          rowKey="case_id"
          dataSource={items}
          columns={columns}
          scroll={{ x: 900 }}
          onRow={(r) => ({ onClick: () => openDetail(r.case_id), style: { cursor: "pointer" } })}
          pagination={{
            current: page,
            pageSize,
            total,
            position: ["bottomCenter"],
            showSizeChanger: false,
            showQuickJumper: true,
            showTotal: undefined,
            pageSizeOptions: PAGE_SIZE_OPTIONS,
            onChange: (p, ps) => {
              setPage(p);
              if (ps !== pageSize) { setPageSize(ps); load(filter, 1, ps); }
              else load(filter, p, ps);
            },
          }}
        />
      </Card>

      <Modal
        title="案件详情"
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={[
          <Button key="cancel" onClick={() => setDetail(null)}>关闭</Button>,
          <Button key="ok" type="primary" onClick={submitReview}>提交审核</Button>,
        ]}
        width={960}
      >
        {detail && (
          <div className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <div className="text-sm font-medium mb-3">基本信息</div>
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="案件ID">{detail.case_id}</Descriptions.Item>
                  <Descriptions.Item label="用户ID">{detail.user_id}</Descriptions.Item>
                  <Descriptions.Item label="评分"><span className="font-semibold">{detail.final_score}</span></Descriptions.Item>
                  <Descriptions.Item label="等级">
                    {detail.risk_level && (
                      <Tag color={detail.risk_level === "高" || detail.risk_level === "极高" ? "red" : detail.risk_level === "中" ? "orange" : "green"}>
                        {detail.risk_level}
                      </Tag>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="决策">
                    {detail.decision && (() => { const dm = DECISION_META[detail.decision]; return <Tag color={dm?.color}>{dm?.label}</Tag>; })()}
                  </Descriptions.Item>
                  <Descriptions.Item label="状态">
                    {detail.case_status && (() => { const s = STATUS_META[detail.case_status]; return <Tag color={s?.color}>{s?.label}</Tag>; })()}
                  </Descriptions.Item>
                  <Descriptions.Item label="分类">{detail.case_category}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">{detail.create_time ? new Date(detail.create_time).toLocaleString() : "-"}</Descriptions.Item>
                  <Descriptions.Item label="审核人">{detail.reviewer || "-"}</Descriptions.Item>
                  <Descriptions.Item label="审核意见">{detail.review_comment || "-"}</Descriptions.Item>
                </Descriptions>
              </div>

              <div className="space-y-5">
                <div>
                  <div className="text-sm font-medium mb-3">命中规则</div>
                  <Table
                    size="small"
                    bordered
                    pagination={false}
                    dataSource={detail.triggered_rules.map((r, i) => ({ ...r, key: i }))}
                    columns={[
                      { title: "规则", dataIndex: "rule_name" },
                      { title: "等级", dataIndex: "risk_level", width: 70, render: (v: string) => <Tag color={v === "高" || v === "极高" ? "red" : v === "中" ? "orange" : "green"}>{v}</Tag> },
                      { title: "分值", dataIndex: "risk_score", width: 70 },
                    ]}
                  />
                </div>
                <div>
                  <div className="text-sm font-medium mb-3">用户画像</div>
                  <Descriptions size="small" column={1} bordered>
                    <Descriptions.Item label="风险评分">{detail.user_profile?.risk_score ?? "-"}</Descriptions.Item>
                    <Descriptions.Item label="总订单">{detail.user_profile?.total_orders ?? "-"}</Descriptions.Item>
                    <Descriptions.Item label="退款率">{detail.user_profile?.refund_rate !== undefined ? `${(detail.user_profile.refund_rate * 100).toFixed(1)}%` : "-"}</Descriptions.Item>
                    <Descriptions.Item label="投诉次数">{detail.user_profile?.complaint_count ?? "-"}</Descriptions.Item>
                  </Descriptions>
                </div>
              </div>
            </div>

            <div className="bg-gray-50 p-4 rounded-md">
              <div className="text-sm font-medium mb-3">ML 评分 (XGBoost)</div>
              <div className="space-y-2 text-sm">
                {detail.ml_score !== null && detail.ml_score !== undefined && (
                  <div>P(拒绝): <span className="font-semibold">{(detail.ml_score * 100).toFixed(2)}%</span> ({detail.ml_score.toFixed(4)})</div>
                )}
                <div>风险分 (sigmoid 校准): <span className="font-semibold">{detail.ml_score !== null && detail.ml_score !== undefined ? Math.round(detail.ml_score * 100) : "-"}</span> / 100</div>
                <div>
                  ML 决策: {detail.ml_decision && (() => { const dm = DECISION_META[detail.ml_decision]; return <Tag color={dm?.color}>{dm?.label}</Tag>; })()}
                </div>
              </div>
            </div>

            <div className="border-t pt-4 space-y-3">
              <div className="text-sm font-medium">审核处置</div>
              <Select
                className="w-full" value={reviewForm.decision}
                onChange={(v) => setReviewForm({ ...reviewForm, decision: v })}
                options={[
                  { value: "已通过", label: "已通过 (放行)" },
                  { value: "已拒绝", label: "已拒绝" },
                  { value: "已关闭", label: "已关闭" },
                ]}
              />
              <Input placeholder="审核人" value={reviewForm.reviewer}
                onChange={(e) => setReviewForm({ ...reviewForm, reviewer: e.target.value })} />
              <Input.TextArea rows={2} placeholder="审核意见"
                value={reviewForm.review_comment}
                onChange={(e) => setReviewForm({ ...reviewForm, review_comment: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={reviewForm.add_to_blacklist}
                  onChange={(e) => setReviewForm({ ...reviewForm, add_to_blacklist: e.target.checked })} />
                加入黑名单
              </label>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
