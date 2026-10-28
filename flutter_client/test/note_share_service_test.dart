import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:linggan_chenggao/services/note_share_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/xhs_notes/share');
  const service = PlatformNoteShareService(channel: channel);
  const origin = Rect.fromLTWH(12, 24, 160, 48);
  final images = <XFile>[XFile('/tmp/one.jpg'), XFile('/tmp/two.png')];

  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
    debugDefaultTargetPlatformOverride = null;
  });

  test('sends only image paths and the iPad popover origin', () async {
    MethodCall? received;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          received = call;
          return <String, String>{
            'status': 'launched',
            'destination': 'xiaohongshu',
          };
        });

    final outcome = await service.shareImages(images, origin: origin);

    expect(received?.method, 'shareImages');
    expect(received?.arguments, <String, Object>{
      'paths': <String>['/tmp/one.jpg', '/tmp/two.png'],
      'origin': <String, double>{'x': 12, 'y': 24, 'width': 160, 'height': 48},
    });
    expect(outcome.status, ShareStatus.launched);
    expect(outcome.destination, ShareDestination.xiaohongshu);
  });

  test(
    'preserves system-share cancellation without treating it as success',
    () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (_) async {
            return <String, String>{
              'status': 'cancelled',
              'destination': 'system',
            };
          });

      final outcome = await service.shareImages(images, origin: origin);

      expect(outcome.status, ShareStatus.cancelled);
      expect(outcome.destination, ShareDestination.system);
    },
  );

  test('surfaces native permission and file errors to the caller', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          throw PlatformException(code: 'invalid_image', message: '图片已被删除。');
        });

    await expectLater(
      service.shareImages(images, origin: origin),
      throwsA(
        isA<PlatformException>().having(
          (error) => error.code,
          'code',
          'invalid_image',
        ),
      ),
    );
  });

  test('rejects an invalid native response', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async => null);

    await expectLater(
      service.shareImages(images, origin: origin),
      throwsA(isA<PlatformException>()),
    );
  });

  test('rejects empty selection and invalid popover coordinates', () async {
    await expectLater(
      service.shareImages(<XFile>[], origin: origin),
      throwsArgumentError,
    );
    await expectLater(
      service.shareImages(images, origin: Rect.zero),
      throwsArgumentError,
    );
  });

  test('gives a clear error on unsupported desktop platforms', () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.macOS;

    await expectLater(
      service.shareImages(images, origin: origin),
      throwsUnsupportedError,
    );
  });
}
