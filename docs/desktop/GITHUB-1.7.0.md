# GitHub 登录（1.7.0）

目标：用户不该为了看自己的仓库去 GitHub 手动造一个 PAT。点「用 GitHub 登录」，在浏览器确认，回来就能看到仓库列表。

## 用的是设备码流程

桌面应用没有自己的回调服务器，GitHub 为这种情况提供了 OAuth Device Flow：

1. 应用 `POST https://github.com/login/device/code`，带上 `client_id` 和 `scope=repo`。
2. GitHub 返回 `device_code`（保密，留在主进程）、`user_code`（给人看，如 `ABCD-1234`）、`expires_in`、`interval`。
3. 应用把验证码显示出来并打开 `https://github.com/login/device`，用户在浏览器里输入并同意。
4. 应用按 `interval` 轮询 `POST https://github.com/login/oauth/access_token`：
   - `authorization_pending` → 继续等；
   - `slow_down` → 用 GitHub 新给的 `interval` 放慢（最小 10 秒）；
   - `expired_token` / `bad_verification_code` → 结束，提示重新开始；
   - `access_denied` → 结束，提示用户取消了授权；
   - 拿到 `access_token` → 调 `GET /user` 确认身份，加密保存并结束。

轮询在渲染进程里用 `setTimeout` 串起来，组件卸载或用户点「取消」就停，不会留下定时器。`device_code` 只在主进程内存里，成功后立刻丢弃。

## Client ID 从哪来

设备码流程只需要公开的 Client ID，不需要 client secret。取值顺序：

1. 构造 `GitHub` 时的 `options.clientId`（构建期注入）；
2. 设置页里填的（存在 `github.json` 的 `clientId`，明文，不是密钥）；
3. 环境变量 `ECA_GITHUB_CLIENT_ID`。

建一次就好：GitHub → Settings → Developer settings → **OAuth Apps** → New OAuth App，勾选 **Enable Device Flow**，把 Client ID 填进设置页。

没配置时界面不会假装能登录：登录区直接说明为什么不可用、去哪儿建，并且把「本机 gh」和「访问令牌」两条路放在前面。

## 三条路的关系

| 路径 | 需要什么 | 适合谁 |
| --- | --- | --- |
| 用 GitHub 登录 | 一个 OAuth App Client ID | 产品用户，一次点击 |
| 使用本机 gh 登录 | 本机 `gh auth login` 过 | 开发者，零配置 |
| 访问令牌 | 手动创建 PAT | 兜底、临时 |

三条路最终都落到同一个 `connect(token)`：校验 `/user`、`safeStorage` 加密、写 `github.json`。界面只回显账号名和仓库列表，令牌不出主进程。

## 权限与撤销

只申请 `repo`：读仓库列表需要它，克隆私有仓库也需要它。用户在 GitHub → Settings → Applications 里随时可以撤销，撤销后应用下次请求会收到 401，界面提示「GitHub 拒绝了这个令牌」。

## 测试

`desktop/tests/github.test.cjs` 用注入的 `fetch` 覆盖了：拿到码、`pending`、成功后加密写入、成功后不能复用 device code、没有 Client ID 不联网、`slow_down` 的间隔、过期、拒绝、未启用 Device Flow、Client ID 的增删改与断开保留、`gh` 令牌登录。
