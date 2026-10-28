# 密钥与发布安全

模型密钥只保存在服务端的 `.env` 或部署平台的环境变量中。仓库仅提供空白的 `.env.example`，不要把真实模型 Key、服务访问 Key、签名证书或带凭据的配置文件提交到 Git。

Flutter 的服务设置仅接收自己在 `APP_API_KEYS` 中配置的接口访问 Key，不接收 `APP_LLM_API_KEY`。不要通过 `--dart-define` 把模型密钥编译进 APK / IPA。

仓库忽略环境文件、日志、生成资料、运行截图、构建产物和移动端签名配置。`.gitignore` 不会清除已跟踪文件或提交历史；每次发布前仍应检查实际提交内容。

安装 [Gitleaks](https://github.com/gitleaks/gitleaks) 后，可以在项目根目录扫描暂存内容与已有历史：

```sh
gitleaks git --pre-commit --staged --redact=100 .
gitleaks git --redact=100 .
```

如果密钥曾被推送到远端，应先在模型供应商或对应平台撤销并重新生成，再处理提交历史；仅删除当前文件无法收回已经公开的密钥。报告问题时提供请求 ID 与脱敏说明，不要在公开 Issue、截图或聊天中粘贴密钥和私人照片。
