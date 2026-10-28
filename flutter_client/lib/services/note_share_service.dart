import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

/// Android can confirm only that a receiving app was opened. A completed iOS
/// activity also does not confirm that a note was published on Xiaohongshu.
enum ShareStatus { launched, completed, cancelled }

enum ShareDestination { xiaohongshu, system }

class ShareOutcome {
  const ShareOutcome({required this.status, required this.destination});

  final ShareStatus status;
  final ShareDestination destination;
}

abstract class NoteShareService {
  const NoteShareService();

  /// Shares images only. The caller keeps title/body copying explicit in the UI.
  /// [origin] is the share button's rectangle in global Flutter coordinates.
  Future<ShareOutcome> shareImages(List<XFile> images, {required Rect origin});
}

class PlatformNoteShareService implements NoteShareService {
  const PlatformNoteShareService({
    MethodChannel channel = const MethodChannel('xhs_notes/share'),
  }) : _channel = channel;

  final MethodChannel _channel;

  @override
  Future<ShareOutcome> shareImages(
    List<XFile> images, {
    required Rect origin,
  }) async {
    if (images.isEmpty || images.any((image) => image.path.isEmpty)) {
      throw ArgumentError('请先选择需要分享的图片。');
    }
    if (!origin.left.isFinite ||
        !origin.top.isFinite ||
        !origin.width.isFinite ||
        !origin.height.isFinite ||
        origin.width <= 0 ||
        origin.height <= 0) {
      throw ArgumentError('分享按钮的位置无效，请重新尝试。');
    }
    if (kIsWeb ||
        (defaultTargetPlatform != TargetPlatform.android &&
            defaultTargetPlatform != TargetPlatform.iOS)) {
      throw UnsupportedError('图片分享目前支持 Android 和 iOS 客户端。');
    }

    final value = await _channel.invokeMapMethod<String, dynamic>(
      'shareImages',
      <String, dynamic>{
        'paths': images.map((image) => image.path).toList(growable: false),
        'origin': <String, double>{
          'x': origin.left,
          'y': origin.top,
          'width': origin.width,
          'height': origin.height,
        },
      },
    );
    final ShareStatus status;
    switch (value?['status']) {
      case 'launched':
        status = ShareStatus.launched;
      case 'completed':
        status = ShareStatus.completed;
      case 'cancelled':
        status = ShareStatus.cancelled;
      default:
        throw PlatformException(
          code: 'invalid_share_response',
          message: '系统未返回有效的分享结果。',
        );
    }
    return ShareOutcome(
      status: status,
      destination: value?['destination'] == 'xiaohongshu'
          ? ShareDestination.xiaohongshu
          : ShareDestination.system,
    );
  }
}
