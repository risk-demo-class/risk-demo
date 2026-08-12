import { useState, useEffect } from "react";
import { Layout, Menu, Typography, Badge, ConfigProvider } from "antd";
import {
  SafetyOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  ProfileOutlined,
  BarChartOutlined,
  StopOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import Dashboard from "./pages/Dashboard";
import RiskCheck from "./pages/RiskCheck";
import RuleBoard from "./pages/RuleBoard";
import CaseBoard from "./pages/CaseBoard";
import AssessmentBoard from "./pages/AssessmentBoard";
import BlacklistBoard from "./pages/BlacklistBoard";
import AgentChat from "./pages/AgentChat";

const { Sider, Header, Content } = Layout;

// 7 页菜单 (顺序对齐基线 AI_Risk 侧边栏)
const MENU = [
  { key: "dashboard", icon: <DashboardOutlined />, label: "风控仪表盘" },
  { key: "rules", icon: <FileSearchOutlined />, label: "规则管理" },
  { key: "cases", icon: <ProfileOutlined />, label: "案件管理" },
  { key: "assessment", icon: <BarChartOutlined />, label: "评估历史" },
  { key: "risk", icon: <ExperimentOutlined />, label: "风险检查" },
  { key: "agent", icon: <RobotOutlined />, label: "AI 风控助手" },
  { key: "blacklist", icon: <StopOutlined />, label: "黑名单" },
];

function getHashKey(): string {
  const h = window.location.hash.replace("#/", "").split("?")[0];
  return MENU.some((m) => m.key === h) ? h : "dashboard";
}

export default function App() {
  const [page, setPage] = useState(getHashKey());

  useEffect(() => {
    const onHash = () => setPage(getHashKey());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (key: string) => {
    window.location.hash = `#/${key}`;
    setPage(key);
  };

  const renderPage = () => {
    switch (page) {
      case "dashboard": return <Dashboard />;
      case "risk": return <RiskCheck />;
      case "rules": return <RuleBoard />;
      case "cases": return <CaseBoard />;
      case "assessment": return <AssessmentBoard />;
      case "blacklist": return <BlacklistBoard />;
      case "agent": return <AgentChat />;
      default: return <Dashboard />;
    }
  };

  return (
    <ConfigProvider theme={{ token: { colorPrimary: "#1677FF" } }}>
      <Layout style={{ minHeight: "100vh" }}>
        <Sider width={236} theme="dark" style={{ background: "#001529" }}>
          <div className="flex items-center gap-3 px-5 h-16 text-white border-b border-[#ffffff10]">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#1677FF22]">
              <SafetyOutlined style={{ fontSize: 20, color: "#1677FF" }} />
            </div>
            <div>
              <div className="text-[16px] font-semibold leading-tight tracking-wide">风控中心</div>
              <div className="text-[11px] text-[#8c8c8c]">Bank-Risk 控制台</div>
            </div>
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[page]}
            onClick={(e) => go(e.key)}
            items={MENU}
            style={{ background: "#001529", borderRight: 0, paddingTop: 8 }}
            className="risk-menu"
          />
        </Sider>

        <Layout>
          <Header
            style={{
              background: "#fff",
              padding: "0 24px",
              height: 64,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              boxShadow: "0 1px 4px rgba(0,21,41,0.08)",
            }}
          >
            <Typography.Title level={4} style={{ margin: 0 }}>
              {MENU.find((m) => m.key === page)?.label}
            </Typography.Title>
            <Badge status="processing" text="实时决策引擎" color="#52C41A" />
          </Header>

          <Content className="p-6 overflow-auto" style={{ background: "#F0F2F5" }}>
            <div className="fade-in" key={page}>
              {renderPage()}
            </div>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}
