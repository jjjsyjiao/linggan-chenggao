import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../models/service_settings.dart';
import '../services/note_api_service.dart';
import '../services/note_share_service.dart';
import '../widgets/photo_preview.dart';
import '../widgets/workflow_steps.dart';
import 'note_preview_screen.dart';
import 'service_settings_sheet.dart';

class CreationScreen extends StatefulWidget {
  const CreationScreen({
    super.key,
    required this.apiService,
    required this.shareService,
    this.imagePicker,
  });

  final NoteApiService apiService;
  final NoteShareService shareService;
  final ImagePicker? imagePicker;

  @override
  State<CreationScreen> createState() => _CreationScreenState();
}

class _CreationScreenState extends State<CreationScreen> {
  final _idea = TextEditingController();
  late final _picker = widget.imagePicker ?? ImagePicker();
  final List<XFile> _images = [];
  ServiceSettings _settings = ServiceSettings.defaults();
  bool _multiSelect = true;
  bool _picking = false;
  bool _busy = false;
  double _progress = 0;
  int _seconds = 0;
  Timer? _timer;
  CancelToken? _cancelToken;
  NoteApiException? _error;

  @override
  void initState() {
    super.initState();
    _idea.addListener(_refresh);
    if (Platform.isAndroid) _recoverLostImages();
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    _cancelToken?.cancel('screen disposed');
    _idea.dispose();
    super.dispose();
  }

