import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class XaiTextField extends StatefulWidget {
  const XaiTextField(
      {super.key,
      required this.controller,
      required this.label,
      this.password = false,
      this.email = false,
      this.code = false,
      this.enabled = true,
      this.textInputAction});
  final TextEditingController controller;
  final String label;
  final bool password;
  final bool email;
  final bool code;
  final bool enabled;
  final TextInputAction? textInputAction;
  @override
  State<XaiTextField> createState() => _XaiTextFieldState();
}

class _XaiTextFieldState extends State<XaiTextField> {
  bool hidden = true;
  @override
  Widget build(BuildContext context) => TextField(
        key: ValueKey(widget.label),
        controller: widget.controller,
        enabled: widget.enabled,
        obscureText: widget.password && hidden,
        autocorrect: false,
        enableSuggestions: !widget.password,
        keyboardType: widget.code
            ? TextInputType.number
            : widget.email
                ? TextInputType.emailAddress
                : TextInputType.text,
        textInputAction: widget.textInputAction,
        maxLength: widget.code ? 6 : null,
        inputFormatters: widget.code
            ? [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(6)
              ]
            : null,
        style: widget.code
            ? const TextStyle(
                fontSize: 24, fontWeight: FontWeight.w700, letterSpacing: 8)
            : null,
        textAlign: widget.code ? TextAlign.center : TextAlign.start,
        decoration: InputDecoration(
            labelText: widget.label,
            counterText: '',
            suffixIcon: widget.password
                ? IconButton(
                    tooltip: hidden ? 'Show password' : 'Hide password',
                    icon: Icon(hidden
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined),
                    onPressed: () => setState(() => hidden = !hidden),
                  )
                : null),
      );
}
