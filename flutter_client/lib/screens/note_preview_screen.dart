import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../models/generated_note.dart';
import '../services/note_share_service.dart';
import '../widgets/photo_preview.dart';
import '../widgets/workflow_steps.dart';

class NotePreviewScreen extends StatefulWidget {
  const NotePreviewScreen({
    super.key,
    required this.note,
    required this.images,
    required this.shareService,
  });

  final GeneratedNote note;
  final List<XFile> images;
  final NoteShareService shareService;

  @override
  State<NotePreviewScreen> createState() => _NotePreviewScreenState();
}

class _NotePreviewScreenState extends State<NotePreviewScreen> {
  late final _title = TextEditingController(text: widget.note.title);
  late final _content = TextEditingController(text: widget.note.content);
  late final _tags = TextEditingController(
    text: widget.note.tags.map((tag) => '#$tag').join(' '),
  );
  final _pages = PageController();
  final _shareButton = GlobalKey();
  int _imageIndex = 0;
  bool _sharing = false;
  String? _shareMessage;

  @override
  void initState() {
    super.initState();
    _title.addListener(_refresh);
    _content.addListener(_refresh);
    _tags.addListener(_refresh);
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _title.dispose();
    _content.dispose();
    _tags.dispose();
    _pages.dispose();
    super.dispose();
  }

  String get _bodyWithTags {
    final body = _content.text.trim();
    final tags = _tags.text
        .split(RegExp(r'[\s,，]+'))
        .map((tag) => tag.replaceFirst(RegExp(r'^#+'), '').trim())
        .where((tag) => tag.isNotEmpty)
        .toSet()
        .where(
          (tag) => !RegExp(
            '(?:^|\\s)#${RegExp.escape(tag)}(?:\\s|\$)',
          ).hasMatch(body),
        )
        .map((tag) => '#$tag')
        .join(' ');
    return tags.isEmpty ? body : '$body\n\n$tags';
  }

  String get _wholeNote => '${_title.text.trim()}\n\n$_bodyWithTags';

  int get _titleLength => _title.text.runes.length;
  int get _bodyLength => _bodyWithTags.runes.length;

