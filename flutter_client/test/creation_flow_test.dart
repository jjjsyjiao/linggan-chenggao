import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:linggan_chenggao/main.dart';
import 'package:linggan_chenggao/models/generated_note.dart';
import 'package:linggan_chenggao/models/service_settings.dart';
import 'package:linggan_chenggao/services/note_api_service.dart';
import 'package:linggan_chenggao/services/note_share_service.dart';

class _Picker extends ImagePicker {
  _Picker(this.images);
  final List<XFile> images;
  int singleCalls = 0;
  int multiCalls = 0;

  @override
  Future<List<XFile>> pickMultiImage({
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    int? limit,
    bool requestFullMetadata = true,
  }) async {
    multiCalls++;
    return images;
  }

  @override
  Future<XFile?> pickImage({
    required ImageSource source,
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    CameraDevice preferredCameraDevice = CameraDevice.rear,
    bool requestFullMetadata = true,
  }) async {
    singleCalls++;
    expect(source, ImageSource.gallery);
    return images.first;
  }
}

class _Api extends NoteApiService {
  bool waitForCancellation = false;
  bool demo = true;
  bool fail = false;
  List<String> reviewWarnings = const [];
  int calls = 0;
  List<XFile>? uploadedImages;
  final requests =
      <({ServiceSettings settings, String idea, List<XFile> images})>[];
  final notesByIdea = <String, GeneratedNote>{};
  @override
  Future<GeneratedNote> generate({
    required ServiceSettings settings,
    required String idea,
    required List<XFile> images,
    required CancelToken cancelToken,
    ProgressCallback? onSendProgress,
  }) async {
    calls++;
    uploadedImages = images;
    requests.add((
      settings: settings,
      idea: idea,
      images: List<XFile>.of(images),
    ));
    onSendProgress?.call(1, 1);
    if (waitForCancellation) {
      await cancelToken.whenCancel;
      throw const NoteApiException('已取消', cancelled: true);
    }
    if (fail) throw const NoteApiException('模型服务暂不可用', requestId: 'error-id');
    if (notesByIdea[idea] case final note?) return note;
    return GeneratedNote(
      title: '周末的小确幸',
      content: '阳光正好，记录生活。',
      tags: const ['生活记录'],
      imageOrder: List.generate(
        images.length,
        (index) => 'img_${images.length - index - 1}',
      ),
      isDemo: demo,
      reviewWarnings: reviewWarnings,
    );
  }
}

class _Share implements NoteShareService {
  List<XFile>? images;
  Rect? origin;
  @override
  Future<ShareOutcome> shareImages(
    List<XFile> images, {
    required Rect origin,
  }) async {
    this.images = images;
    this.origin = origin;
    return const ShareOutcome(
      status: ShareStatus.launched,
      destination: ShareDestination.system,
    );
  }
}

