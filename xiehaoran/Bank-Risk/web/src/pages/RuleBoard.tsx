import { useEffect, useState } from "react";
import { Card, Tag, Alert, Empty, Table, Switch, Button, Space, Modal, Form, Input, Select, InputNumber, App } from "antd";
import { EditOutlined, DeleteOutlined } from "@ant-design/icons";
import { api, DECISION_META, RuleMeta, RULE_CATEGORY_OPTIONS, RISK_LEVEL_OPTIONS } from "../api";

const EVENT_OPTS = [
  { value: "通用", label: "通用" },
  { value: "transfer", label: "转账" },
  { value: "loan_apply", label: "贷款申请" },
  { value: "card_txn", label: "卡片交易" },
  { value: "repay", label: "还款" },
  { value: "login", label: "登录" },
];
const ACTION_OPTS = [
  { value: "pass", label: "通过" },
  { value: "review", label: "复核" },
  { value: "reject", label: "拒绝" },
  { value: "freeze", label: "冻结" },
  { value: "report", label: "报送" },
];

export default function RuleBoard() {
  const { message } = App.useApp();
  const [data, setData] = useState<RuleMeta[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RuleMeta | null>(null);
  const [form] = Form.useForm();
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<"rule_id" | "risk_score" | "priority" | "risk_level" | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc" | undefined>(undefined);

  const load = () => {
    setLoading(true);
    api.rules(category, page, pageSize, sortBy, sortOrder).then((r) => {
      setData(r.items); setTotal(r.total); setErr(null);
    }).catch((e) => setErr(e.message)).finally(() => setLoading(false));
  };
  useEffect(load, [category, page, pageSize, sortBy, sortOrder]);

  // 处理表头排序点击：受控排序，切换排序时回到第 1 页
  const handleTableChange = (
    _pagination: any,
    _filters: any,
    sorter: any,
  ) => {
    const field = sorter.field as "rule_id" | "risk_score" | "priority" | "risk_level" | undefined;
    const order = sorter.order === "ascend" ? "asc" : sorter.order === "descend" ? "desc" : undefined;
    setSortBy(field);
    setSortOrder(order);
    setPage(1);
  };

  const toggle = async (r: RuleMeta) => {
    try {
      await api.toggleRule(r.rule_id);
      message.success(`${r.rule_name} 已${r.is_enabled ? "停用" : "启用"}`);
      load();
    } catch (e: any) { message.error(e.message); }
  };

  const del = (r: RuleMeta) => {
    Modal.confirm({
      title: "确认删除规则",
      content: `确定要删除规则「${r.rule_name}」(${r.rule_id}) 吗？此操作不可恢复。`,
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try { await api.deleteRule(r.rule_id); message.success("已删除"); load(); }
        catch (e: any) { message.error(e.message); }
      },
    });
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ event_type: "通用", risk_level: "中", action: "review", risk_score: 60, priority: 0, rule_condition: "" });
    setModalOpen(true);
  };

  const openEdit = (r: RuleMeta) => {
    setEditing(r);
    form.setFieldsValue({
      rule_id: r.rule_id, rule_name: r.rule_name, rule_category: r.rule_category,
      event_type: r.event_type, risk_level: r.risk_level, risk_score: r.risk_score,
      action: r.action, priority: r.priority, description: r.description,
      rule_condition: r.rule_condition ? JSON.stringify(r.rule_condition, null, 2) : "",
    });
    setModalOpen(true);
  };

  const handleClose = () => {
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
  };

  const save = async (vals: any) => {
    const payload = {
      rule_id: vals.rule_id, rule_name: vals.rule_name, rule_category: vals.rule_category,
      event_type: vals.event_type || "通用", risk_level: vals.risk_level, risk_score: vals.risk_score,
      action: vals.action, rule_condition: vals.rule_condition ? JSON.parse(vals.rule_condition) : {},
      description: vals.description, priority: vals.priority ?? 0,
    };
    try {
      if (editing) {
        await api.updateRule(editing.rule_id, payload);
        message.success("规则已更新");
      } else {
        await api.createRule(payload);
        message.success("规则已创建");
      }
      handleClose(); load();
    } catch (e: any) { message.error(e.message); }
  };

  const categoryColor = (v: string) => {
    const map: Record<string, string> = {
      订单欺诈: "blue",
      支付风险: "green",
      账户风险: "purple",
      信贷风险: "gold",
      反洗钱: "red",
      设备风险: "cyan",
      登录风险: "orange",
      售后滥用: "volcano",
      地址风险: "geekblue",
      物流风险: "lime",
    };
    return map[v] || "blue";
  };

  if (err) return <Alert type="error" showIcon message={err} />;

  const PAGE_SIZE_OPTS = [10, 20, 50, 100];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <Space size="middle">
          <Select
            style={{ width: 130 }}
            value={category ?? ""}
            onChange={(v) => { setCategory(v || undefined); setPage(1); }}
            options={[{ value: "", label: "全部分类" }, ...RULE_CATEGORY_OPTIONS]}
          />
          <Space size="small">
            <span className="text-sm text-[#666]">每页</span>
            <Select
              value={pageSize}
              style={{ width: 80 }}
              onChange={(v) => { setPageSize(v); setPage(1); }}
              options={PAGE_SIZE_OPTS.map((n) => ({ value: n, label: `${n} 条` }))}
            />
            <span className="text-sm text-[#666]">条</span>
          </Space>
          <span className="text-sm text-[#999]">共 {total} 条，当前 {Math.min(total, data.length)} 条/页</span>
        </Space>
        <Button type="primary" onClick={openCreate}>新建规则</Button>
      </div>

      <Card size="small">
        <Table
          loading={loading}
          rowKey="rule_id"
          dataSource={data}
          onChange={handleTableChange}
          pagination={{
            current: page,
            pageSize,
            total,
            onChange: (p) => { setPage(p); },
            position: ["bottomCenter"],
          }}
          columns={[
            { title: "规则ID", dataIndex: "rule_id", width: 90, sorter: true, sortOrder: sortBy === "rule_id" ? (sortOrder === "asc" ? "ascend" : "descend") : null, render: (v) => <span className="text-[#eb2f96] font-mono text-[13px]">{v}</span> },
            { title: "规则名", dataIndex: "rule_name", render: (v) => <span className="font-medium">{v}</span> },
            { title: "分类", dataIndex: "rule_category", width: 100, render: (v) => <Tag color={categoryColor(v)}>{v}</Tag> },
            { title: "事件类型", dataIndex: "event_type", width: 90, render: (v) => <Tag>{v}</Tag> },
            { title: "等级", dataIndex: "risk_level", width: 80, sorter: true, sortOrder: sortBy === "risk_level" ? (sortOrder === "asc" ? "ascend" : "descend") : null, render: (v) => <Tag color={v === "极高" ? "red" : v === "高" ? "volcano" : "default"}>{v}</Tag> },
            { title: "分值", dataIndex: "risk_score", align: "center" as const, width: 70, sorter: true, sortOrder: sortBy === "risk_score" ? (sortOrder === "asc" ? "ascend" : "descend") : null },
            { title: "动作", dataIndex: "action", width: 90, render: (v) => { const dm = DECISION_META[v]; return <Tag color={dm?.color}>{dm?.label}</Tag>; } },
            { title: "优先级", dataIndex: "priority", align: "center" as const, width: 80, sorter: true, sortOrder: sortBy === "priority" ? (sortOrder === "asc" ? "ascend" : "descend") : null },
            { title: "状态", dataIndex: "is_enabled", align: "center" as const, width: 70, render: (v, r) => <Switch size="small" checked={v} onChange={() => toggle(r)} /> },
            { title: "操作", align: "center" as const, width: 100, render: (_, r) => (
              <Space size="small">
                <Button type="link" size="small" icon={<EditOutlined />} style={{ color: "#1890ff" }} onClick={() => openEdit(r)} />
                <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => del(r)} />
              </Space>
            )},
          ]}
        />
      </Card>

      <Modal title={editing ? "编辑规则" : "新建规则"} open={modalOpen} onCancel={handleClose} onOk={() => form.submit()} okText={editing ? "保存" : "创建"} width={680}>
        <Form form={form} layout="vertical" onFinish={save} initialValues={{ event_type: "通用", risk_level: "中", action: "review", risk_score: 60, priority: 0 }}>
          <div className="grid grid-cols-3 gap-3">
            <Form.Item name="rule_id" label="规则ID" rules={[{ required: true }]}>
              <Input placeholder="R009" disabled={!!editing} />
            </Form.Item>
            <Form.Item name="rule_name" label="规则名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="rule_category" label="分类" rules={[{ required: true }]}>
              <Select options={RULE_CATEGORY_OPTIONS} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-4 gap-3">
            <Form.Item name="event_type" label="事件类型">
              <Select options={EVENT_OPTS} />
            </Form.Item>
            <Form.Item name="risk_level" label="风险等级">
              <Select options={RISK_LEVEL_OPTIONS} />
            </Form.Item>
            <Form.Item name="risk_score" label="分值 (0-100)">
              <InputNumber min={0} max={100} className="w-full" />
            </Form.Item>
            <Form.Item name="action" label="动作">
              <Select options={ACTION_OPTS} />
            </Form.Item>
          </div>
          <Form.Item name="rule_condition" label="条件表达式 (JSON)" extra={`如 {"field":"large_amt_flag","op":">=","value":1}`}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <div className="grid grid-cols-4 gap-3">
            <Form.Item name="priority" label="优先级">
              <InputNumber min={0} max={1000} className="w-full" />
            </Form.Item>
            <div className="col-span-3">
              <Form.Item name="description" label="描述">
                <Input />
              </Form.Item>
            </div>
          </div>
        </Form>
      </Modal>
    </div>
  );
}
