import 'package:flutter/material.dart';
import 'xai_colors.dart';
import 'xai_spacing.dart';
import 'xai_typography.dart';

abstract final class XaiTheme {
  static ThemeData light() => _theme(Brightness.light);
  static ThemeData dark() => _theme(Brightness.dark);

  static ThemeData _theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final surface = dark ? XaiColors.darkSurface : XaiColors.surface;
    final background = dark ? XaiColors.darkBackground : XaiColors.background;
    final ink = dark ? const Color(0xFFF4F6FC) : XaiColors.ink;
    final muted = dark ? const Color(0xFFADB7CA) : XaiColors.muted;
    final line = dark ? XaiColors.darkLine : XaiColors.line;
    final scheme =
        ColorScheme.fromSeed(seedColor: XaiColors.brand, brightness: brightness)
            .copyWith(
      primary: dark ? const Color(0xFF8C9BFF) : XaiColors.brand,
      secondary: XaiColors.accent,
      surface: surface,
      error: XaiColors.danger,
    );
    final border = OutlineInputBorder(
        borderRadius: BorderRadius.circular(XaiSpacing.radiusSmall),
        borderSide: BorderSide(color: line));
    return ThemeData(
      brightness: brightness,
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      textTheme: XaiTypography.theme(ink, muted),
      cardTheme: CardThemeData(
          color: surface,
          elevation: 0,
          margin: EdgeInsets.zero,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(XaiSpacing.radius),
              side: BorderSide(color: line))),
      inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: surface,
          border: border,
          enabledBorder: border,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 14, vertical: 14)),
      filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(46),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(XaiSpacing.radiusSmall)),
              textStyle: const TextStyle(fontWeight: FontWeight.w700))),
      outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(46),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(XaiSpacing.radiusSmall)),
              side: BorderSide(color: line))),
    );
  }
}
