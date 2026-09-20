import 'package:flutter/material.dart';

abstract final class XaiTypography {
  static TextTheme theme(Color ink, Color muted) => TextTheme(
        headlineLarge: TextStyle(
            fontSize: 30,
            height: 1.15,
            fontWeight: FontWeight.w800,
            letterSpacing: -0.7,
            color: ink),
        headlineMedium: TextStyle(
            fontSize: 26,
            height: 1.2,
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
            color: ink),
        titleLarge:
            TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: ink),
        titleMedium:
            TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: ink),
        bodyLarge: TextStyle(fontSize: 16, height: 1.5, color: ink),
        bodyMedium: TextStyle(fontSize: 14, height: 1.5, color: muted),
        labelLarge: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
      );
}
