# 灵感成稿：小红书笔记生成与 Flutter 客户端

选择相册图片，输入创作要求，生成标题、正文和话题；在预览页编辑后，携图打开小红书并手动粘贴文案、确认发布。支持 Android / iOS，只选择图片，不包含视频。

**第一次使用，按下面的顺序：准备环境 → 跑通免费演示 → 配置真实 AI → 运行手机 App。** 不需要先学习 CrewAI，也不需要先安装数据库、Redis 或 Docker。

## 先了解需要运行什么

```text
手机 / 模拟器上的 Flutter App
          ↓ 上传图片与创作要求
电脑上的 Python 服务（本地端口 8072）
          ↓ 仅真实模式调用
阿里云通义视觉模型
```

- **演示模式**：无需模型密钥，不调用模型；返回带“演示”标记的示例稿，用于验证安装、选图、上传和预览，不会按要求真实创作。
- **真实模式**：图片和完整创作要求一起发送给模型，生成可编辑草稿。需要联网及可用的模型 API Key，模型调用可能产生费用。
- 本地体验时电脑服务需要保持运行；手机脱离电脑使用，需要另行部署服务到云端。模型计算在阿里云，电脑或云服务器不需要 GPU。

| 想做什么 | 从哪里开始 |
| --- | --- |
| 第一次安装、先确认能跑 | 按下方第 1～3 步操作 |
| 用自己的图片真实生成 | 第 4 步 |
| 安装到 Android / iPhone | 第 5 步及 [Flutter 详细指南](flutter_client/README.md) |
| 学习原来的 CrewAI 多 Agent 课程 | 跑通后看[代码阅读指南](doc/代码阅读指南.md) |

## 1. 准备源码和工具

下载或克隆**本项目完整源码**，解压后用 VS Code 等编辑器打开文件夹。在编辑器里打开终端；当前目录应能看到下面这些文件，这里称为“项目根目录”：

已安装 Git 时，可在终端执行：

```sh
git clone https://github.com/jjjsyjiao/linggan-chenggao.git
cd linggan-chenggao
```

```text
README.md
pyproject.toml
uv.lock
.env.example
src/
flutter_client/
```

下面的后端命令都在项目根目录执行。不要在 `src/` 或 `flutter_client/` 中执行后端安装命令。

本项目使用 `uv` 安装 Python 和依赖。只需按自己的系统执行一组安装命令：

Windows PowerShell：

```powershell
winget install --id astral-sh.uv -e
```

macOS / Linux 终端：

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后关闭并重新打开终端，再进入项目根目录。执行 `uv --version`，能看到版本号即成功。若没有 `winget` 或安装失败，参考 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)。

## 2. 安装 Python 依赖并创建配置

### 安装依赖

下面的命令在 Windows PowerShell、macOS 和 Linux 中相同：

```sh
uv python install 3.13
uv sync --frozen --python 3.13 --extra dev
```

`uv` 会建立根目录的 `.venv/` 虚拟环境，并按 `uv.lock` 安装固定版本的依赖。看到安装/审计完成且没有错误即成功；后续使用 `uv run`，无需手动激活环境或再运行 `pip install`。

**使用 Python 3.11～3.13，这里统一选 3.13。** 当前 CrewAI 依赖不支持 Python 3.14 及以上；不要直接用系统里任意版本的 Python。首次安装需要下载 Python 和依赖，请保持网络连接。

### 创建 `.env`

`.env` 是服务配置文件，放在项目根目录。只在它不存在时复制示例，已有配置请保留。

Windows PowerShell：

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

macOS / Linux：

```sh
if [ ! -f .env ]; then cp .env.example .env; fi
```

用编辑器打开 `.env`，找到并修改下面几项，同名配置只保留一条：

```dotenv
APP_ENV=development
APP_XHS_DEMO_MODE=true
APP_LLM_API_KEY=
APP_API_KEYS=
```

其余配置保持示例值即可。本次先用演示模式，所以两种 Key 都留空。笔记生成不需要启动 MySQL、Redis，也不需要百度搜索密钥。Windows 请确认文件名确实为 `.env`，没有被保存成 `.env.txt`。

## 3. 启动服务，完成第一次演示生成

### 终端 A：启动服务