void main() {
  late Directory directory;
  late List<XFile> images;
  late _Picker picker;
  late _Api api;
  late _Share share;
  String? clipboard;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('linggan-widget-test-');
    images = [];
    for (var i = 0; i < 2; i++) {
      final file = await File('${directory.path}/photo_$i.png').writeAsBytes(
        base64Decode(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8i0AAAAASUVORK5CYII=',
        ),
      );
      images.add(XFile(file.path));
    }
    picker = _Picker(images);
    api = _Api();
    share = _Share();
    clipboard = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
          if (call.method == 'Clipboard.setData') {
            clipboard = (call.arguments as Map)['text'] as String;
          }
          return null;
        });
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null);
    await directory.delete(recursive: true);
  });

  Future<void> open(WidgetTester tester) async {
    tester.view.resetPhysicalSize();
    tester.view.physicalSize = const Size(430, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    await tester.pumpWidget(
      LingganApp(apiService: api, shareService: share, imagePicker: picker),
    );
    await tester.pumpAndSettle();
  }

  Future<void> selectAndWrite(WidgetTester tester) async {
    await tester.tap(find.text('从相册挑选图片'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('idea_input')));
    await tester.enterText(find.byKey(const Key('idea_input')), '分享周末咖啡探店');
    await tester.pump();
  }

  testWidgets(
    'picks images, generates reordered preview, edits and copies before sharing',
    (tester) async {
      await open(tester);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('generate_button')))
            .onPressed,
        isNull,
      );
      await selectAndWrite(tester);
      expect(picker.multiCalls, 1);
      await tester.tap(find.byKey(const Key('generate_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('demo_notice')), findsOneWidget);
      expect(find.byKey(const Key('draft_notice')), findsNothing);
      expect(find.text('笔记预览'), findsOneWidget);
      await tester.ensureVisible(find.byKey(const Key('note_title')));
      await tester.enterText(find.byKey(const Key('note_title')), '我的真实标题');
      await tester.ensureVisible(find.byKey(const Key('note_content')));
      await tester.enterText(find.byKey(const Key('note_content')), '补充真实的体验。');
      await tester.tap(find.text('复制文案并分享图片'));
      await tester.pumpAndSettle();
      expect(clipboard, '我的真实标题\n\n补充真实的体验。\n\n#生活记录');
      expect(
        share.images!.map((image) => image.path),
        images.reversed.map((image) => image.path),
      );
      expect(share.origin!.width, greaterThan(0));
      expect(find.textContaining('已打开系统分享'), findsWidgets);
    },
  );

  testWidgets(
    'regenerates the same images with the complete edited idea and a fresh draft',
    (tester) async {
      const firstIdea = '给这组菊花写一段温柔的观花日记。\n不要地点、时间和养护建议。';
      const secondIdea = '换成简洁的摄影观察，分两点写花瓣和构图，不写抒情句。';
      final firstNote = GeneratedNote(
        title: '把秋意藏进菊花里',
        content: '层叠花瓣接住了目光，留下一页温柔的花间手记。',
        tags: const ['观花手记'],
        imageOrder: const ['img_0', 'img_1'],
        isDemo: false,
      );
      final secondNote = GeneratedNote(
        title: '菊花花瓣与构图观察',
        content: '一、观察层叠花瓣的排列。\n二、留意主体与背景的关系。',
        tags: const ['花卉摄影'],
        imageOrder: const ['img_0', 'img_1'],
        isDemo: false,
      );
      api.notesByIdea.addAll({firstIdea: firstNote, secondIdea: secondNote});
      await open(tester);
      await selectAndWrite(tester);
      await tester.enterText(find.byKey(const Key('idea_input')), firstIdea);
      await tester.tap(find.byKey(const Key('generate_button')));
      await tester.pumpAndSettle();

      Future<void> expectDraft(GeneratedNote note) async {
        for (final entry in {
          'note_title': note.title,
          'note_content': note.content,
          'note_tags': note.tags.map((tag) => '#$tag').join(' '),
        }.entries) {
          final field = find.byKey(Key(entry.key));
          await tester.ensureVisible(field);
          await tester.pumpAndSettle();
          expect(tester.widget<TextField>(field).controller!.text, entry.value);
        }
      }

      await expectDraft(firstNote);
      // A local edit in the first preview must not leak into the next response.
      await tester.ensureVisible(find.byKey(const Key('note_title')));
      await tester.enterText(find.byKey(const Key('note_title')), '第一版手工修改的标题');
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.text('2 / 20'), findsOneWidget);
      await tester.ensureVisible(find.byKey(const Key('idea_input')));
      expect(
        tester
            .widget<TextField>(find.byKey(const Key('idea_input')))
            .controller!
            .text,
        firstIdea,
      );
      await tester.enterText(find.byKey(const Key('idea_input')), secondIdea);
      await tester.ensureVisible(find.byKey(const Key('generate_button')));
      await tester.tap(find.byKey(const Key('generate_button')));
      await tester.pumpAndSettle();

      expect(api.calls, 2);
      expect(api.requests.map((request) => request.idea), [
        firstIdea,
        secondIdea,
      ]);
      for (final request in api.requests) {
        expect(
          request.images.map((image) => image.path),
          images.map((image) => image.path),
        );
      }
      expect(picker.multiCalls, 1);
      await expectDraft(secondNote);
      expect(find.text(firstNote.title), findsNothing);
      expect(find.text(firstNote.content), findsNothing);
      expect(find.text('#观花手记'), findsNothing);
      expect(find.text('第一版手工修改的标题'), findsNothing);
    },
  );

  testWidgets(
    'long edits remain intact and warn using title and body-with-tags rune counts',
    (tester) async {
      await open(tester);
      await selectAndWrite(tester);
      await tester.tap(find.byKey(const Key('generate_button')));
      await tester.pumpAndSettle();
      final title = '🌸' * 21;
      final body = '字' * 995;
      await tester.ensureVisible(find.byKey(const Key('note_title')));
      await tester.enterText(find.byKey(const Key('note_title')), title);
      await tester.pump();
      final titleField = tester.widget<TextField>(
        find.byKey(const Key('note_title')),
      );
      expect(titleField.controller!.text, title);
      expect(titleField.decoration!.helperText, '21 / 20 字 · 标题偏长，建议精简后发布');
      expect(
        titleField.decoration!.helperStyle!.color,
        const Color(0xFFC24538),
      );
      await tester.ensureVisible(find.byKey(const Key('note_content')));
      await tester.enterText(find.byKey(const Key('note_content')), body);
      await tester.pump();
      final bodyField = tester.widget<TextField>(
        find.byKey(const Key('note_content')),
      );
      expect(bodyField.controller!.text, body);
      // The 995-character body exceeds the suggestion only after tags and spacing.
      expect(
        bodyField.decoration!.helperText,
        '1002 / 1000 字（含话题）· 正文偏长，建议精简后发布',
      );
      expect(bodyField.decoration!.helperStyle!.color, const Color(0xFFC24538));
      await tester.tap(find.text('复制文案并分享图片'));
      await tester.pumpAndSettle();
      expect(clipboard, '$title\n\n$body\n\n#生活记录');
      expect(share.images, isNotNull);
    },
  );

  testWidgets(
    'real generated notes show a draft reminder instead of a demo notice',
    (tester) async {
      api.demo = false;
      await open(tester);
      await selectAndWrite(tester);
      await tester.tap(find.byKey(const Key('generate_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('draft_notice')), findsOneWidget);
      expect(find.text('AI 创作草稿 · 请核对图片细节与事实，删去未发生的经历和效果描述。'), findsOneWidget);
      expect(find.byKey(const Key('demo_notice')), findsNothing);
      expect(find.byKey(const Key('review_notice')), findsNothing);
      expect(find.text('复制文案并分享图片'), findsOneWidget);
    },
  );

  testWidgets(
    'review warnings stay visible while editing and never enter copied or shared copy',
    (tester) async {
      api.demo = false;
      api.reviewWarnings = const ['请核对地点是否来自真实经历。', '花期信息需要核实。'];
      await open(tester);
      await selectAndWrite(tester);
      await tester.tap(find.byKey(const Key('generate_button')));
      await tester.pumpAndSettle();

      expect(find.text('有待核对的草稿'), findsOneWidget);
      expect(find.text('你的灵感，已经成稿'), findsNothing);
      expect(find.byKey(const Key('review_notice')), findsOneWidget);
      expect(find.text('• 请核对地点是否来自真实经历。'), findsOneWidget);
      expect(find.text('• 花期信息需要核实。'), findsOneWidget);
      expect(find.text('AI 草稿仍需人工核对'), findsOneWidget);
      expect(find.byKey(const Key('draft_notice')), findsNothing);

      await tester.ensureVisible(find.byKey(const Key('note_title')));
      await tester.enterText(find.byKey(const Key('note_title')), '修改后的菊花标题');
      await tester.ensureVisible(find.byKey(const Key('note_content')));
      await tester.enterText(
        find.byKey(const Key('note_content')),
        '只记录画面中的花瓣。',
      );
      await tester.ensureVisible(find.text('复制文案并分享图片'));
      await tester.tap(find.text('复制文案并分享图片'));
      await tester.pumpAndSettle();

      expect(clipboard, '修改后的菊花标题\n\n只记录画面中的花瓣。\n\n#生活记录');
      for (final warning in api.reviewWarnings) {
        expect(clipboard, isNot(contains(warning)));
      }
      expect(clipboard, isNot(contains('有待核对的草稿')));
      expect(share.images, isNotNull);
      expect(find.textContaining('已打开系统分享'), findsWidgets);
    },
  );

  testWidgets('single mode opens image-only gallery picker', (tester) async {
    await open(tester);
    await tester.tap(find.text('单张添加'));
    await tester.tap(find.text('从相册挑选图片'));
    await tester.pumpAndSettle();
    expect(picker.singleCalls, 1);
    expect(picker.multiCalls, 0);
    expect(find.text('1 / 20'), findsOneWidget);
  });

  testWidgets('cancels generation while retaining images and idea', (
    tester,
  ) async {
    api.waitForCancellation = true;
    await open(tester);
    await selectAndWrite(tester);
    await tester.tap(find.byKey(const Key('generate_button')));
    await tester.pump();
    expect(find.byKey(const Key('cancel_button')), findsOneWidget);
    await tester.tap(find.byKey(const Key('cancel_button')));
    await tester.pumpAndSettle();
    expect(find.text('已取消本次等待，你的图片和想法已保留'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('idea_input')))
          .controller!
          .text,
      '分享周末咖啡探店',
    );
    expect(find.text('2 / 20'), findsOneWidget);
    expect(find.text('笔记预览'), findsNothing);
  });

  testWidgets('shows genuine backend failure then supports retry', (
    tester,
  ) async {
    api.fail = true;
    await open(tester);
    await selectAndWrite(tester);
    await tester.tap(find.byKey(const Key('generate_button')));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).first, const Offset(0, -500));
    await tester.pumpAndSettle();
    expect(find.text('模型服务暂不可用'), findsOneWidget);
    expect(find.text('笔记预览'), findsNothing);
    api.fail = false;
    await tester.ensureVisible(find.text('重新生成'));
    await tester.tap(find.text('重新生成'));
    await tester.pumpAndSettle();
    expect(find.text('笔记预览'), findsOneWidget);
    expect(api.calls, 2);
  });
}
