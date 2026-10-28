import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'screens/creation_screen.dart';
import 'services/note_api_service.dart';
import 'services/note_share_service.dart';

void main() => runApp(const LingganApp());

class LingganApp extends StatelessWidget {
  const LingganApp({
    super.key,
    this.apiService,
    this.shareService,
    this.imagePicker,
  });

  final NoteApiService? apiService;
  final ImagePicker? imagePicker;
  final NoteShareService? shareService;

  @override
  Widget build(BuildContext context) {
    final colors = ColorScheme.fromSeed(
      seedColor: const Color(0xFFED6658),
      brightness: Brightness.light,
      primary: const Color(0xFFE65E51),
      onPrimary: Colors.white,
      surface: const Color(0xFFFFFCF8),
      onSurface: const Color(0xFF332C29),
    );
    return MaterialApp(
      title: '灵感成稿',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: colors,
        scaffoldBackgroundColor: const Color(0xFFFFFCF8),
        fontFamilyFallback: const [
          'PingFang SC',
          'Noto Sans CJK SC',
          'sans-serif',
        ],
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFFFFFCF8),
          elevation: 0,
          scrolledUnderElevation: 0,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: const BorderSide(color: Color(0xFFE9E3DC)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: const BorderSide(color: Color(0xFFE9E3DC)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: BorderSide(color: colors.primary, width: 1.5),
          ),
          contentPadding: const EdgeInsets.all(18),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size(0, 54),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            textStyle: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            minimumSize: const Size(0, 48),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
          ),
        ),
        snackBarTheme: SnackBarThemeData(
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      home: CreationScreen(
        imagePicker: imagePicker,
        apiService: apiService ?? NoteApiService(),
        shareService: shareService ?? const PlatformNoteShareService(),
      ),
    );
  }
}
