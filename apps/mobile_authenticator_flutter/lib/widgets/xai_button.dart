import 'package:flutter/material.dart';

class XaiButton extends StatelessWidget {
  const XaiButton(
      {super.key,
      required this.label,
      required this.onPressed,
      this.icon,
      this.secondary = false});
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool secondary;
  @override
  Widget build(BuildContext context) {
    final child = icon == null
        ? Text(label, textAlign: TextAlign.center)
        : Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
                Icon(icon),
                const SizedBox(width: 8),
                Flexible(child: Text(label, textAlign: TextAlign.center)),
              ]);
    return secondary
        ? OutlinedButton(onPressed: onPressed, child: child)
        : FilledButton(onPressed: onPressed, child: child);
  }
}
