import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../services/api_service.dart';
import '../theme/xai_theme.dart';

class AuthFlow extends StatelessWidget {
  const AuthFlow({super.key});
  @override
  Widget build(BuildContext context) =>
      switch (context.watch<AppState>().authStage) {
        AuthStage.mfa => const LoginPanel(mfa: true),
        AuthStage.verifyEmail => const VerificationPanel(),
        _ => const LoginPanel(),
      };
}

class AuthFrame extends StatelessWidget {
  const AuthFrame(
      {required this.title,
      required this.subtitle,
      required this.child,
      super.key});
  final String title, subtitle;
  final Widget child;
  @override
  Widget build(BuildContext c) => Scaffold(
      body: Center(
          child: SingleChildScrollView(
              padding: const EdgeInsets.all(32),
              child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 460),
                  child: Card(
                      child: Padding(
                          padding: const EdgeInsets.all(36),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                const Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(Icons.shield_outlined,
                                          color: XaiColors.brand, size: 38),
                                      SizedBox(width: 10),
                                      Text('XAI Compress',
                                          style: TextStyle(
                                              fontSize: 22,
                                              fontWeight: FontWeight.w700))
                                    ]),
                                const SizedBox(height: 28),
                                Text(title,
                                    textAlign: TextAlign.center,
                                    style: Theme.of(c)
                                        .textTheme
                                        .headlineSmall
                                        ?.copyWith(
                                            fontWeight: FontWeight.w700)),
                                const SizedBox(height: 8),
                                Text(subtitle,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                        color: XaiColors.muted)),
                                const SizedBox(height: 24),
                                child
                              ])))))));
}

class LoginPanel extends StatefulWidget {
  const LoginPanel({this.mfa = false, super.key});
  final bool mfa;
  @override
  State<LoginPanel> createState() => _LoginPanelState();
}

class _LoginPanelState extends State<LoginPanel> {
  final email = TextEditingController(),
      password = TextEditingController(),
      code = TextEditingController();
  bool busy = false, hidden = true, register = false;
  String? error;
  Future<void> submit() async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    final s = context.read<AppState>();
    try {
      if (register) {
        await s.api.register(
            email.text.split('@').first, email.text.trim(), password.text);
        s.requireEmailVerification(email.text.trim());
      } else {
        await s.login(
            widget.mfa ? s.pendingEmail! : email.text.trim(), password.text,
            totp: widget.mfa ? code.text.trim() : null);
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      password.clear();
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext c) => AuthFrame(
      title: widget.mfa
          ? 'Verify your identity'
          : register
              ? 'Create account'
              : 'Welcome back',
      subtitle: widget.mfa
          ? 'Enter the 6-digit code from XAI Authenticator'
          : 'Authenticate before accessing your private workspace.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (!widget.mfa)
          TextField(
              controller: email,
              autofocus: true,
              onSubmitted: (_) => submit(),
              decoration: const InputDecoration(
                  labelText: 'Email', prefixIcon: Icon(Icons.mail_outline))),
        if (!widget.mfa) const SizedBox(height: 14),
        TextField(
            controller: password,
            obscureText: hidden,
            onSubmitted: (_) => submit(),
            decoration: InputDecoration(
                labelText: 'Password',
                prefixIcon: const Icon(Icons.lock_outline),
                suffixIcon: IconButton(
                    tooltip: 'Show or hide password',
                    onPressed: () => setState(() => hidden = !hidden),
                    icon: Icon(hidden
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined)))),
        if (widget.mfa) ...[
          const SizedBox(height: 14),
          TextField(
              controller: code,
              autofocus: true,
              maxLength: 6,
              onSubmitted: (_) => submit(),
              decoration: const InputDecoration(
                  labelText: '6-digit code',
                  prefixIcon: Icon(Icons.shield_outlined)))
        ],
        if (error != null)
          Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(error!,
                  style: const TextStyle(color: XaiColors.danger))),
        const SizedBox(height: 18),
        FilledButton(
            onPressed: busy ? null : submit,
            child: Text(widget.mfa
                ? 'Verify and continue'
                : register
                    ? 'Create account'
                    : 'Login')),
        if (widget.mfa)
          TextButton(onPressed: safeBack, child: const Text('Back to login'))
        else ...[
          TextButton(
              onPressed: () => Navigator.push(
                  c,
                  MaterialPageRoute(
                      builder: (_) => const ForgotPasswordPanel())),
              child: const Text('Forgot password?')),
          TextButton(
              onPressed: () => setState(() => register = !register),
              child: Text(register ? 'Sign in instead' : 'Create account'))
        ]
      ]));
  void safeBack() => context.read<AppState>().backToLogin();
  @override
  void dispose() {
    email.dispose();
    password.dispose();
    code.dispose();
    super.dispose();
  }
}

