# 📊 Risk Demo 课程演示仓库

本仓库用于课程各小组的**演示成果提交与展示**。每位同学在**对应行业方向**下建立**自己的名字分支**，把代码 / 演示成果推送到自己的分支上。

- 仓库地址：https://github.com/risk-demo-class/risk-demo
- 所属组织：**risk-demo-class**（GitHub Organization）
- 仓库为**公开**仓库：任何人都可以查看，但**只有被老师邀请的同学才能推送**。

---

## 一、分支结构

| 分支名 | 行业方向 | 保护状态 |
|---|---|---|
| `main` | 主分支 | 🔒 受保护，仅组织所有者可推送 |
| `tourism` | 旅游 | 🔒 受保护，仅组织所有者可推送 |
| `banking` | 银行 | 🔒 受保护，仅组织所有者可推送 |
| `education` | 教育 | 🔒 受保护，仅组织所有者可推送 |
| `manufacturing` | 制造业 | 🔒 受保护，仅组织所有者可推送 |
| `logistics` | 物流 | 🔒 受保护，仅组织所有者可推送 |
| `medical` | 医疗 | 🔒 受保护，仅组织所有者可推送 |
| `telecom` | 电信 | 🔒 受保护，仅组织所有者可推送 |
| `sharing-economy` | 共享经济 | 🔒 受保护，仅组织所有者可推送 |

> 🔒 受保护 = 不能直接推送（会被 GitHub 拒绝）。这保证了行业分支和主分支**保持干净**。
>
> 同学们**不需要也不应该**直接推送到上面这些分支——你们推送的是**自己名字的分支**（见下文）。

---

## 二、重要规则（务必遵守）

1. ✅ **每位同学只能往自己的分支推送**，分支用自己的名字命名（如 `zhangsan`、`li-xiaoming`）
2. ✅ 自己的分支**从对应行业分支派生**（例如旅游组的同学从 `tourism` 派生），保证内容和行业主题一致
3. 🚫 **禁止向 `main` 和 8 个行业分支直接推送**（已开启保护，推送会被拒绝）
4. 🚫 **禁止修改、覆盖其他同学的分支**
5. 📁 建议在自己的分支里先建一个**自己名字的文件夹**放成果，便于查看

---

## 三、学生推送步骤（第一次）

### 第 0 步：准备工作

1. **注册 GitHub 账号**：https://github.com/join （已有账号跳过）
2. **把你的 GitHub 用户名发给老师**——老师把你加入对应行业团队后，你才有推送权限
3. **安装 Git**：https://git-scm.com/download/win 一路 Next 安装

### 第 1 步：克隆仓库到本地

打开命令行（Windows 按 `Win+R` 输入 `cmd` 回车；或右键桌面 →「在终端中打开」），执行：

```bash
git clone https://github.com/risk-demo-class/risk-demo.git
cd risk-demo
```

### 第 2 步：从你的行业分支派生自己的分支（用自己的名字）

先确定你属于哪个行业组，然后执行（以**旅游组**、名字 **zhangsan** 为例）：

```bash
git checkout -b zhangsan origin/tourism
```

> 把 `origin/tourism` 换成你所在组的行业分支：旅游 `tourism`、银行 `banking`、教育 `education`、制造业 `manufacturing`、物流 `logistics`、医疗 `medical`、电信 `telecom`、共享经济 `sharing-economy`。
>
> 分支名建议：名字拼音全小写，多个字用 `-` 连接（如 `zhangsan`、`wang-xiaoming`）。**不要用中文和空格**。

### 第 3 步：放入你的成果

把代码 / 演示文件（PPT、图片、视频、代码等）复制到仓库文件夹里，建议建一个自己的文件夹：

```bash
mkdir zhangsan
# 然后把你的文件放进 zhangsan 文件夹
```

### 第 4 步：提交并推送（关键！）

```bash
git add .
git commit -m "zhangsan 提交旅游行业演示成果"
git push -u origin zhangsan
```

看到 `branch 'zhangsan' set up to track` 和进度条走完，就说明**推送成功**了 🎉

### 第 5 步：确认成果

