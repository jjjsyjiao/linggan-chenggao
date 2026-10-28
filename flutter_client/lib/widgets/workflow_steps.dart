import 'package:flutter/material.dart';

class WorkflowSteps extends StatelessWidget {
  const WorkflowSteps({super.key, required this.current});
  final int current;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      for (var i = 0; i < 3; i++) ...[
        if (i > 0)
          Expanded(
            child: Container(
              height: 1,
              margin: const EdgeInsets.symmetric(horizontal: 10),
              color: const Color(0xFFE8E1D8),
            ),
          ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: i <= current
                    ? Theme.of(context).colorScheme.primary
                    : const Color(0xFFF0EAE3),
              ),
              child: Center(
                child: i < current
                    ? const Icon(Icons.check, size: 16, color: Colors.white)
                    : Text(
                        '${i + 1}',
                        style: TextStyle(
                          color: i <= current
                              ? Colors.white
                              : const Color(0xFF95877C),
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
              ),
            ),
            const SizedBox(width: 7),
            Text(
              ['选图片', '写想法', '预览分享'][i],
              style: TextStyle(
                fontSize: 12,
                color: i <= current
                    ? const Color(0xFF4D3C32)
                    : const Color(0xFF9B8E83),
                fontWeight: i == current ? FontWeight.w700 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ],
    ],
  );
}
