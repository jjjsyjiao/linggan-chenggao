import 'package:flutter/material.dart';

import '../models/service_settings.dart';

Future<ServiceSettings?> showServiceSettings(
  BuildContext context,
  ServiceSettings settings,
) => showModalBottomSheet<ServiceSettings>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  backgroundColor: Theme.of(context).scaffoldBackgroundColor,
  builder: (context) => _ServiceSettingsSheet(settings: settings),
);

class _ServiceSettingsSheet extends StatefulWidget {
  const _ServiceSettingsSheet({required this.settings});
  final ServiceSettings settings;

  @override
  State<_ServiceSettingsSheet> createState() => _ServiceSettingsSheetState();
}

class _ServiceSettingsSheetState extends State<_ServiceSettingsSheet> {
  final _form = GlobalKey<FormState>();
  late final _url = TextEditingController(text: widget.settings.baseUrl);
  late final _key = TextEditingController(text: widget.settings.apiKey);
  bool _obscure = true;

  @override
  void dispose() {
    _url.dispose();
    _key.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SafeArea(
    child: SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(
        24,
        8,
        24,
        MediaQuery.viewInsetsOf(context).bottom + 24,
      ),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '连接创作服务',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 10),
            const Text(
              '连接你自己的 Python 服务，让图片与想法开始创作。',
              style: TextStyle(color: Color(0xFF8C7F74), height: 1.6),
            ),
            const SizedBox(height: 24),
            TextFormField(
              controller: _url,
              decoration: const InputDecoration(
                labelText: '服务地址',
                hintText: 'http://192.168.1.8:8072',
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
              validator: (value) =>
                  ServiceSettings.validateBaseUrl(value ?? ''),
            ),
            const SizedBox(height: 18),
            TextFormField(
              controller: _key,
              obscureText: _obscure,
              enableSuggestions: false,
              autocorrect: false,
              decoration: InputDecoration(
                labelText: 'API Key（可选）',
                helperText: '仅保存在本次运行内存中，退出后需重新填写',
                suffixIcon: IconButton(
                  onPressed: () => setState(() => _obscure = !_obscure),
                  tooltip: _obscure ? '显示 API Key' : '隐藏 API Key',
                  icon: Icon(
                    _obscure
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFF5EFE7),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Text(
                '真机：手机和电脑连接同一 Wi-Fi，填写电脑的局域网 IP，服务监听 0.0.0.0。\n\nAndroid 模拟器：10.0.2.2:8072\niOS 模拟器：127.0.0.1:8072\n公网服务请使用 HTTPS。',
                style: TextStyle(
                  color: Color(0xFF796D62),
                  fontSize: 13,
                  height: 1.6,
                ),
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  if (_form.currentState!.validate()) {
                    Navigator.pop(
                      context,
                      ServiceSettings(
                        baseUrl: _url.text.trim(),
                        apiKey: _key.text.trim(),
                      ),
                    );
                  }
                },
                child: const Text('保存连接设置'),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
