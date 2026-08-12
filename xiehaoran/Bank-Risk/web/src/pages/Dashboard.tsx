import { useEffect, useState } from "react";
import { Card, Statistic, Row, Col, Alert, Empty, Table, Tag } from "antd";
import {
  ArrowUpOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ProfileOutlined,
  PieChartOutlined,
  BarChartOutlined,
} from "@ant-design/icons";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from "recharts";
import { api, DashboardOverview, DECISION_META } from "../api";

const RISK_LEVEL_META: Record<string, { label: string; color: string }> = {
  低: { label: "低风险", color: "#52C41A" },
  中: { label: "中风险", color: "#1677FF" },
  高: { label: "高风险", color: "#FA8C16" },
  极高: { label: "极高风险", color: "#FF4D4F" },
};

export default function Dashboard() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.dashboardOverview().then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return <Alert type="error" showIcon message={err} />;
  if (!data) return <Card loading />;

  const stats = [
    { title: "今日评估", value: data.today_assessments, icon: <ProfileOutlined />, color: "#1677FF" },
    { title: "今日高风险", value: data.today_high_risk, icon: <WarningOutlined />, color: "#FF4D4F" },
    {
      title: "通过率",
      value: data.pass_rate,
      suffix: "%",
      icon: <CheckCircleOutlined />,
      color: "#52C41A",
    },
    { title: "待处理案件", value: data.pending_cases, icon: <ArrowUpOutlined />, color: "#FA8C16" },
  ];

  const trendData = data.trend_7d.map((t) => ({
    date: t.date.slice(5),
    总评估: t.count,
    高风险: t.high_risk_count,
  }));

  const riskPie = data.risk_level_distribution.map((d) => ({
    name: RISK_LEVEL_META[d.level]?.label ?? d.level,
    value: d.count,
    level: d.level,
  }));
  const totalRisk = riskPie.reduce((s, d) => s + d.value, 0);

  const decisionData = data.decision_distribution.map((d) => ({
    name: DECISION_META[d.decision]?.label ?? d.decision,
    value: d.count,
    decision: d.decision,
  }));

  return (
    <div className="space-y-5">
      <Row gutter={16}>
        {stats.map((s) => (
          <Col xs={24} sm={12} lg={6} key={s.title}>
            <Card className="stat-card">
              <Statistic
                title={s.title}
                value={s.value}
                suffix={s.suffix}
                prefix={<span style={{ color: s.color }}>{s.icon}</span>}
                valueStyle={{ color: s.color, fontWeight: 600 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card
            title={
              <span className="flex items-center gap-2 font-medium">
                <BarChartOutlined className="text-[#1677FF]" /> 近7天评估趋势
              </span>
            }
            size="small"
          >
            {trendData.length === 0 ? (
              <Empty description="暂无数据" />
            ) : (
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={trendData} margin={{ top: 16, right: 24, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#595959" }} stroke="#d9d9d9" />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#595959" }} stroke="#d9d9d9" />
                  <ReTooltip
                    contentStyle={{ borderRadius: 8, border: "1px solid #f0f0f0", fontSize: 13 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
                  <Line
                    type="monotone"
                    dataKey="总评估"
                    stroke="#1677FF"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#1677FF" }}
                    activeDot={{ r: 6 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="高风险"
                    stroke="#FF4D4F"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#FF4D4F" }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={
              <span className="flex items-center gap-2 font-medium">
                <PieChartOutlined className="text-[#1677FF]" /> Top 命中规则
              </span>
            }
            size="small"
          >
            {data.top_rules.length === 0 ? (
              <Empty description="暂无命中" />
            ) : (
              <Table
                size="small"
                pagination={false}
                dataSource={data.top_rules}
                rowKey="rule_id"
                columns={[
                  { title: "规则", dataIndex: "rule_name" },
                  {
                    title: "命中次数",
                    dataIndex: "hit_count",
                    align: "right" as const,
                    render: (v: number) => <Tag color="blue">{v}</Tag>,
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card
            title={
              <span className="flex items-center gap-2 font-medium">
                <PieChartOutlined className="text-[#722ED1]" /> 风险等级分布（今日）
              </span>
            }
            size="small"
          >
            {riskPie.length === 0 ? (
              <Empty description="暂无数据" />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={riskPie}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={70}
                    outerRadius={100}
                    paddingAngle={2}
                  >
                    {riskPie.map((d) => (
                      <Cell key={d.level} fill={RISK_LEVEL_META[d.level]?.color ?? "#1677FF"} />
                    ))}
                  </Pie>
                  <ReTooltip
                    formatter={(v: number, n: string) => [`${v} 笔 (${totalRisk ? Math.round((v / totalRisk) * 100) : 0}%)`, n]}
                    contentStyle={{ borderRadius: 8, border: "1px solid #f0f0f0", fontSize: 13 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 13 }} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            title={
              <span className="flex items-center gap-2 font-medium">
                <BarChartOutlined className="text-[#FA8C16]" /> 今日决策动作分布
              </span>
            }
            size="small"
          >
            {decisionData.length === 0 ? (
              <Empty description="暂无数据" />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart
                  data={decisionData}
                  layout="vertical"
                  margin={{ top: 8, right: 24, left: 16, bottom: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "#595959" }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={64}
                    tick={{ fontSize: 12, fill: "#595959" }}
                  />
                  <ReTooltip
                    cursor={{ fill: "#f5f5f5" }}
                    contentStyle={{ borderRadius: 8, border: "1px solid #f0f0f0", fontSize: 13 }}
                  />
                  <Bar dataKey="value" name="笔数" radius={[0, 6, 6, 0]} barSize={22}>
                    {decisionData.map((d) => (
                      <Cell key={d.decision} fill={DECISION_META[d.decision]?.color ?? "#1677FF"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