在项目根目录执行，三种系统使用同一条命令：

```sh
uv run --frozen python -m uvicorn app.main:app --app-dir src --host 0.0.0.0 --port 8072
```

看到 `Application startup complete` 和 `Uvicorn running on http://0.0.0.0:8072`，表示启动完成。**保持终端 A 开着**；需要停止时按 `Ctrl+C`。首次启动先使用上面的单进程命令，不加 `--reload` 或 `--workers`，以兼容 Windows 的生成子进程。

在电脑浏览器打开：

| 地址 | 应该看到什么 |
| --- | --- |
| [健康检查](http://127.0.0.1:8072/health/live) | `{"status":"ok"}` |
| [接口文档](http://127.0.0.1:8072/docs) | FastAPI 接口列表，可查看请求字段 |

`0.0.0.0` 是监听地址，浏览器和 App 使用下面给出的访问地址。健康检查正常只代表服务可访问，不代表模型密钥或 AI 生成已经验证。

### 终端 B：上传仓库自带图片

另开一个终端 B，仍进入项目根目录，保留终端 A。先使用仓库自带的测试图片，避免图片路径写错。

Windows PowerShell（使用 `curl.exe`）：

```powershell
curl.exe -sS -F "idea_text=给这张照片写一篇简短随笔" -F "images=@tests/integration/20260202161329_150_6.jpg" http://127.0.0.1:8072/api/v1/xhs/notes/generate
```

macOS / Linux：

```sh
curl -sS -F "idea_text=给这张照片写一篇简短随笔" -F "images=@tests/integration/20260202161329_150_6.jpg" http://127.0.0.1:8072/api/v1/xhs/notes/generate
```

**成功标志**：返回 JSON 中 `code` 为 `0`，`data` 有 `title`、`content`，且 `is_demo` 为 `true`。这表示上传、图片校验和演示响应链路已跑通；演示不会启动模型生成子进程，也不代表真实模型效果。

上传多张图片时重复添加 `-F "images=@另一张图片的路径"`。换成自己的图片时，路径必须指向真实存在的图片；含空格的路径保留整段双引号。

这条安装与演示路径已在 macOS、Python 3.13.13 的独立新环境验证：依赖安装成功，健康检查与图片生成均返回 HTTP 200。Windows 命令已按平台差异核对，尚未在 Windows 实机验证。

## 4. 切换真实 AI 生成

演示成功后，再按[阿里云百炼获取 API Key 的官方说明](https://help.aliyun.com/zh/model-studio/get-api-key)创建可用密钥。默认配置使用中国内地北京接入，密钥、地域和模型权限需要匹配。

在根目录 `.env` 中修改：

```dotenv
APP_XHS_DEMO_MODE=false
APP_LLM_API_KEY=这里换成你自己的百炼模型密钥
APP_LLM_IMAGE_MODEL=qwen3-vl-plus
APP_LLM_REGION=cn
```

`APP_LLM_API_KEY` 后填真实值，不要保留示例文字。按 `Ctrl+C` 停止终端 A，再执行第 3 步的启动命令；修改 `.env` 后必须重启。环境变量优先于 `.env`，如果此前在终端设置过同名变量，也要同步修改或清除。

再次发送第 3 步的生成请求，或在手机 App 中生成。**真实生成成功时 `is_demo=false`**，且标题、正文随图片和创作要求生成。每次点击或执行请求都会发起新的生成，可能计费；不要将真实生成请求当作健康探测反复执行。

这个快速接口只发送一次视觉模型请求，不运行独立写作、策略或 SEO Agent，也不自动重试。生成稿仍需检查事实：来源、排版或发布长度问题会通过 `review_warnings` 提示编辑；没有提示也不代表事实已核验。

## 5. 在 Android / iOS 上体验

后端保持运行，在另一个终端安装并运行 Flutter 客户端。首次需要安装 **Flutter SDK + Android Studio/Android SDK**；只有 Flutter 插件还不够。按 [Flutter 客户端详细指南](flutter_client/README.md)完成安装、`flutter doctor` 和设备连接，再执行：

```sh
cd flutter_client
flutter pub get
flutter devices
```

从 `flutter devices` 中选择 Android 设备。比如模拟器 ID 确实为 `emulator-5554` 时，运行：

```sh
flutter run -d emulator-5554
```

真机在 App 右上角“服务设置”中填写服务地址。**手机和电脑需在同一 Wi-Fi**，先在手机浏览器检查对应 `/health/live`：

| 设备 | App 服务地址 |
| --- | --- |
| Android 官方模拟器 | `http://10.0.2.2:8072` |
| Android / iPhone 真机 | `http://电脑当前局域网IP:8072`，需替换中文为实际 IP |
| iOS 模拟器，后端也在这台 Mac | `http://127.0.0.1:8072` |

手机上的 `localhost` 指手机自身。服务地址只填根地址，不追加 `/api` 或 `/docs`；Wi-Fi、防火墙和 USB 反向端口转发的排查步骤见客户端指南。iOS 构建需要 macOS + Xcode，iPhone 还需配置开发签名。

手机端操作：**选单张/多张图片 → 填写具体要求 → 生成 → 编辑标题、正文和话题 → 复制文案并分享图片 → 在小红书手动粘贴并确认发布**。分享不会自动公开发布，也不保证所有小红书版本都能进入相同的发布页面。

## 常见问题

| 现象 | 处理方法 |
| --- | --- |
| 找不到 `uv` | 完成安装后重新打开终端，检查 PATH；见官方安装说明 |
| `No pyproject.toml found` / 找不到测试图片 | 回到包含 `pyproject.toml` 的项目根目录 |
| Python 版本不兼容或依赖装不上 | 重新执行 `uv python install 3.13` 和第 2 步固定版本的同步命令；保留仓库的 `uv.lock` |
| Windows 生成时报子进程相关错误 | 使用第 3 步命令；先去掉 `--reload` 和多 worker 配置 |
| `Address already in use` | 8072 已被占用，确认是否已有本项目服务；换端口时要同步修改命令及 App 地址 |
| 浏览器打开 `http://127.0.0.1:8072` 返回404 | 根路径没有网页；请访问 `/health/live` 或 `/docs` |
| `/health/live` 正常但总是固定示例 | 演示模式不会真实创作；关闭演示、填写模型密钥并重启 |
| 改 `.env` 没生效 | 先停止并重启后端；确认根目录及系统环境变量没有覆盖配置 |
| HTTP 401 | 请求头/App 的服务 Key 不匹配 `APP_API_KEYS`，不要填成模型 Key |
| HTTP 413 / 415 | 图片过大、损坏或格式不支持；先试一张小 JPEG/PNG |
| HTTP 429 | 当前生成槽已满，等待现有任务结束；不要连续重复提交 |
| HTTP 502 / 503 / 504 | 根据返回的 `message` 和 `request_id` 查终端或 `logs/app.log`；分别排查模型响应、密钥/配置及超时 |
| 手机无法连接 | 先用手机浏览器检查健康地址，核对电脑 IP、同一 Wi-Fi、监听地址、防火墙；详见客户端指南 |

遇到问题时保留错误信息和 `request_id`，不要发送 `.env` 内容或模型密钥。
密钥配置、提交前扫描和误泄露处理见[密钥与发布安全](SECURITY.md)。

## 配置速查

完整配置见 [.env.example](.env.example)。以下是入门最常用的项目：

| 配置 | 用途 | 本地入门设置 |
| --- | --- | --- |
| `APP_ENV` | 运行环境 | `development`，可访问 `/docs` |
| `APP_XHS_DEMO_MODE` | 是否使用演示稿 | 首次 `true`，真实创作改 `false` |
| `APP_LLM_API_KEY` | Python 调用通义模型的密钥 | 演示留空，真实生成必填；只放服务端 |
| `APP_LLM_IMAGE_MODEL` | `/generate` 的视觉模型 | `qwen3-vl-plus` |
| `APP_LLM_REGION` | 模型接入地域 | `cn`；其他地域需核对密钥及接入地址 |
| `APP_LLM_MODEL` | 旧 `/report` 使用的文字模型 | `qwen-plus` |
| `APP_API_KEYS` | 你自己设置的接口访问密钥 | 本地开发可留空；非空时 App 填其中一个值 |
| `APP_DATABASE_URL` / `APP_REDIS_URL` | 数据层、缓存扩展配置 | 当前笔记生成无需启动这些服务 |
| `APP_BAIDU_API_KEY` | 百度搜索工具密钥 | 当前笔记生成不需要 |
| `APP_PORT` | `python -m app` 入口读取的端口 | 本指南用 uvicorn，实际端口由命令的 `--port` 指定 |

两种 Key 用途不同：**模型 Key (`APP_LLM_API_KEY`) 不要填入 Flutter 的服务设置；Flutter 只接收你在 `APP_API_KEYS` 中自行设置的服务访问 Key。** `.env` 中统一使用 `APP_LLM_API_KEY`；备用 `QWEN_API_KEY` 只从已导出的系统环境变量读取。

## 开发、接口与部署

### 离线测试

在项目根目录运行，测试使用模拟上游，不会调用付费模型：

```sh
uv run --frozen pytest tests/ -q
```

客户端测试在 `flutter_client/` 中运行 `flutter test`。2026-10-28 最近一次功能回归为后端 631 项、Flutter 32 项通过；历史真实调用、耗时和质量局限见[生成速度优化](doc/生成速度优化.md)。离线通过不等于真实模型权限、文案质量或所有操作系统均已验证。

`tests/integration/xhs_note_curl.sh` 是向已启动服务发请求的 **Bash 示例**，调用较慢的 `/report`，不属于上面的离线测试；真实模式下会调用模型。需要研究完整报告时，再使用 `bash tests/integration/xhs_note_curl.sh`，Windows 需 Bash 环境。

### 两个生成接口

| 接口 | 作用 | 使用场景 |
| --- | --- | --- |
| `POST /api/v1/xhs/notes/generate` | 一次多图视觉请求，返回标题、正文、话题、图片顺序、核对提示 | Flutter 和日常笔记生成 |
| `POST /api/v1/xhs/notes/report` | CrewAI 三阶段多 Agent 完整报告，包含图片分析、编辑方案和文案 | 学习课程、研究完整流程 |

快速接口使用 multipart 的 `idea_text`（1～2000字符）和重复的 `images` 字段。最多20张静态图片，每张10 MiB、总计50 MiB。发布目标为标题20字符、正文连话题1000字符；超出时保留可编辑草稿并提示。接收草稿的绝对资源上限为标题200、正文8000字符；坏JSON、图片ID缺失/重复及绝对超限等仍返回失败。详见[客户端接口与服务验证](doc/客户端接口与服务验证.md)。

### 目录与阅读路线

```text
src/app/main.py                  FastAPI 入口
src/app/api/v1/xhs_note.py        两个生成接口
src/app/crews/xhs_note/fast_flow.py  一次携带全部图片和完整要求
src/app/services/note_draft.py    保留草稿、收集核对提示
src/app/crews/xhs_note/runner.py  隔离生成进程与结果传输
src/app/crews/xhs_note/flows.py   旧 CrewAI 完整多 Agent 流程
flutter_client/                 Android / iOS 客户端
tests/                          离线测试
doc/                            课程、设计和验证记录
deploy/                         Docker / K8s 部署文件
```

课程《企业级多智能体设计实战》第 11 课的原有 Agent、Task 和学习路线保留在[代码阅读指南](doc/代码阅读指南.md)，更多材料见[课程大纲](doc/课程大纲.md)、[课程逐字稿](doc/课程逐字稿.md)及[设计文档](doc/design/小红书爆款笔记项目设计文档.md)。课程微信：xiaohan_chat。
框架与课程来源说明见 [NOTICE.md](NOTICE.md)。

### 云端部署属于后续步骤

先跑通本地流程，再考虑 [Dockerfile](deploy/docker/Dockerfile) 或 [K8s 配置](deploy/k8s/deployment.yaml)。Docker 当前内部端口为 `8000`，与本地指南的 `8072` 不同，需设置正确的端口映射。Docker 安装过程尚未按 `uv.lock` 固定全部依赖，不能当作本指南已验证的干净安装路径。

公网部署时设置自己的服务访问密钥与生产配置，通过 HTTPS 提供接口，并把 Flutter 地址切换到公网根地址；模型密钥只留在服务端。`APP_ENV=production` 会关闭 `/docs`、拒绝演示生成；生产生成接口还要求配置非空 `APP_API_KEYS`。

## License

MIT
