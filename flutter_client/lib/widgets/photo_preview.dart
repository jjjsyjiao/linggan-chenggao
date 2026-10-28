import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

class PhotoThumbnail extends StatelessWidget {
  const PhotoThumbnail({
    super.key,
    required this.image,
    this.fit = BoxFit.cover,
    this.decodeSize = 480,
  });
  final XFile image;
  final BoxFit fit;

  /// Bound both decoded dimensions, including unusually tall panoramas.
  final int decodeSize;

  @override
  Widget build(BuildContext context) => Image(
    image: ResizeImage(
      FileImage(File(image.path)),
      width: decodeSize,
      height: decodeSize,
      policy: ResizeImagePolicy.fit,
    ),
    fit: fit,
    errorBuilder: (context, error, stackTrace) => const ColoredBox(
      color: Color(0xFFF0EAE3),
      child: Center(
        child: Icon(Icons.broken_image_outlined, color: Color(0xFF988A80)),
      ),
    ),
  );
}

Future<void> showPhotoPreview(
  BuildContext context,
  List<XFile> images,
  int initialIndex,
) => showDialog<void>(
  context: context,
  useSafeArea: false,
  builder: (context) =>
      _PhotoGallery(images: images, initialIndex: initialIndex),
);

class _PhotoGallery extends StatefulWidget {
  const _PhotoGallery({required this.images, required this.initialIndex});
  final List<XFile> images;
  final int initialIndex;

  @override
  State<_PhotoGallery> createState() => _PhotoGalleryState();
}

class _PhotoGalleryState extends State<_PhotoGallery> {
  late final PageController _controller = PageController(
    initialPage: widget.initialIndex,
  );
  late int _index = widget.initialIndex;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Dialog.fullscreen(
    backgroundColor: const Color(0xFF1F1C1B),
    child: SafeArea(
      child: Column(
        children: [
          Row(
            children: [
              IconButton(
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close, color: Colors.white),
                tooltip: '关闭预览',
              ),
              const Spacer(),
              Text(
                '${_index + 1} / ${widget.images.length}',
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(width: 24),
            ],
          ),
          Expanded(
            child: PageView.builder(
              controller: _controller,
              itemCount: widget.images.length,
              onPageChanged: (index) => setState(() => _index = index),
              itemBuilder: (context, index) => InteractiveViewer(
                child: PhotoThumbnail(
                  image: widget.images[index],
                  fit: BoxFit.contain,
                  decodeSize: 1600,
                ),
              ),
            ),
          ),
          const Padding(
            padding: EdgeInsets.all(20),
            child: Text(
              '左右滑动查看 · 双指缩放',
              style: TextStyle(color: Colors.white70),
            ),
          ),
        ],
      ),
    ),
  );
}