  Future<void> _copy(String value, String message) async {
    try {
      await Clipboard.setData(ClipboardData(text: value));
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
      }
    } on PlatformException {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('未能复制，请稍后重试')));
      }
    }
  }

  Future<void> _share() async {
    if (_sharing) return;
    if (_title.text.trim().isEmpty || _content.text.trim().isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请先填写标题和正文')));
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    final box = _shareButton.currentContext?.findRenderObject() as RenderBox?;
    final origin = box == null
        ? const Rect.fromLTWH(0, 0, 1, 1)
        : box.localToGlobal(Offset.zero) & box.size;
    setState(() {
      _sharing = true;
      _shareMessage = null;
    });
    try {
      await Clipboard.setData(ClipboardData(text: _wholeNote));
      final outcome = await widget.shareService.shareImages(
        widget.images,
        origin: origin,
      );
      if (!mounted) return;
      final message = switch (outcome.status) {
        ShareStatus.cancelled => '已关闭分享。整篇文案仍在剪贴板中，可以再次分享。',
        ShareStatus.completed => '分享流程已完成。请在小红书检查图片，并手动粘贴标题和正文后发布。',
        ShareStatus.launched =>
          outcome.destination == ShareDestination.xiaohongshu
              ? '已唤起小红书。请检查图片，再从剪贴板粘贴文案，确认后发布。'
              : '已打开系统分享。请选择小红书，再从剪贴板粘贴文案，确认后发布。',
      };
      setState(() => _shareMessage = message);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 6)),
      );
    } on PlatformException catch (error) {
      if (mounted) {
        setState(
          () => _shareMessage =
              error.message ?? '无法打开分享。请确认已安装小红书；也可以复制文案后手动选择图片发布。',
        );
      }
    } on MissingPluginException {
      if (mounted) {
        setState(
          () => _shareMessage =
              '当前运行环境没有移动端分享能力。请在 Android 或 iOS 设备上使用，或复制文案后手动发布。',
        );
      }
    } catch (_) {
      if (mounted) {
        setState(() => _shareMessage = '暂时无法分享图片。文案已复制，可打开小红书手动添加图片并粘贴文案。');
      }
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_sharing,
    child: Scaffold(
      appBar: AppBar(
        title: const Text(
          '笔记预览',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),
        actions: [
          TextButton(
            onPressed: () => _copy(_wholeNote, '已复制整篇笔记'),
            child: const Text('复制整篇'),
          ),
          const SizedBox(width: 6),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(22, 16, 22, 28),
            children: [
              const WorkflowSteps(current: 2),
              const SizedBox(height: 26),
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(7),
                    decoration: BoxDecoration(
                      color: widget.note.reviewWarnings.isEmpty
                          ? const Color(0xFFF0F3E8)
                          : const Color(0xFFFFE3BA),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      widget.note.reviewWarnings.isEmpty
                          ? Icons.check_rounded
                          : Icons.info_outline_rounded,
                      color: Color(0xFF7A8B59),
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      widget.note.reviewWarnings.isEmpty
                          ? '你的灵感，已经成稿'
                          : '有待核对的草稿',
                      style: const TextStyle(
                        fontSize: 21,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                widget.note.reviewWarnings.isEmpty
                    ? '再加一点你的语气，让它更像你。'
                    : '请对照图片和实际情况修改，再自行确认发布。',
                style: const TextStyle(color: Color(0xFF9B8C80), fontSize: 13),
              ),
              if (widget.note.isDemo) ...[
                const SizedBox(height: 16),
                Container(
                  key: const Key('demo_notice'),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFE3BA),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.science_outlined,
                        size: 20,
                        color: Color(0xFF9B5A10),
                      ),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '演示结果：未调用 AI 模型\n此内容仅用于验证选图、生成和分享流程。',
                          style: TextStyle(
                            fontSize: 13,
                            height: 1.6,
                            color: Color(0xFF91520E),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ] else if (widget.note.reviewWarnings.isEmpty) ...[
                const SizedBox(height: 16),
                Container(
                  key: const Key('draft_notice'),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF5EFE7),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Text(
                    'AI 创作草稿 · 请核对图片细节与事实，删去未发生的经历和效果描述。',
                    style: TextStyle(
                      fontSize: 12,
                      height: 1.7,
                      color: Color(0xFF8D7B6D),
                    ),
                  ),
                ),
              ],
              if (widget.note.reviewWarnings.isNotEmpty) ...[
                const SizedBox(height: 16),
                Container(
                  key: const Key('review_notice'),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFEFD9),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'AI 草稿仍需人工核对',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF91520E),
                        ),
                      ),
                      const SizedBox(height: 6),
                      for (final warning in widget.note.reviewWarnings)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            '• $warning',
                            style: const TextStyle(
                              fontSize: 12,
                              height: 1.7,
                              color: Color(0xFF91520E),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 24),
              ClipRRect(
                borderRadius: BorderRadius.circular(22),
                child: AspectRatio(
                  aspectRatio: 1.05,
                  child: Stack(
                    children: [
                      PageView.builder(
                        controller: _pages,
                        itemCount: widget.images.length,
                        onPageChanged: (index) =>
                            setState(() => _imageIndex = index),
                        itemBuilder: (context, index) => GestureDetector(
                          onTap: () =>
                              showPhotoPreview(context, widget.images, index),
                          child: SizedBox.expand(
                            child: PhotoThumbnail(
                              image: widget.images[index],
                              decodeSize: 1080,
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        top: 14,
                        left: 14,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            _imageIndex == 0 ? '封面图' : '笔记配图',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        bottom: 14,
                        right: 14,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            '${_imageIndex + 1} / ${widget.images.length}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (widget.images.length > 1) ...[
                const SizedBox(height: 12),
                SizedBox(
                  height: 62,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: widget.images.length,
                    separatorBuilder: (context, index) =>
                        const SizedBox(width: 8),
                    itemBuilder: (context, index) => GestureDetector(
                      onTap: () => _pages.animateToPage(
                        index,
                        duration: const Duration(milliseconds: 240),
                        curve: Curves.easeOut,
                      ),
                      child: Container(
                        width: 62,
                        padding: const EdgeInsets.all(2),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: index == _imageIndex
                                ? const Color(0xFFE65E51)
                                : Colors.transparent,
                            width: 2,
                          ),
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: PhotoThumbnail(image: widget.images[index]),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 24),
              _fieldHeading('笔记标题', () => _copy(_title.text.trim(), '标题已复制')),
              const SizedBox(height: 10),
              TextField(
                key: const Key('note_title'),
                controller: _title,
                enabled: !_sharing,
                maxLines: 3,
                minLines: 1,
                decoration: InputDecoration(
                  hintText: '写一个让人想点开的标题',
                  helperText: _titleLength > 20
                      ? '$_titleLength / 20 字 · 标题偏长，建议精简后发布'
                      : '$_titleLength / 20 字 · 可自由编辑',
                  helperMaxLines: 2,
                  helperStyle: _titleLength > 20
                      ? const TextStyle(
                          color: Color(0xFFC24538),
                          fontWeight: FontWeight.w600,
                        )
                      : null,
                ),
                style: const TextStyle(
                  fontSize: 19,
                  fontWeight: FontWeight.w700,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 22),
              _fieldHeading('笔记正文', () => _copy(_bodyWithTags, '正文和话题已复制')),
              const SizedBox(height: 10),
              TextField(
                key: const Key('note_content'),
                controller: _content,
                enabled: !_sharing,
                minLines: 7,
                maxLines: null,
                decoration: InputDecoration(
                  hintText: '分享你想记录的细节…',
                  helperText: _bodyLength > 1000
                      ? '$_bodyLength / 1000 字（含话题）· 正文偏长，建议精简后发布'
                      : '$_bodyLength / 1000 字（含话题）· 发布前请核对内容',
                  helperMaxLines: 2,
                  helperStyle: _bodyLength > 1000
                      ? const TextStyle(
                          color: Color(0xFFC24538),
                          fontWeight: FontWeight.w600,
                        )
                      : null,
                ),
                style: const TextStyle(fontSize: 15, height: 1.8),
              ),
              const SizedBox(height: 22),
              const Text(
                '话题标签',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const Key('note_tags'),
                controller: _tags,
                enabled: !_sharing,
                minLines: 1,
                maxLines: 3,
                style: const TextStyle(
                  color: Color(0xFFB76147),
                  height: 1.7,
                  fontSize: 14,
                ),
                decoration: const InputDecoration(
                  hintText: '#日常灵感 #生活记录',
                  helperText: '用空格分隔，复制正文时会一起带上',
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '字数为创作建议，实际发布规则以小红书发布页为准。',
                style: TextStyle(
                  fontSize: 11,
                  height: 1.6,
                  color: Color(0xFFA5988A),
                ),
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: const Color(0xFFF5EFE7),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(
                          Icons.near_me_outlined,
                          size: 19,
                          color: Color(0xFF9D7760),
                        ),
                        SizedBox(width: 9),
                        Text(
                          '距离分享，只差一步',
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 14,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '1  点击下方按钮，整篇文案会先复制到剪贴板\n2  分享图片到小红书（iPhone 请在分享面板选择）\n3  手动粘贴标题与正文，检查后在小红书确认发布',
                      style: TextStyle(
                        fontSize: 12,
                        height: 1.9,
                        color: Color(0xFF927F6F),
                      ),
                    ),
                    if (_shareMessage != null) ...[
                      const SizedBox(height: 14),
                      Text(
                        _shareMessage!,
                        key: const Key('share_message'),
                        style: const TextStyle(
                          color: Color(0xFFB65B43),
                          fontSize: 13,
                          height: 1.7,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (widget.note.requestId != null)
                Padding(
                  padding: const EdgeInsets.only(top: 18),
                  child: Text(
                    '请求编号 ${widget.note.requestId}',
                    style: const TextStyle(
                      fontSize: 10,
                      color: Color(0xFFB6AA9D),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.fromLTRB(22, 14, 22, 10),
          decoration: const BoxDecoration(
            color: Color(0xFFFFFCF8),
            border: Border(top: BorderSide(color: Color(0xFFF0E9E0))),
          ),
          child: Center(
            heightFactor: 1,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 716),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      key: _shareButton,
                      onPressed: _sharing ? null : _share,
                      icon: _sharing
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.ios_share_rounded, size: 19),
                      label: Text(_sharing ? '正在打开分享…' : '复制文案并分享图片'),
                    ),
                  ),
                  const SizedBox(height: 9),
                  const Text(
                    '发布由你确认 · 不会自动发布到账号',
                    style: TextStyle(fontSize: 10, color: Color(0xFFADA093)),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );

  Widget _fieldHeading(String title, VoidCallback copy) => Row(
    children: [
      Text(
        title,
        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
      ),
      const Spacer(),
      InkWell(
        onTap: copy,
        borderRadius: BorderRadius.circular(8),
        child: const Padding(
          padding: EdgeInsets.all(5),
          child: Row(
            children: [
              Icon(Icons.copy_outlined, size: 14, color: Color(0xFFAE8A73)),
              SizedBox(width: 5),
              Text(
                '复制',
                style: TextStyle(fontSize: 12, color: Color(0xFFAE8A73)),
              ),
            ],
          ),
        ),
      ),
    ],
  );
}
