import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:linggan_chenggao/models/generated_note.dart';
import 'package:linggan_chenggao/models/service_settings.dart';
import 'package:linggan_chenggao/services/note_api_service.dart';

class _Adapter implements HttpClientAdapter {
  _Adapter(this.handler);
  final Future<ResponseBody> Function(
    RequestOptions,
    Stream<Uint8List>?,
    Future<void>?,
  )
  handler;
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) => handler(options, requestStream, cancelFuture);
  @override
  void close({bool force = false}) {}
}

ResponseBody _json(Object body, [int status = 200]) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: ['application/json'],
  },
);
Map<String, dynamic> _note({List<String> order = const ['img_0']}) => {
  'code': 0,
  'message': 'ok',
  'request_id': 'req-test',
  'data': {
    'title': '生活有光',
    'content': '记录周末的日常。',
    'tags': ['#生活记录'],
    'image_order': order,
    'is_demo': true,
  },
};

void main() {
  late Directory directory;
  late XFile image;
  late Dio dio;
  late NoteApiService service;
  const settings = ServiceSettings(
    baseUrl: 'http://localhost:8072/',
    apiKey: 'example-key',
  );
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('linggan-api-test-');
    final file = await File('${directory.path}/photo.jpg')
        .writeAsBytes([1, 2, 3]);
    image = XFile(file.path);
    dio = Dio();
    service = NoteApiService(dio: dio);
  });
  tearDown(() async {
    dio.close(force: true);
    await directory.delete(recursive: true);
  });

  test('sends multipart with repeated images fields and API key', () async {
    dio.httpClientAdapter = _Adapter((options, stream, _) async {
      expect(
        options.uri.toString(),
        'http://localhost:8072/api/v1/xhs/notes/generate',
      );
      expect(options.headers['X-API-Key'], 'example-key');
      expect(options.receiveTimeout, const Duration(minutes: 12));
      final bytes = await stream!.fold<List<int>>(
        [],
        (result, bytes) => result..addAll(bytes),
      );
      final multipart = utf8.decode(bytes, allowMalformed: true);
      expect(RegExp('name="images"').allMatches(multipart).length, 2);
      expect(multipart, isNot(contains('images[]')));
      expect(multipart, contains('name="idea_text"'));
      expect(multipart, contains('周末探店'));
      expect(multipart, contains('image/jpeg'));
      return _json(_note(order: ['img_1', 'img_0']));
    });
    final result = await service.generate(
      settings: settings,
      idea: ' 周末探店 ',
      images: [image, image],
      cancelToken: CancelToken(),
    );
    expect(result.title, '生活有光');
    expect(result.tags, ['生活记录']);
    expect(result.imageIndices(2), [1, 0]);
    expect(result.isDemo, isTrue);
  });

  test('preserves upstream errors and request id', () async {
    dio.httpClientAdapter = _Adapter(
      (_, stream, cancel) async => _json({
        'code': 50201,
        'message': '视觉模型配置无效',
        'request_id': 'failed-request',
      }, 502),
    );
    await expectLater(
      service.generate(
        settings: settings,
        idea: '日常',
        images: [image],
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<NoteApiException>()
            .having((e) => e.message, 'message', '视觉模型配置无效')
            .having((e) => e.statusCode, 'status', 502)
            .having((e) => e.requestId, 'request id', 'failed-request'),
      ),
    );
  });

  test('explains standard FastAPI validation errors', () async {
    dio.httpClientAdapter = _Adapter(
      (_, stream, cancel) async => _json({
        'detail': [
          {
            'loc': ['body', 'idea_text'],
            'msg': 'String should have at least 1 character',
            'type': 'string_too_short',
          },
        ],
      }, 422),
    );
    await expectLater(
      service.generate(
        settings: settings,
        idea: '想法',
        images: [image],
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'detail',
          contains('at least 1 character'),
        ),
      ),
    );
  });

  test('rejects malformed successful response', () async {
    dio.httpClientAdapter = _Adapter(
      (_, stream, cancel) async => _json(_note(order: [])),
    );
    await expectLater(
      service.generate(
        settings: settings,
        idea: '想法',
        images: [image],
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'message',
          contains('图片顺序'),
        ),
      ),
    );
  });

  test('cancels an in-flight request', () async {
    final started = Completer<void>();
    dio.httpClientAdapter = _Adapter((options, stream, cancel) async {
      started.complete();
      await cancel;
      throw DioException.requestCancelled(
        requestOptions: options,
        reason: 'user cancelled',
      );
    });
    final token = CancelToken();
    final result = service.generate(
      settings: settings,
      idea: '想法',
      images: [image],
      cancelToken: token,
    );
    final expectation = expectLater(
      result,
      throwsA(
        isA<NoteApiException>().having((e) => e.cancelled, 'cancelled', isTrue),
      ),
    );
    await started.future;
    token.cancel();
    await expectation;
  });

  test('does not send already cancelled request', () async {
    var invoked = false;
    dio.httpClientAdapter = _Adapter((_, stream, cancel) async {
      invoked = true;
      return _json(_note());
    });
    final token = CancelToken()..cancel();
    await expectLater(
      service.generate(
        settings: settings,
        idea: '想法',
        images: [image],
        cancelToken: token,
      ),
      throwsA(
        isA<NoteApiException>().having((e) => e.cancelled, 'cancelled', isTrue),
      ),
    );
    expect(invoked, isFalse);
  });

  test('explains timeout and authentication failures', () async {
    dio.httpClientAdapter = _Adapter((options, stream, cancel) async {
      throw DioException.receiveTimeout(
        timeout: const Duration(minutes: 12),
        requestOptions: options,
      );
    });
    await expectLater(
      service.generate(
        settings: settings,
        idea: '想法',
        images: [image],
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'message',
          contains('超时'),
        ),
      ),
    );
    dio.httpClientAdapter = _Adapter(
      (_, stream, cancel) async => _json({}, 401),
    );
    await expectLater(
      service.generate(
        settings: settings,
        idea: '想法',
        images: [image],
        cancelToken: CancelToken(),
      ),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'message',
          contains('API Key'),
        ),
      ),
    );
  });

  test('validates count and idea limits before upload', () async {
    await expectLater(
      service.buildFormData(idea: '日常', images: []),
      throwsA(isA<NoteApiException>()),
    );
    await expectLater(
      service.buildFormData(idea: '日常', images: List.filled(21, image)),
      throwsA(isA<NoteApiException>()),
    );
    await expectLater(
      service.buildFormData(idea: ' ', images: [image]),
      throwsA(isA<NoteApiException>()),
    );
    await expectLater(
      service.buildFormData(idea: '字' * 2001, images: [image]),
      throwsA(isA<NoteApiException>()),
    );
    expect(
      (await service.buildFormData(
        idea: '🌸' * 2000,
        images: [image],
      )).fields.single.value.runes.length,
      2000,
    );
  });

  test('rejects large image and total payload before upload', () async {
    final file = await File('${directory.path}/large.jpg')
        .open(mode: FileMode.write);
    await file.truncate(10 * 1024 * 1024 + 1);
    await file.close();
    final large = XFile('${directory.path}/large.jpg');
    await expectLater(
      service.buildFormData(idea: '日常', images: [large]),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'message',
          contains('10 MiB'),
        ),
      ),
    );
    final smaller = await File('${directory.path}/smaller.jpg')
        .open(mode: FileMode.write);
    await smaller.truncate(9 * 1024 * 1024);
    await smaller.close();
    await expectLater(
      service.buildFormData(
        idea: '日常',
        images: List.filled(6, XFile('${directory.path}/smaller.jpg')),
      ),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'message',
          contains('50 MiB'),
        ),
      ),
    );
  });

  test('handles image removed from filesystem', () async {
    await File(image.path).delete();
    await expectLater(
      service.buildFormData(idea: '日常', images: [image]),
      throwsA(
        isA<NoteApiException>().having(
          (e) => e.message,
          'message',
          contains('重新选择'),
        ),
      ),
    );
  });

  test('rejects duplicate and invalid image references', () {
    for (final order in [
      ['img_0', 'img_0'],
      ['img_0'],
      ['img_0', 'img_2'],
      ['photo_0', 'img_1'],
    ]) {
      expect(
        () => GeneratedNote.fromResponse(_note(order: order)).imageIndices(2),
        throwsFormatException,
      );
    }
    expect(
      () => GeneratedNote.fromResponse({
        'code': 0,
        'data': {'title': '', 'content': '正文'},
      }),
      throwsFormatException,
    );
  });

  test('server URL permits root http/https only', () {
    for (final url in [
      'localhost:8072',
      'ftp://example.com',
      'http://user:password@example.com',
      'http://localhost:8072/api',
      'https://example.com?key=secret',
    ]) {
      expect(ServiceSettings.validateBaseUrl(url), isNotNull);
    }
    expect(ServiceSettings.validateBaseUrl('http://192.168.1.2:8072/'), isNull);
    expect(ServiceSettings.validateBaseUrl('https://example.com'), isNull);
  });
}
