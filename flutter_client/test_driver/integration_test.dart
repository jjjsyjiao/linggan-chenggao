import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    onScreenshot: (name, bytes, [arguments]) async {
      final directory = Directory('../artifacts/mobile');
      await directory.create(recursive: true);
      await File('${directory.path}/$name.png').writeAsBytes(bytes);
      return true;
    },
  );
}
