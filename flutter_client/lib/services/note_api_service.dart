import 'dart:io';

import 'package:dio/dio.dart';
import 'package:image_picker/image_picker.dart';

import '../models/generated_note.dart';
import '../models/service_settings.dart';

class NoteApiException implements Exception {
  const NoteApiException(
    this.message, {
    this.requestId,
    this.statusCode,
    this.cancelled = false,
  });

  final String message;
  final String? requestId;
  final int? statusCode;
  final bool cancelled;

  @override
  String toString() => message;
}

class NoteApiService {
  NoteApiService({Dio? dio}) : _dio = dio ?? Dio() {
    _dio.options.connectTimeout = const Duration(seconds: 10);
  }

  final Dio _dio;

  /// A fresh body is built for each attempt: Dio multipart streams are single use.
  Future<FormData> buildFormData({
    required String idea,
    required List<XFile> images,
  }) async {
    if (images.isEmpty || images.length > 20) {
      throw const NoteApiException('请选择 1–20 张图片');
    }
    final trimmedIdea = idea.trim();
    if (trimmedIdea.isEmpty || trimmedIdea.runes.length > 2000) {
      throw const NoteApiException('请填写 1–2000 字的创作想法');
    }
    final form = FormData()..fields.add(MapEntry('idea_text', trimmedIdea));
    var totalBytes = 0;
    for (final image in images) {
      try {
        final length = await image.length();
        if (length > 10 * 1024 * 1024) {
          throw const NoteApiException('单张图片不能超过 10 MiB，请压缩后重试');
        }
        totalBytes += length;
        if (totalBytes > 50 * 1024 * 1024) {
          throw const NoteApiException('图片总大小不能超过 50 MiB，请减少数量或压缩后重试');
        }
        form.files.add(
          MapEntry(
            'images',
            await MultipartFile.fromFile(
              image.path,
              filename: image.name,
              contentType: DioMediaType.parse(_imageMimeType(image)),
            ),
          ),
        );
      } on FileSystemException {
        throw const NoteApiException('图片已不可读取，请从相册重新选择');
      }
    }
    return form;
  }

  Future<GeneratedNote> generate({
    required ServiceSettings settings,
    required String idea,
    required List<XFile> images,
    required CancelToken cancelToken,
    ProgressCallback? onSendProgress,
  }) async {
    if (ServiceSettings.validateBaseUrl(settings.baseUrl) != null) {
      throw const NoteApiException('服务地址无效，请先检查右上角的服务设置');
    }
    try {
      final form = await buildFormData(idea: idea, images: images);
      if (cancelToken.isCancelled) {
        throw const NoteApiException('已取消本次生成', cancelled: true);
      }
      final response = await _dio.post<dynamic>(
        '${settings.normalizedBaseUrl}/api/v1/xhs/notes/generate',
        data: form,
        cancelToken: cancelToken,
        onSendProgress: onSendProgress,
        options: Options(
          headers: {
            if (settings.apiKey.trim().isNotEmpty)
              'X-API-Key': settings.apiKey.trim(),
          },
          sendTimeout: const Duration(minutes: 2),
          receiveTimeout: const Duration(minutes: 12),
        ),
      );
      if (response.data is Map && response.data['code'] != 0) {
        throw _serverError(response.data, response.statusCode);
      }
      final note = GeneratedNote.fromResponse(response.data);
      note.imageIndices(images.length);
      return note;
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) {
        throw const NoteApiException('已取消本次生成', cancelled: true);
      }
      if (error.response != null) {
        throw _serverError(error.response!.data, error.response!.statusCode);
      }
      switch (error.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.sendTimeout:
        case DioExceptionType.receiveTimeout:
          throw const NoteApiException('请求超时。请检查服务状态后重试；复杂笔记可能需要几分钟');
        case DioExceptionType.badCertificate:
          throw const NoteApiException('服务证书验证失败，请检查 HTTPS 配置');
        default:
          throw const NoteApiException(
            '无法连接服务。请检查地址、网络和 Python 服务是否已启动；真机需要填写电脑的局域网 IP',
          );
      }
    } on FormatException catch (error) {
      throw NoteApiException(error.message);
    }
  }

  String _imageMimeType(XFile image) {
    final known = image.mimeType;
    if (known != null && known.startsWith('image/')) return known;
    return switch (image.name.split('.').last.toLowerCase()) {
      'jpg' || 'jpeg' => 'image/jpeg',
      'png' => 'image/png',
      'webp' => 'image/webp',
      'heic' => 'image/heic',
      'heif' => 'image/heif',
      'gif' => 'image/gif',
      'avif' => 'image/avif',
      _ => 'application/octet-stream',
    };
  }

  NoteApiException _serverError(dynamic data, int? status) {
    String? requestId;
    String? message;
    if (data is Map) {
      requestId = data['request_id'] is String
          ? data['request_id'] as String
          : null;
      if (data['message'] is String && (data['message'] as String).isNotEmpty) {
        message = data['message'] as String;
      } else if (data['detail'] is String) {
        message = data['detail'] as String;
      } else if (data['detail'] is List) {
        final details = (data['detail'] as List).whereType<Map>();
        message = details
            .map((item) => item['msg']?.toString() ?? '参数无效')
            .join('；');
      }
    }
    final fallback = switch (status) {
      401 || 403 => '服务鉴权失败，请检查 API Key',
      413 => '图片过大，请减少图片数量或压缩后重试',
      415 => '服务不支持此图片格式，请使用 JPEG、PNG 或 WebP',
      429 => '服务繁忙，请稍后重试',
      502 || 503 => '创作服务暂时不可用，请检查服务端的模型配置',
      504 => '创作服务处理超时，请稍后重试',
      422 => '请求参数无效，请检查图片和创作想法',
      _ => '生成失败${status == null ? '' : '（HTTP $status）'}，请稍后重试',
    };
    return NoteApiException(
      message?.isNotEmpty == true ? message! : fallback,
      requestId: requestId,
      statusCode: status,
    );
  }
}
