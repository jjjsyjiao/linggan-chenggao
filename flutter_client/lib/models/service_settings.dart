import 'package:flutter/foundation.dart';

class ServiceSettings {
  const ServiceSettings({required this.baseUrl, this.apiKey = ''});

  factory ServiceSettings.defaults() => ServiceSettings(
    baseUrl: const String.fromEnvironment('API_BASE_URL').isNotEmpty
        ? const String.fromEnvironment('API_BASE_URL')
        : defaultTargetPlatform == TargetPlatform.android
        ? 'http://10.0.2.2:8072'
        : 'http://127.0.0.1:8072',
  );

  final String baseUrl;

  /// Kept in memory only. Never logged, embedded, or written to preferences.
  final String apiKey;

  static String? validateBaseUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !{'http', 'https'}.contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      return '请输入完整的 http:// 或 https:// 服务地址';
    }
    if (uri.path.isNotEmpty && uri.path != '/') {
      return '请填写服务根地址，不需要 /api 路径';
    }
    return null;
  }

  String get normalizedBaseUrl =>
      baseUrl.trim().replaceFirst(RegExp(r'/+$'), '');
}
