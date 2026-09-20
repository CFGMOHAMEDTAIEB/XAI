import 'package:flutter/material.dart';
import '../theme/xai_spacing.dart';

class XaiCard extends StatelessWidget {
  const XaiCard({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Card(
      child:
          Padding(padding: const EdgeInsets.all(XaiSpacing.lg), child: child));
}
