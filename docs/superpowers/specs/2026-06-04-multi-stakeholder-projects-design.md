# 多利益相关者项目协作 — 设计文档 (Multi-Stakeholder Projects Design)

> 日期: 2026-06-04
> 状态: 待实现 (设计已确认)

## 背景与问题 (Background & Problem)

当前系统中,`InterviewSession` 直接挂在单个 `user_id` 上,意味着**每个访谈项目只属于一个账号**。
这造成一个缺陷:同一个项目的其他利益相关者 (stakeholder) 无法访问该项目。

同时,系统存在**角色定位不清**的问题:`User` 模型带有 `domain_level`(只对 stakeholder 有意义),
但项目目标又说"由需求工程师 (Requirements Engineer, RE) 审查导出",两者混在一个账号概念里。

本设计引入**双角色 + 项目 + 邀请制**,解决上述两个问题。

## 工作流程总览 (Workflow)

系统有**两种角色**(沿用代码中已有的 `role` 字段取值):

- **需求工程师 (`requirements_engineer`)** — 配置者 + 审查者
- **利益相关者 (`stakeholder`)** — 自己登录、自己与 AI 对话

> **与现有代码的调和(重要):** 合并进来的代码里 RE 已经是一个**全局策展人**
> (`GET /sessions` 让 RE 看到所有人的会话)。本设计**取代**该行为,改为
> **项目作用域**:RE 只能看到**自己拥有的项目**下的会话。`role` 取值继续用
> `requirements_engineer` / `stakeholder`,`promote_user.py` 脚本保留。

核心流程 (Flow 2):

1. RE 登录 → 创建项目,设定 `background / goals / scope`。
2. RE 在项目内输入 stakeholder 邮箱 → 发出**邀请**。
3. 系统生成 `Invitation`(token + 过期时间),状态 `pending`。
   - FYP 阶段**不真发邮件**:邀请链接直接显示在 RE 界面,由 RE 自行转发。
4. stakeholder 打开邀请链接 → **自己设置密码** → 激活账号 + 加入项目 (`Membership`),`Invitation` 置为 `accepted`。
5. stakeholder 登录后,在**自己的会话**里独立与 AI 对话,回答 AI 生成的追问问题。
6. RE 不介入对话;访谈结束后,RE 查看该项目下**所有** stakeholder 的会话并导出需求报告。
7. stakeholder 在访谈结束时,只看到 **"本次需求采集已结束"** 的状态,不查看整理出的需求。

## 角色权限 (Permissions)

| 操作 | engineer | stakeholder |
|---|---|---|
| 创建项目 / 设定背景 | ✅ | ❌ |
| 邀请成员(仅限自己拥有的项目) | ✅ | ❌ |
| 与 AI 对话(回答追问) | ❌ | ✅(仅自己的会话) |
| 查看项目下所有会话(仅限自己拥有的项目) | ✅ | ❌ |
| 查看自己的会话 | — | ✅(仅自己的) |
| 查看 / 导出需求报告 | ✅ | ❌ |
| 查看"采集已结束"状态 | — | ✅ |

## 数据模型 (Data Model)

去掉 `InterviewSession.user_id`,改为以 `Project` 为中心的结构。

```
User
  - id, email, hashed_password, real_name, phone
  - role: "requirements_engineer" | "stakeholder"   # 已存在于代码
  - domain_level                            # 仅 stakeholder 有意义
  - status: "active" | "invited"            # invited = 已邀请未激活(可选)
  - created_at

Project                                      # 新增
  - id
  - owner_id            -> User(engineer)    # 项目拥有者
  - title
  - background          # RE 设定,喂给 AI 作上下文
  - goals
  - scope
  - created_at, updated_at

Membership                                   # 新增,User <-> Project 多对多
  - id
  - project_id -> Project
  - user_id    -> User(stakeholder)
  - role_in_project: "stakeholder"
  - joined_at
  # 约束: (project_id, user_id) 唯一

Invitation                                   # 新增,邀请制核心
  - id
  - project_id -> Project
  - email
  - token              # 一次性激活令牌
  - status: "pending" | "accepted" | "expired"
  - expires_at         # 默认 7 天
  - created_at

InterviewSession                             # 改造
  - id
  - project_id   -> Project                  # 改:不再直接挂 user_id
  - stakeholder_id -> User(stakeholder)      # 这段对话属于哪个 stakeholder(一人一段)
  - status: active | completed | archived
  - phase: exploration | deepening | validation
  - summary
  - created_at, updated_at
  # 约束: (project_id, stakeholder_id) 唯一 —— 一人一项目一会话

DialogueTurn   # 不变,挂 session_id
Requirement    # 不变,挂 session_id
```

### 关键不变量 (Invariants)

- 一个 `Project` 由一个 engineer 拥有 (`owner_id`)。
- 一个 stakeholder 可加入**多个**项目(通过多条 `Membership`)。
- 一个 stakeholder 在**一个项目里只有一段** `InterviewSession`(`(project_id, stakeholder_id)` 唯一)。
- RE 只能操作/查看自己 `owner_id` 名下的项目及其会话。
- stakeholder 只能查看/操作自己的会话。

## 邀请流程细节 (Invitation Details)

- **链接有效期**: 7 天;过期后 `status = expired`,RE 可重新邀请。
- **已注册邮箱被邀请**: 跳过设密码,直接创建 `Membership` 加入项目。
- **邮件发送**: FYP 阶段不实现,邀请链接显示在 RE 界面由其手动转发。
  - 未来工作: 接入邮件服务自动发送。

## AI 上下文衔接 (AI Context Integration)

`Project.background / goals / scope` 在生成追问问题时,作为上下文注入现有 `ContextManager`
(可拼入或替换其 `summary` 输入),让 AI 的提问围绕 RE 设定的项目方向展开。

## 受影响的现有代码 (Impacted Existing Code)

- `backend/app/models/user.py` — 增加 `role`、(可选)`status`。
- `backend/app/models/session.py` — `user_id` → `project_id` + `stakeholder_id`。
- 新增模型: `project.py`、`membership.py`、`invitation.py`。
- `backend/app/routers/sessions.py` — 改为基于 project / membership 的归属与鉴权。
- 新增路由: 项目 CRUD、邀请(创建/接受)、成员列表。
- `backend/app/deps.py` — 增加按角色 (engineer / stakeholder) 鉴权的依赖。
- 前端: 区分 engineer 与 stakeholder 两套界面;新增项目管理页、邀请页、邀请接受/设密码页。

## 范围之外 / 未来工作 (Out of Scope / Future Work)

- 真实邮件发送服务。
- 跨利益相关者的**需求冲突检测**(本结构为其打基础,但本期不做)。
- RE 在访谈过程中实时介入 / 调整 AI 提问(本期 RE 不介入)。
- stakeholder 在一个项目中开启多段会话(本期一人一段)。
- stakeholder 查看自己被整理出的需求(本期仅显示"已结束"状态)。
