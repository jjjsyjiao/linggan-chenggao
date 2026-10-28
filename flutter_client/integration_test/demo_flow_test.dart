// Run against a real server started with APP_XHS_DEMO_MODE=true.
// The image picker alone is substituted; HTTP, decoding, navigation and editing
// use the production implementation. This test never opens or publishes to XHS.
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:integration_test/integration_test.dart';
import 'package:linggan_chenggao/main.dart';
import 'package:linggan_chenggao/services/note_share_service.dart';

class _FixturePicker extends ImagePicker {
  _FixturePicker(this.files);

  final List<XFile> files;

  @override
  Future<List<XFile>> pickMultiImage({
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    int? limit,
    bool requestFullMetadata = true,
  }) async => files;

  @override
  Future<LostDataResponse> retrieveLostData() async => LostDataResponse.empty();
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('real multipart upload produces an editable demo note', (
    tester,
  ) async {
    final directory = await Directory.systemTemp.createTemp('xhs_mobile_e2e_');
    final pixel = await _fixtureImage();
    final first = File('${directory.path}/first.png');
    final second = File('${directory.path}/second.png');
    await first.writeAsBytes(pixel);
    await second.writeAsBytes(pixel);

    await tester.pumpWidget(
      LingganApp(
        imagePicker: _FixturePicker([XFile(first.path), XFile(second.path)]),
      ),
    );
    await tester.pumpAndSettle();
    if (Platform.isAndroid) {
      await binding.convertFlutterSurfaceToImage();
      await tester.pumpAndSettle();
    }
    await binding.takeScreenshot('${Platform.operatingSystem}_creation_home');
    await tester.tap(find.text('从相册挑选图片'));
    await tester.pumpAndSettle();
    expect(find.text('2 / 20'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('idea_input')));
    await tester.enterText(
      find.byKey(const Key('idea_input')),
      '记录周末的生活灵感，用自然真诚的语气分享。',
    );
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('generate_button')));

    // A bounded polling loop allows real network I/O to progress.
    for (var attempt = 0; attempt < 120; attempt++) {
      await tester.pump(const Duration(milliseconds: 250));
      if (find.byKey(const Key('demo_notice')).evaluate().isNotEmpty) break;
      if (find.byKey(const Key('generation_error')).evaluate().isNotEmpty) {
        final messages = tester
            .widgetList<Text>(find.byType(Text))
            .map((text) => text.data)
            .whereType<String>()
            .join('\n');
        fail('Backend request failed:\n$messages');
      }
    }
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('demo_notice')), findsOneWidget);
    await binding.takeScreenshot(
      '${Platform.operatingSystem}_demo_note_preview',
    );
    final pageScroll = find
        .byWidgetPredicate(
          (widget) =>
              widget is Scrollable &&
              widget.axisDirection == AxisDirection.down,
        )
        .first;
    await tester.scrollUntilVisible(
      find.byKey(const Key('note_title')),
      200,
      scrollable: pageScroll,
    );
    expect(find.byKey(const Key('note_title')), findsOneWidget);
    final title = tester.widget<TextField>(find.byKey(const Key('note_title')));
    expect(title.controller!.text, isNotEmpty);

    await tester.ensureVisible(find.byKey(const Key('note_title')));
    await tester.enterText(find.byKey(const Key('note_title')), '手动修改后的标题');
    expect(title.controller!.text, '手动修改后的标题');
    await tester.scrollUntilVisible(
      find.byKey(const Key('note_content')),
      200,
      scrollable: pageScroll,
    );
    await tester.enterText(find.byKey(const Key('note_content')), '我补充的真实体验。');
    final body = tester.widget<TextField>(
      find.byKey(const Key('note_content')),
    );
    expect(body.controller!.text, '我补充的真实体验。');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    await binding.takeScreenshot('${Platform.operatingSystem}_edited_note');
    expect(tester.takeException(), isNull);

    // Android returns after opening its receiver/chooser. On iOS the share
    // sheet awaits user dismissal, which is verified separately in Simulator.
    if (Platform.isAndroid) {
      final outcome = await const PlatformNoteShareService().shareImages([
        XFile(first.path),
        XFile(second.path),
      ], origin: const Rect.fromLTWH(20, 20, 120, 50));
      expect(outcome.status, ShareStatus.launched);
    }

    await tester.pumpWidget(const SizedBox.shrink());
    await directory.delete(recursive: true);
  });
}

Future<Uint8List> _fixtureImage() async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    const Rect.fromLTWH(0, 0, 640, 800),
    Paint()..color = const Color(0xFFF7E8D7),
  );
  canvas.drawCircle(
    const Offset(460, 260),
    170,
    Paint()..color = const Color(0xFFEFA28C),
  );
  canvas.drawRRect(
    RRect.fromRectAndRadius(
      const Rect.fromLTWH(80, 350, 310, 340),
      const Radius.circular(40),
    ),
    Paint()..color = const Color(0xFF85957C),
  );
  final painter = TextPainter(
    text: const TextSpan(
      text: 'DEMO\nLITTLE MOMENTS',
      style: TextStyle(
        color: Color(0xFF38312B),
        fontSize: 32,
        fontWeight: FontWeight.bold,
        height: 1.6,
      ),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  painter.paint(canvas, const Offset(60, 70));
  final picture = recorder.endRecording();
  final image = await picture.toImage(640, 800);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  picture.dispose();
  painter.dispose();
  return data!.buffer.asUint8List();
}
