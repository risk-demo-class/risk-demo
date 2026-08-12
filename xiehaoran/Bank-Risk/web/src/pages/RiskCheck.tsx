import { useEffect, useState } from "react";
import {
  Card, Form, Input, InputNumber, Select, Switch, Button, Tabs, Tag, Timeline,
  Collapse, Alert, App, Descriptions, Divider,
} from "antd";
import { SendOutlined, ReloadOutlined } from "@ant-design/icons";
import { api, DECISION_META, EVENT_OPTIONS, RiskCheckResponse } from "../api";

// 各事件类型的演示样例 (对齐 11 维特征字段语义)
const SAMPLES: Record<string, any> = {
  transfer: { source_id: "T300011", user_id: "C200001", amount: 260000, counterparty_acct: "C200099", counterparty_acct_cnt: 12, txn_time: "2026-05-03 03:20:00", geo_deviation: true, ip_risk_score: 1 },
  loan_apply: { source_id: "T300012", user_id: "C200001", amount: 50000, credit_query_cnt: 12, apply_org_cnt: 6 },
  card_txn: { source_id: "T300013", user_id: "C200001", amount: 88000, counterparty_acct: "C200088", geo_deviation: true, txn_time: "2026-05-03 02:00:00" },
  repay: { source_id: "T300014", user_id: "C200001", amount: 3000 },
  login: { source_id: "T300015", user_id: "C200001", login_fail_5m: 8, geo_deviation: true, txn_time: "2026-05-03 04:30:00" },
};

export default function RiskCheck() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [eventType, setEventType] = useState("transfer");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RiskCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSample = (type: string) => {
    setEventType(type);
    form.setFieldsValue({ event_type: type, ...SAMPLES[type] });
  };

  useEffect(() => {
    const qs = window.location.hash.split("?")[1];
    if (!qs) return;
    const p = new URLSearchParams(qs);
    const eventType = p.get("event_type");
    const sourceId = p.get("source_id");
    const userId = p.get("user_id");
    const valid = EVENT_OPTIONS.some((o) => o.value === eventType);
    const vals: Record<string, string> = {};
    if (valid && eventType) { vals.event_type = eventType; setEventType(eventType); }
    if (sourceId) vals.source_id = sourceId;
    if (userId) vals.user_id = userId;
    if (Object.keys(vals).length) form.setFieldsValue(vals);
  }, []);

  const onFinish = async (vals: any) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.riskCheck({
        event_type: vals.event_type,
        source_id: String(vals.source_id),
        user_id: String(vals.user_id),
        event_data: {
          amount: vals.amount,
          counterparty_acct: vals.counterparty_acct,
          counterparty_acct_cnt: vals.counterparty_acct_cnt,
          credit_query_cnt: vals.credit_query_cnt,
          apply_org_cnt: vals.apply_org_cnt,
          login_fail_5m: vals.login_fail_5m,
          txn_time: vals.txn_time,
          geo_deviation: vals.geo_deviation ? 1 : 0,
          ip_risk_score: vals.ip_risk_score ? 1 : 0,
        },
      });
      setResult(res);
      message.success("决策完成");
    } catch (e: any) {
      setError(e.message);
      setResult(null);
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const dm = result ? DECISION_META[result.decision] : null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
      <Card
        title="事件录入"
        className="lg:col-span-3"
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={() => loadSample(eventType)}>
            填充样例
          </Button>
        }
      >
        <Form form={form} layout="vertical" initialValues={{ event_type: "transfer", ...SAMPLES.transfer }} onFinish={onFinish}>
          <Form.Item name="event_type" label="事件类型" rules={[{ required: true }]}>
            <Tabs
              items={EVENT_OPTIONS.map((o) => ({ key: o.value, label: o.label }))}
              activeKey={eventType}
              onChange={(k) => loadSample(k)}
            />
          </Form.Item>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="source_id" label="业务单号" rules={[{ required: true }]}>
              <Input placeholder="T300011" />
            </Form.Item>
            <Form.Item name="user_id" label="客户号" rules={[{ required: true }]}>
              <Input placeholder="C200001" />
            </Form.Item>
            <Form.Item name="amount" label="金额 (元)">
              <InputNumber className="w-full" min={0} step={1000} />
            </Form.Item>
            <Form.Item name="counterparty_acct" label="交易对手账户">
              <Input placeholder="C200099" />
            </Form.Item>
            <Form.Item name="counterparty_acct_cnt" label="近1h对手数">
              <InputNumber className="w-full" min={0} />
            </Form.Item>
            <Form.Item name="credit_query_cnt" label="30天征信查询">
              <InputNumber className="w-full" min={0} />
            </Form.Item>
            <Form.Item name="apply_org_cnt" label="借贷平台数">
              <InputNumber className="w-full" min={0} />
            </Form.Item>
            <Form.Item name="login_fail_5m" label="5分钟登录失败">
              <InputNumber className="w-full" min={0} />
            </Form.Item>
            <Form.Item name="txn_time" label="交易时间">
              <Input placeholder="2026-05-03 03:20:00" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="geo_deviation" label="地理/IP 突变" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="ip_risk_score" label="IP 风险" valuePropName="checked">
              <Switch />
            </Form.Item>
          </div>
          <Button type="primary" htmlType="submit" loading={loading} icon={<SendOutlined />} block>
            发起决策
          </Button>
        </Form>
      </Card>

      <div className="lg:col-span-2 space-y-4">
        {error && <Alert type="error" showIcon message="决策失败" description={error} />}
        {!result && !error && (
          <Card className="text-center text-[#8c8c8c] py-16">填写事件后点击「发起决策」查看结果</Card>
        )}
        {result && dm && (
          <>
            <Card className="text-center">
              <div className="text-[13px] text-[#8c8c8c] mb-1">决策结果</div>
              <div
                className="inline-flex items-center justify-center rounded-xl px-8 py-4 text-2xl font-semibold"
                style={{ background: dm.bg, color: dm.color }}
              >
                {dm.label.toUpperCase()}
              </div>
              <div className="mt-2 text-[12px] text-[#8c8c8c]">
                评分 {result.final_score} · 等级 {result.risk_level} · {result.user_id}
              </div>
              {result.ml_score != null && (
                <div className="mt-1 text-[12px] text-[#8c8c8c]">
                  ML分 {result.ml_score.toFixed(3)} · {result.ml_decision}
                </div>
              )}
              {result.blocked_by && (
                <Tag color="purple" className="mt-2">撞黑: {result.blocked_by}</Tag>
              )}
            </Card>

            <Card title="命中规则" size="small">
              {result.triggered_rules.length === 0 ? (
                <div className="text-[#52C41A]">无规则命中, 正常放行</div>
              ) : (
                <Timeline
                  items={result.triggered_rules.map((r) => ({
                    color: DECISION_META[r.action]?.color,
                    children: (
                      <div>
                        <Tag color={DECISION_META[r.action]?.color}>{r.action}</Tag>
                        <span className="text-[13px] font-medium">{r.rule_name}</span>
                        <div className="text-[12px] text-[#8c8c8c]">{r.description}</div>
                      </div>
                    ),
                  }))}
                />
              )}
            </Card>

            <Card title="11 维特征向量" size="small">
              <Collapse
                items={[{
                  key: "f",
                  label: "展开特征向量",
                  children: (
                    <Descriptions column={2} size="small">
                      {Object.entries(result.features).map(([k, v]) => (
                        <Descriptions.Item key={k} label={k}>
                          {typeof v === "number" ? v.toFixed(3) : v}
                        </Descriptions.Item>
                      ))}
                    </Descriptions>
                  ),
                }]}
              />
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