class VerificationPanel extends StatefulWidget {
  const VerificationPanel({super.key});
  @override
  State<VerificationPanel> createState() => _VerificationPanelState();
}

class _VerificationPanelState extends State<VerificationPanel> {
  final code = TextEditingController();
  String? error;
  int cooldown = 0;
  Timer? timer;
  Future<void> verify() async {
    try {
      await context.read<AppState>().completeEmailVerification(code.text);
    } on ApiException catch (e) {
      setState(() => error = e.message);
    }
  }

  Future<void> resend() async {
    await context
        .read<AppState>()
        .api
        .sendEmailVerification(context.read<AppState>().pendingEmail!);
    cooldown = 60;
    timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (cooldown <= 1) {
        t.cancel();
        cooldown = 0;
      } else {
        cooldown--;
      }
      if (mounted) setState(() {});
    });
    setState(() {});
  }

  @override
  Widget build(BuildContext c) => AuthFrame(
      title: 'Verify your email',
      subtitle: 'Enter the emailed verification code.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        TextField(
            controller: code,
            autofocus: true,
            maxLength: 6,
            onSubmitted: (_) => verify(),
            decoration: const InputDecoration(labelText: 'Verification code')),
        if (error != null)
          Text(error!, style: const TextStyle(color: XaiColors.danger)),
        FilledButton(onPressed: verify, child: const Text('Verify email')),
        TextButton(
            onPressed: cooldown > 0 ? null : resend,
            child:
                Text(cooldown > 0 ? 'Resend in ${cooldown}s' : 'Resend code')),
        TextButton(
            onPressed: context.read<AppState>().backToLogin,
            child: const Text('Back to login'))
      ]));
  @override
  void dispose() {
    timer?.cancel();
    code.dispose();
    super.dispose();
  }
}

class ForgotPasswordPanel extends StatefulWidget {
  const ForgotPasswordPanel({super.key});
  @override
  State<ForgotPasswordPanel> createState() => _ForgotPasswordPanelState();
}

class _ForgotPasswordPanelState extends State<ForgotPasswordPanel> {
  final email = TextEditingController(),
      code = TextEditingController(),
      password = TextEditingController(),
      confirm = TextEditingController();
  int step = 0;
  String? token, error;
  Future<void> go() async {
    try {
      final a = context.read<AppState>().api;
      if (step == 0) {
        await a.forgotPassword(email.text.trim());
        step = 1;
      } else if (step == 1) {
        token = await a.verifyResetCode(email.text.trim(), code.text);
        step = 2;
      } else {
        if (password.text != confirm.text) {
          throw const ApiException('Passwords do not match.');
        }
        await a.resetPassword(token!, password.text);
        token = null;
        if (mounted) Navigator.pop(context);
      }
      if (mounted) setState(() {});
    } on ApiException catch (e) {
      setState(() => error = e.message);
    }
  }

  @override
  Widget build(BuildContext c) => AuthFrame(
      title: 'Reset password',
      subtitle: step == 0
          ? 'Request a reset code.'
          : step == 1
              ? 'If eligible, a code has been sent.'
              : 'MFA remains enabled after reset.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (step == 0)
          TextField(
              controller: email,
              decoration: const InputDecoration(labelText: 'Email')),
        if (step == 1)
          TextField(
              controller: code,
              maxLength: 6,
              decoration: const InputDecoration(labelText: 'Reset code')),
        if (step == 2) ...[
          TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'New password')),
          const SizedBox(height: 12),
          TextField(
              controller: confirm,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Confirm password'))
        ],
        if (error != null)
          Text(error!, style: const TextStyle(color: XaiColors.danger)),
        const SizedBox(height: 16),
        FilledButton(
            onPressed: go,
            child: Text(step == 0
                ? 'Send reset code'
                : step == 1
                    ? 'Verify code'
                    : 'Reset password')),
        TextButton(
            onPressed: () => Navigator.pop(c), child: const Text('Cancel'))
      ]));
  @override
  void dispose() {
    token = null;
    email.dispose();
    code.dispose();
    password.dispose();
    confirm.dispose();
    super.dispose();
  }
}