打开 https://github.com/risk-demo-class/risk-demo ，点击左上角的 **Branch 下拉框**，选择你的分支名 `zhangsan`，即可看到你的文件。

---

## 四、以后每次更新（重复这三条）

```bash
git add .
git commit -m "更新说明，比如：补充了演示视频"
git push
```

> 如果提示 `git pull` 或分支落后，说明有其他同学在**同一个分支**上推过（一般不会发生，因为每人一个分支）。必要时先 `git pull` 再推。

---

## 五、常见问题（FAQ）

| 问题 | 原因与解决办法 |
|---|---|
| `Permission to ... denied` | 老师还没把你加入团队，或邀请没接受。把 GitHub 用户名发给老师 |
| `protected branch ... declined` / `Updates were rejected` | 你试图推送到受保护的分支（main 或行业分支）。改用自己名字的分支：`git checkout -b 你的名字 origin/你的行业分支` |
| `master has no upstream branch` | 说明你在 `main` 上，先执行第 2 步建立自己的分支 |
| 推送超时 / 网络错误 | GitHub 网络不稳定，可以开代理，或改用 SSH 方式（见下节） |
| 忘了自己分支名 | `git branch -a` 查看所有分支（本地+远程） |

### 网络不好？用 SSH 方式（可选）

如果 HTTPS 推送经常超时，可以用 SSH：

1. 生成密钥：`ssh-keygen -t ed25519 -C "你的邮箱"`（一路回车）
2. 查看公钥：`cat ~/.ssh/id_ed25519.pub`，复制全部内容
3. 粘贴到 GitHub：https://github.com/settings/keys → New SSH key → 保存
4. 之后用 SSH 地址克隆：

```bash
git clone git@github.com:risk-demo-class/risk-demo.git
cd risk-demo
git checkout -b zhangsan origin/tourism
# ... 后面的提交推送步骤一样
```

---

## 六、老师（管理员）操作备忘

组织下已建好 **8 个行业团队**（`tourism-team`、`banking-team`、`education-team`、`manufacturing-team`、`logistics-team`、`medical-team`、`telecom-team`、`sharing-economy-team`），都已对该仓库有 **push 权限**。学生加入团队后即可推送自己的分支。

### 1. 把学生加入对应行业团队（推荐方式）

```bash
# 把 zhangsan 加入旅游组
gh api -X PUT orgs/risk-demo-class/teams/tourism-team/memberships/zhangsan -f role=member
```

或网页操作：组织主页 → **Teams** → 进入 `tourism-team` → **Add member** → 输入学生用户名。

### 2. 严格锁定：每个学生分支只允许本人推送（组织仓库已支持 ✅）

收集齐学生用户名后，对每个学生的分支设置「仅该学生可推送」（这样别人想推也推不上去）：

```bash
# 示例：锁定 zhangsan 的分支，只允许 zhangsan（和老师）推送
gh api -X PUT repos/risk-demo-class/risk-demo/branches/zhangsan/protection \
  -H "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{"required_status_checks":null,"enforce_admins":false,
 "required_pull_request_reviews":null,
 "restrictions":{"users":["zhangsan"],"teams":[],"apps":[]}}
EOF
```

> 有多少个学生就执行多少次（分支名、用户名替换一下即可）。也可以把学生名单整理好发给我，我一次性帮你全部配置好。

### 3. 查看各分支的推送情况

```bash
gh api "repos/risk-demo-class/risk-demo/branches?per_page=100" --jq '.[] | select(.name != "main" and .name != "tourism" and .name != "banking" and .name != "education" and .name != "manufacturing" and .name != "logistics" and .name != "medical" and .name != "telecom" and .name != "sharing-economy") | .name'   # 只看学生的个人分支
```

### 4. 合并学生成果到行业分支（可选：汇总演示）

```bash
# 本地操作示例：把 zhangsan 的成果合并进 tourism
git fetch origin
git checkout tourism
git pull
git merge origin/zhangsan
git push
```

或直接在网页上：打开 zhangsan 分支 → **Contribute → Open pull request** → 目标选 `tourism` → 你自己审查并 Merge。

---

*本指南由老师统一发布，如有问题请私信老师。祝大家演示顺利！🎓*
