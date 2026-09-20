import 'package:flutter/material.dart';
import '../theme/xai_colors.dart';
import '../theme/xai_spacing.dart';
import 'xai_card.dart';

class XaiAuthLayout extends StatelessWidget {
  const XaiAuthLayout(
      {super.key,
      required this.eyebrow,
      required this.title,
      required this.subtitle,
      required this.child});
  final String eyebrow;
  final String title;
  final String subtitle;
  final Widget child;
  @override
  Widget build(BuildContext context) => Scaffold(
      body: SafeArea(
          child: LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                    padding: EdgeInsets.fromLTRB(
                        XaiSpacing.lg,
                        XaiSpacing.lg,
                        XaiSpacing.lg,
                        MediaQuery.viewInsetsOf(context).bottom +
                            XaiSpacing.lg),
                    child: ConstrainedBox(
                        constraints: BoxConstraints(
                            minHeight:
                                constraints.maxHeight - XaiSpacing.xl * 2),
                        child: Center(
                            child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 450),
                          child: XaiCard(
                              child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                Align(
                                    child: Container(
                                        width: 48,
                                        height: 48,
                                        decoration: BoxDecoration(
                                            borderRadius:
                                                BorderRadius.circular(14),
                                            gradient: const LinearGradient(
                                                colors: [
                                                  Color(0xFF6073F3),
                                                  XaiColors.accent
                                                ])),
                                        child: const Center(
                                            child: Text('XC',
                                                style: TextStyle(
                                                    color: Colors.white,
                                                    fontWeight:
                                                        FontWeight.w800))))),
                                const SizedBox(height: 18),
                                Text(eyebrow.toUpperCase(),
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                        color: XaiColors.brand,
                                        fontSize: 11,
                                        fontWeight: FontWeight.w800,
                                        letterSpacing: 1.3)),
                                const SizedBox(height: 6),
                                Text(title,
                                    textAlign: TextAlign.center,
                                    style: Theme.of(context)
                                        .textTheme
                                        .headlineMedium),
                                const SizedBox(height: 8),
                                Text(subtitle,
                                    textAlign: TextAlign.center,
                                    style:
                                        Theme.of(context).textTheme.bodyMedium),
                                const SizedBox(height: 24),
                                child,
                              ])),
                        ))),
                  ))));
}
