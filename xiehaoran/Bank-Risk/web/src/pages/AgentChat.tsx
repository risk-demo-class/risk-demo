import { useState, useRef, useEffect } from "react";
import { Card, Input, Button, App, Tag, Collapse } from "antd";
import { SendOutlined, RobotOutlined, UserOutlined, BulbOutlined, LoadingOutlined } from "@ant-design/icons";
import { api } from "../api";

interface Msg { role: "user" | "ai"; content: string; thinking?: string }

const WELCOME_TEXT = `你好！我是银行风控 AI 助手，可以帮你完成以下任务：

- 对账户/交易进行风险检查
- 查询和分析风控案件
- 查看用户风险画像
- 查看仪表盘统计和趋势
- 管理黑名单

请问有什么需要帮助的？`;

const QUICK_ACTIONS: { label: string; prompt: string }[] = [
  { label: "今日统计", prompt: "查看今天的风控统计数据" },
  { label: "待审案件", prompt: "查看所有待审核的案件" },
  { label: "用户画像", prompt: "分析用户的风险画像" },
  { label: "规则分析", prompt: "分析规则命中效果" },
  { label: "趋势分析", prompt: "查看近30天的风控趋势" },
];

export default function AgentChat() {
  const { message } = App.useApp();
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "ai", content: WELCOME_TEXT },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, loading]);

  const send = async (text?: string) => {
    const t = (text ?? input).trim();
    if (!t || loading) return;
    setMsgs((m) => [...m, { role: "user", content: t }]);
    setInput(""); setLoading(true);
    try {
      const res = await api.agentChat(t, sessionId);
      setSessionId(res.session_id);
      setMsgs((m) => [...m, { role: "ai", content: res.reply, thinking: res.thinking }]);
    } catch (e: any) {
      message.error(e.message);
      setMsgs((m) => [...m, { role: "ai", content: `⚠️ ${e.message}` }]);
    } finally { setLoading(false); }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-140px)]">
      <Card className="flex-1 overflow-auto mb-3" styles={{ body: { height: "100%", overflow: "auto" } }}>
        <div className="space-y-4">
          {msgs.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`flex items-center justify-center w-8 h-8 rounded-full ${m.role === "user" ? "bg-[#1677FF] text-white" : "bg-[#722ED1] text-white"}`}>
                {m.role === "user" ? <UserOutlined /> : <RobotOutlined />}
              </div>
              <div className={`max-w-[75%] rounded-lg p-3 text-[13px] leading-relaxed ${m.role === "user" ? "bg-[#1677FF] text-white" : "bg-white border"}`}>
                {m.role === "ai" && m.thinking && (
                  <Collapse
                    size="small"
                    className="mb-2 border-[#F0F0F0] bg-[#FAFAFA]"
                    expandIconPosition="end"
                    items={[{
                      key: "thinking",
                      label: (
                        <span className="flex items-center gap-1 text-[12px] text-[#8C8C8C]">
                          <BulbOutlined /> 思考过程
                        </span>
                      ),
                      children: (
                        <pre className="whitespace-pre-wrap m-0 p-0 text-[12px] leading-relaxed text-[#595959] font-mono">{m.thinking}</pre>
                      ),
                    }]}
                  />
                )}
                <div className="whitespace-pre-wrap">{m.content}</div>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="flex items-center justify-center w-8 h-8 rounded-full bg-[#722ED1] text-white">
                <RobotOutlined />
              </div>
              <div className="flex items-center gap-2 max-w-[75%] rounded-2xl px-4 py-2 text-[13px] text-[#595959] bg-[#F5F5F5] border border-[#E8E8E8]">
                <LoadingOutlined className="text-[#722ED1]" spin />
                <span>思考中...</span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </Card>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-[13px] text-[#8C8C8C]">快捷指令:</span>
        {QUICK_ACTIONS.map((q) => (
          <Tag
            key={q.label}
            className="cursor-pointer text-[13px] hover:border-[#1677FF] hover:text-[#1677FF] transition-colors"
            onClick={() => send(q.prompt)}
          >
            {q.label}
          </Tag>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => send()}
          placeholder="输入风控相关问题, 回车发送"
          disabled={loading}
        />
        <Button type="primary" icon={<SendOutlined />} onClick={() => send()} loading={loading}>发送</Button>
      </div>
    </div>
  );
}
