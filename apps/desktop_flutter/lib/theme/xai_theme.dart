import 'package:flutter/material.dart';

abstract final class XaiColors {
  static const brand = Color(0xff4658d8),
      accent = Color(0xff30b9a7),
      ink = Color(0xff182033),
      muted = Color(0xff687386),
      background = Color(0xfff5f7fb),
      surface = Colors.white,
      line = Color(0xffe1e6ef),
      danger = Color(0xffb42318),
      success = Color(0xff147a4c),
      nav = Color(0xff11182a);
}

abstract final class XaiTheme {
  static ThemeData light = _theme(Brightness.light);
  static ThemeData dark = _theme(Brightness.dark);
  static ThemeData _theme(Brightness b) {
    final dark = b == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
        seedColor: XaiColors.brand,
        brightness: b,
        error: XaiColors.danger,
        surface: dark ? const Color(0xff1b2336) : XaiColors.surface);
    return ThemeData(
        useMaterial3: true,
        brightness: b,
        colorScheme: scheme,
        scaffoldBackgroundColor: dark ? XaiColors.nav : XaiColors.background,
        fontFamily: 'Inter',
        inputDecorationTheme: InputDecorationTheme(
            filled: true,
            fillColor: dark ? const Color(0xff222c42) : Colors.white,
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: XaiColors.line)),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 15)),
        filledButtonTheme: FilledButtonThemeData(
            style: FilledButton.styleFrom(
                backgroundColor: XaiColors.brand,
                foregroundColor: Colors.white,
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)))),
        cardTheme: CardThemeData(
            elevation: 0,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side:
                    BorderSide(color: dark ? Colors.white12 : XaiColors.line))),
        navigationRailTheme: NavigationRailThemeData(
            backgroundColor: dark ? const Color(0xff151d2f) : Colors.white,
            indicatorColor: XaiColors.brand.withValues(alpha: .14)));
  }
}
