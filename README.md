# 📊 Risk Demo 课程演示仓库

本仓库用于课程各小组的**演示成果提交与展示**。每位同学已分配**自己的专属分支**，把代码 / 演示成果推送到自己的分支上即可。

- 仓库地址：https://github.com/risk-demo-class/risk-demo
- 所属组织：**risk-demo-class**（GitHub Organization）
- 仓库为**公开**仓库：任何人都可以查看，但**只有被邀请且接受邀请的同学才能推送**。

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

> 行业分支由老师维护，**同学们不要推送**。你们的成果推送到**自己的个人分支**（分支名由老师统一分配，见老师发放的对照表）。

---

## 二、重要规则（务必遵守）

1. ✅ **每位同学只能往自己的分支推送**——你的分支已经建好并**锁定为仅你本人可推送**，别人推不进来，你也推不进去别人的分支
2. ✅ 推送前请先确认自己在**自己的分支**上（`git status` 可查看）
3. 🚫 **禁止向 `main` 和 8 个行业分支推送**（受保护，推送会被拒绝）
4. 📁 建议在自己的分支里建一个**自己名字的文件夹**放成果，便于查看

---

## 三、学生推送步骤（第一次）

### 第 0 步：准备工作

1. **注册 GitHub 账号**：https://github.com/join （已有账号跳过）
2. **确认已接受组织邀请**：老师已向你发出 **risk-demo-class 组织邀请**，请在 GitHub 通知/邮箱里点 **Accept（接受）**——没接受就无法推送
3. **安装 Git**：https://git-scm.com/download/win 一路 Next 安装

### 第 1 步：克隆仓库（只克隆你自己的分支）

打开命令行（Windows 按 `Win+R` 输入 `cmd` 回车；或右键桌面 →「在终端中打开」），执行（把 `zhangsan` 换成老师发给你的**个人分支名**）：

```bash
git clone --branch zhangsan --single-branch https://github.com/risk-demo-class/risk-demo.git
cd risk-demo
```

> `--single-branch` 表示只下载你自己的分支，克隆完你**已经在自己分支上了**，不需要切换。
> 可执行 `git branch` 确认，显示 `* zhangsan` 即正确。

### 第 2 步：放入你的成果

把代码 / 演示文件（PPT、图片、视频、代码等）复制到仓库文件夹里，建议建一个自己的文件夹：

```bash
mkdir zhangsan
# 然后把你的文件放进 zhangsan 文件夹
```

### 第 3 步：提交并推送（关键！）

```bash
git add .
git commit -m "zhangsan 提交演示成果"
git push
```

看到进度条走完，就说明**推送成功**了 🎉

### 第 4 步：确认成果

打开 https://github.com/risk-demo-class/risk-demo ，点击左上角的 **Branch 下拉框**，选择你的分支名，即可看到你的文件。

---

## 四、以后每次更新（重复这三条）

```bash
git add .
git commit -m "更新说明，比如：补充了演示视频"
git push
```

---

## 五、常见问题（FAQ）

| 问题 | 原因与解决办法 |
|---|---|
| `Permission to ... denied` | 还没接受组织邀请，或推到了别人的分支。先去 GitHub 通知里点 Accept |
| `protected branch ... declined` / `Updates were rejected` | 推到了受保护分支（main/行业分支）或别人的分支。`git checkout 自己的分支名` 切回去再推 |
| `master has no upstream branch` | 在 `main` 上，先执行第 2 步切换到自己的分支 |
| 推送超时 / 网络错误 | GitHub 网络不稳定，可以开代理，或改用 SSH 方式（见下节） |
| 忘了自己分支名 | 问老师，或 `git branch -a` 查看所有分支 |

### 网络不好？用 SSH 方式（可选）

如果 HTTPS 推送经常超时，可以用 SSH：

1. 生成密钥：`ssh-keygen -t ed25519 -C "你的邮箱"`（一路回车）
2. 查看公钥：`cat ~/.ssh/id_ed25519.pub`，复制全部内容
3. 粘贴到 GitHub：https://github.com/settings/keys → New SSH key → 保存
4. 之后用 SSH 地址克隆：

```bash
git clone --branch zhangsan --single-branch git@github.com:risk-demo-class/risk-demo.git
cd risk-demo
# ... 后面的提交推送步骤一样
```

---

## 六、老师（管理员）操作备忘

已完成：8 个行业团队建好（均有仓库写权限）、学生已发组织邀请、个人分支已预建并锁定（仅本人可推，每 30 分钟自动补锁新接受邀请的学生）。

### 1. 查看学生是否已接受邀请

```bash
gh api "orgs/risk-demo-class/invitations" --jq '.[] | .login'   # 待接受的邀请
gh api "orgs/risk-demo-class/members?role=member" --jq '.[].login'   # 已加入的成员
```

### 2. 新增/补录学生

```bash
# 加入行业团队（先让学生提供 GitHub 用户名）
gh api -X PUT orgs/risk-demo-class/teams/tourism-team/memberships/<用户名> -f role=member

# 预建个人分支（从行业分支派生，如 zhangsan 从 tourism）
git push origin tourism:refs/heads/zhangsan

# 锁定分支（仅本人可推；须在学生接受邀请后执行，否则 GitHub 会忽略）
gh api -X PUT repos/risk-demo-class/risk-demo/branches/zhangsan/protection \
  -H "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{"required_status_checks":null,"enforce_admins":false,
 "required_pull_request_reviews":null,
 "restrictions":{"users":["<用户名>"],"teams":[],"apps":[]}}
EOF
```

### 3. 合并学生成果到行业分支（可选：汇总演示）

```bash
git fetch origin
git checkout tourism
git pull
git merge origin/zhangsan
git push
```

---

*本指南由老师统一发布，如有问题请私信老师。祝大家演示顺利！🎓*
