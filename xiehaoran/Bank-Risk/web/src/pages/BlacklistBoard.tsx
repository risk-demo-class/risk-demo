import { useEffect, useState } from "react";
import { Card, Table, Tag, Alert, Button, Modal, Form, Select, Input, Statistic, Space, App } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { api, BlacklistItem, BLACKLIST_TYPE_OPTIONS } from "../api";

const TYPE_META: Record<string, { label: string; color: string }> = {
  account: { label: "账户", color: "blue" },
  device: { label: "设备", color: "cyan" },
  ip: { label: "IP", color: "orange" },
  phone: { label: "手机号", color: "red" },
  id_card: { label: "证件号", color: "purple" },
  merchant: { label: "商户", color: "geekblue" },
  beneficiary: { label: "受益人", color: "magenta" },
};

export default function BlacklistBoard() {
  const { message } = App.useApp();
  const [items, setItems] = useState<BlacklistItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<{ total: number; account: number; ip: number; phone: number } | null>(null);
  const [selectedType, setSelectedType] = useState<string>("");
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async (p = page, ps = pageSize, type = selectedType) => {
    setLoading(true);
    try {
      const [listRes, statRes] = await Promise.all([
        api.blacklist({ page: p, page_size: ps, blacklist_type: type || undefined }),
        api.blacklistStatistics(),
      ]);
      setItems(listRes.items);
      setTotal(listRes.total);
      setPage(listRes.page);
      setPageSize(listRes.page_size);
      setStats(statRes);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(1, 20, ""); }, []);

  const add = async (vals: any) => {
    try {
      await api.addBlacklist(vals);
      message.success("已加入黑名单");
      setModalOpen(false);
      form.resetFields();
      load(1, pageSize, "");
    } catch (e: any) { message.error(e.message); }
  };

  const del = async (id: number) => {
    try {
      await api.deleteBlacklist(id);
      message.success("已移除");
      load(page, pageSize, selectedType);
    } catch (e: any) { message.error(e.message); }
  };

  const formatTime = (v: string | null) => {
    if (!v) return "-";
    const d = new Date(v);
    return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };

  const statCards = [
    { title: "账户黑名单", value: stats?.account ?? 0, color: "#1677FF" },
    { title: "IP黑名单", value: stats?.ip ?? 0, color: "#FA8C16" },
    { title: "手机号黑名单", value: stats?.phone ?? 0, color: "#FF4D4F" },
    { title: "总数", value: stats?.total ?? 0, color: "#262626" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-[18px] font-semibold">黑名单管理</span>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新增黑名单</Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s) => (
          <Card key={s.title} size="small">
            <Statistic title={s.title} value={s.value} valueStyle={{ color: s.color, fontWeight: 600 }} />
          </Card>
        ))}
      </div>

      <Card size="small">
        <Space wrap className="mb-4">
          <Select
            placeholder="全部类型" allowClear style={{ width: 130 }}
            value={selectedType || undefined}
            onChange={(v) => { setSelectedType(v || ""); load(1, pageSize, v || ""); }}
            options={[{ value: "", label: "全部类型" }, ...BLACKLIST_TYPE_OPTIONS]}
          />
          <Select
            value={pageSize} style={{ width: 110 }}
            onChange={(v) => { setPageSize(v); load(1, v, selectedType); }}
            options={[{ value: 10, label: "10 条" }, { value: 20, label: "20 条" }, { value: 50, label: "50 条" }]}
          />
        </Space>
        <div className="text-[13px] text-[#8c8c8c] mb-3">共 {total} 条，当前 {pageSize} 条/页</div>
        <Table
          loading={loading}
          rowKey="blacklist_id"
          dataSource={items}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: false,
            onChange: (p) => load(p, pageSize, selectedType),
          }}
          locale={{ emptyText: "暂无黑名单" }}
          size="small"
          columns={[
            { title: "ID", dataIndex: "blacklist_id", width: 80, align: "center" as const },
            { title: "类型", dataIndex: "blacklist_type", width: 110, render: (v) => { const m = TYPE_META[v]; return <Tag color={m?.color}>{m?.label || v}</Tag>; } },
            { title: "值", dataIndex: "blacklist_value", render: (v) => <span className="font-mono text-[13px]">{v}</span> },
            { title: "原因", dataIndex: "reason" },
            { title: "过期时间", dataIndex: "expire_time", width: 150, render: (v) => <span className="text-[12px]">{formatTime(v)}</span> },
            { title: "创建时间", dataIndex: "create_time", width: 150, render: (v) => <span className="text-[12px]">{formatTime(v)}</span> },
            { title: "操作", width: 90, align: "center" as const, render: (_, r) => <Button type="link" danger size="small" icon={<DeleteOutlined />} onClick={() => del(r.blacklist_id)}>移除</Button> },
          ]}
        />
      </Card>

      <Modal title="新增黑名单" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} okText="新增">
        <Form form={form} layout="vertical" initialValues={{ blacklist_type: "account" }}>
          <Form.Item name="blacklist_type" label="维度" rules={[{ required: true }]}>
            <Select options={BLACKLIST_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="blacklist_value" label="黑名单值" rules={[{ required: true }]}>
            <Input placeholder="如 C999999 / 203.0.113.9" />
          </Form.Item>
          <Form.Item name="reason" label="原因"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
