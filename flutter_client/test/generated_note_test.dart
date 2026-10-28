import 'package:flutter_test/flutter_test.dart';
import 'package:linggan_chenggao/models/generated_note.dart';

Map<String, Object?> _response({Map<String, Object?> additions = const {}}) => {
  'code': 0,
  'request_id': 'request-id',
  'data': {
    'title': '花瓣之间',
    'content': '记录这张菊花照片。',
    'tags': ['菊花'],
    'image_order': ['img_0'],
    ...additions,
  },
};

void main() {
  test('legacy responses without review warnings remain compatible', () {
    final note = GeneratedNote.fromResponse(_response());

    expect(note.title, '花瓣之间');
    expect(note.reviewWarnings, isEmpty);
    expect(() => note.reviewWarnings.add('changed'), throwsUnsupportedError);
  });

  test(
    'review warnings are parsed as an immutable independent string list',
    () {
      final warnings = [' 请核对具体地点。 ', '请核对花期。', '   '];
      final note = GeneratedNote.fromResponse(
        _response(additions: {'review_warnings': warnings}),
      );

      warnings[0] = 'changed after parsing';
      warnings.add('later warning');
      expect(note.reviewWarnings, ['请核对具体地点。', '请核对花期。']);
      expect(() => note.reviewWarnings[0] = 'changed', throwsUnsupportedError);
      expect(note.content, '记录这张菊花照片。');
      expect(note.tags, ['菊花']);
    },
  );

  test('an explicit empty review warnings list is accepted', () {
    final note = GeneratedNote.fromResponse(
      _response(additions: {'review_warnings': <String>[]}),
    );

    expect(note.reviewWarnings, isEmpty);
  });

  test('non-list or non-string review warnings are rejected', () {
    for (final invalid in [
      null,
      'warning',
      1,
      ['warning', 2],
      [{}],
    ]) {
      expect(
        () => GeneratedNote.fromResponse(
          _response(additions: {'review_warnings': invalid}),
        ),
        throwsFormatException,
        reason: 'Expected list[str], received $invalid',
      );
    }
  });

  test('directly constructed notes default to no review warnings', () {
    const note = GeneratedNote(
      title: '花瓣之间',
      content: '记录这张菊花照片。',
      tags: ['菊花'],
      imageOrder: ['img_0'],
    );

    expect(note.reviewWarnings, isEmpty);
  });
}
