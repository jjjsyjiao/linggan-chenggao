/// The editable note returned by the Python service.
class GeneratedNote {
  const GeneratedNote({
    required this.title,
    required this.content,
    required this.tags,
    required this.imageOrder,
    this.requestId,
    this.isDemo = false,
    this.reviewWarnings = const [],
  });

  final String title;
  final String content;
  final List<String> tags;
  final List<String> imageOrder;
  final String? requestId;
  final bool isDemo;
  final List<String> reviewWarnings;

  factory GeneratedNote.fromResponse(dynamic response) {
    if (response is! Map || response['code'] != 0) {
      throw const FormatException('服务返回的笔记格式不正确');
    }
    final data = response['data'];
    if (data is! Map ||
        data['title'] is! String ||
        data['content'] is! String ||
        (data['title'] as String).trim().isEmpty ||
        (data['content'] as String).trim().isEmpty) {
      throw const FormatException('服务没有返回完整的标题与正文');
    }
    final tags = data['tags'];
    final order = data['image_order'];
    if (tags is! List ||
        tags.any((value) => value is! String) ||
        order is! List ||
        order.any((value) => value is! String)) {
      throw const FormatException('服务返回的标签或图片顺序不正确');
    }
    final warnings = data.containsKey('review_warnings')
        ? data['review_warnings']
        : const <String>[];
    if (warnings is! List || warnings.any((value) => value is! String)) {
      throw const FormatException('服务返回的核对提示格式不正确');
    }
    return GeneratedNote(
      title: (data['title'] as String).trim(),
      content: (data['content'] as String).trim(),
      tags: List<String>.unmodifiable(
        tags
            .cast<String>()
            .map((tag) => tag.replaceFirst(RegExp(r'^#+'), '').trim())
            .where((tag) => tag.isNotEmpty),
      ),
      imageOrder: List<String>.unmodifiable(order.cast<String>()),
      requestId: response['request_id'] is String
          ? response['request_id'] as String
          : null,
      isDemo: data['is_demo'] == true,
      reviewWarnings: List<String>.unmodifiable(
        warnings
            .cast<String>()
            .map((warning) => warning.trim())
            .where((warning) => warning.isNotEmpty),
      ),
    );
  }

  /// Each uploaded image must occur exactly once; never silently drop pictures.
  List<int> imageIndices(int imageCount) {
    final indices = imageOrder.map((id) {
      final match = RegExp(r'^img_(\d+)$').firstMatch(id);
      return match == null ? -1 : int.parse(match.group(1)!);
    }).toList();
    if (indices.length != imageCount ||
        indices.toSet().length != imageCount ||
        indices.any((index) => index < 0 || index >= imageCount)) {
      throw const FormatException('服务返回的图片顺序不完整，请重试');
    }
    return indices;
  }
}