  void _message(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _recoverLostImages() async {
    try {
      final response = await _picker.retrieveLostData();
      if (!mounted || response.isEmpty) return;
      if (response.files?.isNotEmpty == true) {
        _acceptImages(response.files!);
        _message('已恢复上次从相册选择的图片，请补充创作想法');
      } else if (response.exception != null) {
        _message('上次选择图片未完成，请重新打开相册');
      }
    } on PlatformException {
      // No draft exists yet; the picker remains available for a fresh selection.
    }
  }

  void _acceptImages(List<XFile> files) {
    final previousPaths = _images.map((file) => file.path).toSet();
    final incoming = files
        .where((file) => previousPaths.add(file.path))
        .toList();
    final remaining = 20 - _images.length;
    setState(() {
      _images.addAll(incoming.take(remaining));
      _error = null;
    });
    if (incoming.length > remaining) _message('最多选择 20 张图片，已保留前 20 张');
  }

  Future<void> _pickImages() async {
    if (_busy || _picking || _images.length >= 20) return;
    setState(() => _picking = true);
    try {
      final remaining = 20 - _images.length;
      // These APIs filter to images. Do not use pickMedia/pickMultipleMedia.
      if (_multiSelect && remaining > 1) {
        final files = await _picker.pickMultiImage(
          limit: remaining,
          requestFullMetadata: false,
        );
        if (mounted) _acceptImages(files);
      } else {
        final image = await _picker.pickImage(
          source: ImageSource.gallery,
          requestFullMetadata: false,
        );
        if (mounted && image != null) _acceptImages([image]);
      }
    } on PlatformException catch (error) {
      _message(
        error.code == 'photo_access_denied'
            ? '相册权限未开启，请在系统设置中允许访问图片'
            : '暂时无法打开相册，请稍后再试',
      );
    } catch (_) {
      _message('图片选择未完成，请重新选择');
    } finally {
      if (mounted) setState(() => _picking = false);
    }
  }

  Future<void> _editSettings() async {
    final settings = await showServiceSettings(context, _settings);
    if (settings != null && mounted) {
      setState(() {
        _settings = settings;
        _error = null;
      });
    }
  }

  void _moveImage(int index, int offset) {
    setState(() {
      final file = _images.removeAt(index);
      _images.insert(index + offset, file);
    });
  }

  Future<void> _generate() async {
    if (_busy || _images.isEmpty || _idea.text.trim().isEmpty) return;
    if (_idea.text.trim().runes.length > 2000) {
      _message('创作想法最多 2000 字，请精简后再试');
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    final images = List<XFile>.of(_images);
    final token = CancelToken();
    setState(() {
      _busy = true;
      _error = null;
      _progress = 0;
      _seconds = 0;
      _cancelToken = token;
    });
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _seconds++);
    });
    try {
      final note = await widget.apiService.generate(
        settings: _settings,
        idea: _idea.text,
        images: images,
        cancelToken: token,
        onSendProgress: (sent, total) {
          if (mounted && !token.isCancelled && total > 0) {
            setState(() => _progress = (sent / total).clamp(0, 1));
          }
        },
      );
      if (!mounted || token.isCancelled) return;
      final orderedImages = note
          .imageIndices(images.length)
          .map((index) => images[index])
          .toList();
      _timer?.cancel();
      setState(() => _busy = false);
      await Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => NotePreviewScreen(
            note: note,
            images: orderedImages,
            shareService: widget.shareService,
          ),
        ),
      );
    } on NoteApiException catch (error) {
      if (!mounted) return;
      if (error.cancelled) {
        _message('已取消本次等待，你的图片和想法已保留');
      } else {
        setState(() => _error = error);
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = const NoteApiException('生成未完成，请检查服务状态后重试'));
      }
    } finally {
      _timer?.cancel();
      if (mounted) {
        setState(() {
          _busy = false;
          _cancelToken = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final canGenerate =
        !_busy &&
        !_picking &&
        _images.isNotEmpty &&
        _idea.text.trim().isNotEmpty;
    return PopScope(
      canPop: !_busy,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop && _busy) _message('正在创作，可先点击「取消等待」');
      },
      child: Scaffold(
        appBar: AppBar(
          titleSpacing: 22,
          title: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                color: Color(0xFFE65E51),
                size: 25,
              ),
              SizedBox(width: 9),
              Text(
                '灵感成稿',
                style: TextStyle(
                  fontSize: 19,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1,
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              onPressed: _busy ? null : _editSettings,
              tooltip: '服务设置',
              icon: const Icon(Icons.tune_rounded),
            ),
            const SizedBox(width: 12),
          ],
        ),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(22, 18, 22, 28),
              children: [
                const Text(
                  'LITTLE MOMENTS, GREAT STORIES',
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 1.7,
                    color: Color(0xFFA29487),
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '生活有灵感，\n落笔就成篇。',
                  style: TextStyle(
                    fontSize: 32,
                    height: 1.35,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '挑几张喜欢的照片，把故事交给我们。',
                  style: TextStyle(color: Color(0xFF928579), fontSize: 14),
                ),
                const SizedBox(height: 28),
                WorkflowSteps(current: _images.isEmpty ? 0 : 1),
                const SizedBox(height: 30),
                _sectionHeading('01', '先挑几张照片', '${_images.length} / 20'),
                const SizedBox(height: 16),
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(
                      value: false,
                      icon: Icon(Icons.image_outlined, size: 18),
                      label: Text('单张添加'),
                    ),
                    ButtonSegment(
                      value: true,
                      icon: Icon(Icons.photo_library_outlined, size: 18),
                      label: Text('批量添加'),
                    ),
                  ],
                  selected: {_multiSelect},
                  onSelectionChanged: _busy || _picking
                      ? null
                      : (value) => setState(() => _multiSelect = value.first),
                  style: const ButtonStyle(
                    visualDensity: VisualDensity.compact,
                  ),
                ),
                const SizedBox(height: 16),
                if (_images.isEmpty) _emptyPicker() else _photoGrid(),
                const SizedBox(height: 10),
                const Text(
                  '仅图片 · 单张 ≤10 MiB · 总计 ≤50 MiB。点图预览，箭头排序。',
                  style: TextStyle(
                    color: Color(0xFF9C8F83),
                    fontSize: 11,
                    height: 1.6,
                  ),
                ),
                const SizedBox(height: 30),
                _sectionHeading('02', '这次想分享什么？', '一点想法就够了'),
                const SizedBox(height: 16),
                TextField(
                  key: const Key('idea_input'),
                  controller: _idea,
                  enabled: !_busy,
                  minLines: 4,
                  maxLines: 8,
                  maxLength: 2000,
                  decoration: const InputDecoration(
                    hintText: '例如：周末在杭州发现一家宝藏咖啡店，想分享店里的氛围、必点饮品和拍照机位，语气轻松自然。',
                    hintStyle: TextStyle(
                      fontSize: 14,
                      height: 1.8,
                      color: Color(0xFFB1A59A),
                    ),
                  ),
                  style: const TextStyle(fontSize: 15, height: 1.8),
                ),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    for (final label in ['探店打卡', '旅行日记', '好物分享', '日常碎片'])
                      ActionChip(
                        label: Text(
                          label,
                          style: const TextStyle(fontSize: 12),
                        ),
                        side: const BorderSide(color: Color(0xFFEAE1D7)),
                        backgroundColor: Colors.transparent,
                        onPressed: _busy
                            ? null
                            : () {
                                _idea.text = _idea.text.trim().isEmpty
                                    ? '写一篇$label笔记，结合图片里的细节，用自然真诚的口吻分享。'
                                    : '${_idea.text}\n风格：$label。';
                              },
                      ),
                  ],
                ),
                if (_busy) ...[const SizedBox(height: 24), _progressCard()],
                if (_error != null) ...[
                  const SizedBox(height: 24),
                  _errorCard(),
                ],
                const SizedBox(height: 20),
                const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.lock_outline_rounded,
                      color: Color(0xFFA5988A),
                      size: 14,
                    ),
                    SizedBox(width: 7),
                    Expanded(
                      child: Text(
                        '所选图片将发送至你配置的创作服务，用于生成笔记。',
                        style: TextStyle(
                          fontSize: 11,
                          height: 1.5,
                          color: Color(0xFFA5988A),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        bottomNavigationBar: SafeArea(
          top: false,
          child: Container(
            decoration: const BoxDecoration(
              color: Color(0xFFFFFCF8),
              border: Border(top: BorderSide(color: Color(0xFFF0E9E0))),
            ),
            padding: const EdgeInsets.fromLTRB(22, 14, 22, 10),
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
                        key: const Key('generate_button'),
                        onPressed: canGenerate ? _generate : null,
                        icon: _busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.auto_awesome_rounded, size: 20),
                        label: Text(_busy ? '正在认真创作…' : '生成我的笔记'),
                      ),
                    ),
                    if (_busy)
                      TextButton(
                        key: const Key('cancel_button'),
                        onPressed: () =>
                            _cancelToken?.cancel('cancelled by user'),
                        child: const Text('取消等待'),
                      ),
                    const SizedBox(height: 9),
                    const Text(
                      'AI 辅助创作 · 发布前请核对真实信息',
                      style: TextStyle(color: Color(0xFFADA093), fontSize: 10),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _sectionHeading(String step, String title, String trailing) => Row(
    children: [
      Text(
        step,
        style: const TextStyle(
          fontSize: 12,
          color: Color(0xFFE65E51),
          fontWeight: FontWeight.w800,
        ),
      ),
      const SizedBox(width: 8),
      Expanded(
        child: Text(
          title,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
        ),
      ),
      Text(
        trailing,
        style: const TextStyle(fontSize: 11, color: Color(0xFF9B8D80)),
      ),
    ],
  );

  Widget _emptyPicker() => Semantics(
    button: true,
    label: '从相册选择图片',
    child: InkWell(
      onTap: _picking ? null : _pickImages,
      borderRadius: BorderRadius.circular(22),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 32),
        decoration: BoxDecoration(
          color: const Color(0xFFF8F1E8),
          border: Border.all(color: const Color(0xFFE9DED1)),
          borderRadius: BorderRadius.circular(22),
        ),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(15),
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
              ),
              child: _picking
                  ? const SizedBox(
                      width: 28,
                      height: 28,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(
                      Icons.add_photo_alternate_outlined,
                      color: Color(0xFFE65E51),
                      size: 28,
                    ),
            ),
            const SizedBox(height: 16),
            Text(
              _picking ? '正在打开相册…' : '从相册挑选图片',
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 7),
            const Text(
              '让每一个画面，都有值得记录的文字',
              style: TextStyle(fontSize: 12, color: Color(0xFFA19385)),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _photoGrid() => LayoutBuilder(
    builder: (context, constraints) {
      final columns = constraints.maxWidth > 500 ? 4 : 3;
      final width = (constraints.maxWidth - (columns - 1) * 8) / columns;
      return Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (var index = 0; index < _images.length; index++)
            SizedBox(
              width: width,
              height: width * 1.25,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    InkWell(
                      onTap: () => showPhotoPreview(context, _images, index),
                      child: PhotoThumbnail(image: _images[index]),
                    ),
                    Positioned(
                      top: 7,
                      left: 7,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 7,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          index == 0 ? '1 · 封面' : '${index + 1}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                          ),
                        ),
                      ),
                    ),
                    Positioned(
                      top: 0,
                      right: 0,
                      child: IconButton(
                        tooltip: '移除第 ${index + 1} 张图片',
                        onPressed: _busy
                            ? null
                            : () => setState(() {
                                _images.removeAt(index);
                                _error = null;
                              }),
                        icon: const Icon(
                          Icons.cancel,
                          color: Colors.white,
                          shadows: [
                            Shadow(blurRadius: 3, color: Colors.black54),
                          ],
                        ),
                        iconSize: 21,
                      ),
                    ),
                    Positioned(
                      bottom: 0,
                      left: 0,
                      right: 0,
                      child: ColoredBox(
                        color: Colors.black45,
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            IconButton(
                              visualDensity: VisualDensity.compact,
                              tooltip: '第 ${index + 1} 张前移',
                              onPressed: _busy || index == 0
                                  ? null
                                  : () => _moveImage(index, -1),
                              icon: const Icon(
                                Icons.chevron_left,
                                color: Colors.white,
                                size: 20,
                              ),
                            ),
                            IconButton(
                              visualDensity: VisualDensity.compact,
                              tooltip: '第 ${index + 1} 张后移',
                              onPressed: _busy || index == _images.length - 1
                                  ? null
                                  : () => _moveImage(index, 1),
                              icon: const Icon(
                                Icons.chevron_right,
                                color: Colors.white,
                                size: 20,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (_images.length < 20)
            SizedBox(
              width: width,
              height: width * 1.25,
              child: Material(
                color: const Color(0xFFF5EFE7),
                borderRadius: BorderRadius.circular(14),
                child: InkWell(
                  borderRadius: BorderRadius.circular(14),
                  onTap: _busy || _picking ? null : _pickImages,
                  child: const Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.add_rounded,
                        size: 30,
                        color: Color(0xFFA08F7F),
                      ),
                      SizedBox(height: 5),
                      Text(
                        '继续添加',
                        style: TextStyle(
                          fontSize: 12,
                          color: Color(0xFFA08F7F),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      );
    },
  );

  Widget _progressCard() => Container(
    key: const Key('generation_progress'),
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF0E9),
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(
              Icons.auto_awesome_outlined,
              color: Color(0xFFE65E51),
              size: 20,
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Text(
                _progress < 1
                    ? '正在上传图片 ${(_progress * 100).round()}%'
                    : '图片已上传，正在为你创作',
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        LinearProgressIndicator(
          value: _progress < 1 ? _progress : null,
          minHeight: 4,
          borderRadius: BorderRadius.circular(4),
        ),
        const SizedBox(height: 12),
        Text(
          _progress < 1 ? '请保持网络连接。' : '正在理解画面、组织标题与正文。通常需要几分钟，请耐心等待。',
          style: const TextStyle(
            fontSize: 12,
            height: 1.7,
            color: Color(0xFF9B7568),
          ),
        ),
        Row(
          children: [
            Text(
              '已等待 ${_seconds ~/ 60}:${(_seconds % 60).toString().padLeft(2, '0')}',
              style: const TextStyle(fontSize: 11, color: Color(0xFFAE8C80)),
            ),
            const Spacer(),
            TextButton(
              onPressed: () => _cancelToken?.cancel('cancelled by user'),
              child: const Text('取消等待'),
            ),
          ],
        ),
      ],
    ),
  );

  Widget _errorCard() => Container(
    key: const Key('generation_error'),
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: const Color(0xFFFFEDEB),
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.error_outline, size: 20, color: Color(0xFFB9473F)),
            SizedBox(width: 8),
            Text(
              '这次没能完成创作',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: Color(0xFFB9473F),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Text(
          _error!.message,
          style: const TextStyle(
            fontSize: 13,
            height: 1.6,
            color: Color(0xFF995A51),
          ),
        ),
        if (_error!.requestId != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: SelectableText(
              '请求编号：${_error!.requestId}',
              style: const TextStyle(fontSize: 10, color: Color(0xFFAA827A)),
            ),
          ),
        const SizedBox(height: 12),
        Row(
          children: [
            OutlinedButton(onPressed: _generate, child: const Text('重新生成')),
            const SizedBox(width: 8),
            TextButton(onPressed: _editSettings, child: const Text('检查服务设置')),
          ],
        ),
      ],
    ),
  );
}
