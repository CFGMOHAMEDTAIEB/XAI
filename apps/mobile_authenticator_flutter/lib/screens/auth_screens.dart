import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';
import '../services/api_service.dart';
import '../theme/xai_colors.dart';
import '../theme/xai_spacing.dart';
import '../widgets/xai_auth_layout.dart';
import '../widgets/xai_button.dart';
import '../widgets/xai_text_field.dart';
import 'home_screen.dart';

void _replace(BuildContext context, Widget screen) => Navigator.of(context)
    .pushReplacement(MaterialPageRoute(builder: (_) => screen));
void _resetTo(BuildContext context, Widget screen) =>
    Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => screen), (_) => false);

class AuthError extends StatelessWidget {
  const AuthError(this.message, {super.key});
  final String? message;
  @override
  Widget build(BuildContext context) => message == null
      ? const SizedBox.shrink()
      : Container(
          key: const ValueKey('auth-error'),
          margin: const EdgeInsets.only(top: 14),
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(
              color: XaiColors.danger.withValues(alpha: .09),
              borderRadius: BorderRadius.circular(10)),
          child:
              Text(message!, style: const TextStyle(color: XaiColors.danger)),
        );
}

class LandingScreen extends StatelessWidget {
  const LandingScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return XaiAuthLayout(
        eyebrow: 'XAI secure identity',
        title: 'Authentication, simplified',
        subtitle:
            'Create or access your XAI account and keep verification codes protected on this device.',
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          XaiButton(
              key: const ValueKey('create-account'),
              label: 'Create account',
              icon: Icons.person_add_alt_1,
              onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const RegistrationScreen()))),
          const SizedBox(height: XaiSpacing.sm),
          XaiButton(
              key: const ValueKey('login'),
              label: 'Login',
              icon: Icons.login,
              secondary: true,
              onPressed: () => Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const LoginScreen()))),
          if (state.accounts.isNotEmpty) ...[
            const SizedBox(height: XaiSpacing.md),
            TextButton.icon(
                onPressed: () {
                  state.openAuthenticator();
                  _resetTo(context, const HomeScreen());
                },
                icon: const Icon(Icons.key_outlined),
                label: const Text('Use authenticator offline')),
          ],
        ]));
  }
}

class RegistrationScreen extends StatefulWidget {
  const RegistrationScreen({super.key});
  @override
  State<RegistrationScreen> createState() => _RegistrationScreenState();
}

class _RegistrationScreenState extends State<RegistrationScreen> {
  final name = TextEditingController(),
      email = TextEditingController(),
      password = TextEditingController(),
      confirm = TextEditingController();
  bool busy = false;
  String? error;
  Future<void> submit() async {
    if (busy) return;
    final normalizedName = name.text.trim().replaceAll(RegExp(r'\s+'), ' ');
    final normalizedEmail = email.text.trim().toLowerCase();
    if (normalizedName.isEmpty || !normalizedEmail.contains('@')) {
      setState(() => error = 'Enter your full name and a valid email.');
      return;
    }
    if (password.text.length < 10 || utf8.encode(password.text).length > 72) {
      setState(() => error = 'Use a password between 10 and 72 UTF-8 bytes.');
      return;
    }
    if (password.text != confirm.text) {
      setState(() => error = 'Passwords do not match.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await context.read<AppState>().apiService.register(
          fullName: normalizedName,
          email: normalizedEmail,
          password: password.text);
      if (mounted) {
        _replace(
            context,
            EmailVerificationScreen(
                email: normalizedEmail,
                fullName: normalizedName,
                registrationPassword: password.text));
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => XaiAuthLayout(
      eyebrow: 'Create your workspace',
      title: 'Create account',
      subtitle:
          'Use a strong password. Your authenticator key will be stored separately in secure device storage.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        XaiTextField(controller: name, label: 'Full name'),
        const SizedBox(height: 12),
        XaiTextField(controller: email, label: 'Email', email: true),
        const SizedBox(height: 12),
        XaiTextField(controller: password, label: 'Password', password: true),
        const SizedBox(height: 12),
        XaiTextField(
            controller: confirm, label: 'Confirm password', password: true),
        const SizedBox(height: 18),
        XaiButton(
            label: busy ? 'Creating account…' : 'Create account',
            onPressed: busy ? null : submit),
        TextButton(
            onPressed:
                busy ? null : () => _replace(context, const LoginScreen()),
            child: const Text('Already registered? Login')),
        AuthError(error),
        if (busy) const LinearProgressIndicator(),
      ]));
  @override
  void dispose() {
    name.dispose();
    email.dispose();
    password.dispose();
    confirm.dispose();
    super.dispose();
  }
}

class EmailVerificationScreen extends StatefulWidget {
  const EmailVerificationScreen(
      {super.key,
      required this.email,
      required this.fullName,
      this.registrationPassword});
  final String email, fullName;
  final String? registrationPassword;
  @override
  State<EmailVerificationScreen> createState() =>
      _EmailVerificationScreenState();
}

class _EmailVerificationScreenState extends State<EmailVerificationScreen> {
  final code = TextEditingController();
  bool busy = false;
  String? error;
  int cooldown = 60;
  Timer? timer;
  @override
  void initState() {
    super.initState();
    _startCooldown();
  }

  void _startCooldown() {
    timer?.cancel();
    setStateIfMounted(() => cooldown = 60);
    timer = Timer.periodic(const Duration(seconds: 1), (value) {
      if (!mounted) return value.cancel();
      setState(() => cooldown--);
      if (cooldown <= 0) value.cancel();
    });
  }

  void setStateIfMounted(VoidCallback action) {
    if (mounted) {
      setState(action);
    } else {
      action();
    }
  }

  Future<void> verify() async {
    if (busy || code.text.length != 6) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final api = context.read<AppState>().apiService;
      if (!await api.confirmAccountVerification(widget.email, code.text)) {
        throw const ApiException('That code was not accepted.');
      }
      if (widget.registrationPassword == null) {
        if (mounted) _resetTo(context, const LoginScreen());
        return;
      }
      await api.login(
          email: widget.email, password: widget.registrationPassword!);
      if (mounted) {
        _replace(context,
            EnrollmentScreen(email: widget.email, fullName: widget.fullName));
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => error = e.status == 410
            ? 'This code expired. Request a new code.'
            : 'That code is invalid or expired. Request a new code and try again.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> resend() async {
    if (busy || cooldown > 0) return;
    setState(() => busy = true);
    try {
      await context
          .read<AppState>()
          .apiService
          .sendAccountVerification(widget.email);
      _startCooldown();
      if (mounted) setState(() => error = null);
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => XaiAuthLayout(
      eyebrow: 'Account security',
      title: 'Verify your email',
      subtitle: 'Enter the 6-digit code sent to ${widget.email}.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        XaiTextField(
            controller: code,
            label: 'Verification code',
            code: true,
            enabled: !busy),
        const SizedBox(height: 16),
        XaiButton(
            label: busy ? 'Verifying…' : 'Verify email',
            onPressed: busy || code.text.length != 6 ? verify : verify),
        TextButton(
            onPressed: busy || cooldown > 0 ? null : resend,
            child:
                Text(cooldown > 0 ? 'Resend in ${cooldown}s' : 'Resend code')),
        AuthError(error),
        if (busy) const LinearProgressIndicator(),
      ]));
  @override
  void dispose() {
    timer?.cancel();
    code.dispose();
    super.dispose();
  }
}

class EnrollmentScreen extends StatefulWidget {
  const EnrollmentScreen(
      {super.key, required this.email, required this.fullName});
  final String email, fullName;
  @override
  State<EnrollmentScreen> createState() => _EnrollmentScreenState();
}

class _EnrollmentScreenState extends State<EnrollmentScreen> {
  bool busy = true;
  String? error;
  String? enrollmentId;
  @override
  void initState() {
    super.initState();
    scheduleMicrotask(start);
  }

  Future<void> start() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final state = context.read<AppState>();
      final data = await state.apiService.startAuthenticatorEnrollment();
      final id = data['enrollment_id'] as String;
      await state.provision(data['otpauth_uri'] as String, id,
          displayName: widget.fullName);
      if (mounted) setState(() => enrollmentId = id);
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => error =
            'Secure storage could not save the authenticator. Retry enrollment.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> confirm() async {
    final state = context.read<AppState>();
    final account = state.accounts
        .where((item) => item.id == 'xai-$enrollmentId')
        .firstOrNull;
    if (account == null) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final code = state.totpService.generate(account, now: state.now).code;
      if (!await state.apiService
          .confirmAuthenticatorEnrollment(enrollmentId!, code)) {
        throw const ApiException('Authenticator confirmation failed.');
      }
      state.openAuthenticator();
      if (mounted) _resetTo(context, const HomeScreen());
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => XaiAuthLayout(
      eyebrow: 'Protected enrollment',
      title: 'Set up authenticator',
      subtitle:
          'XAI generated this enrollment. The secret is stored only in secure device storage and codes are generated offline.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (busy) const Center(child: CircularProgressIndicator()),
        if (!busy && enrollmentId != null) ...[
          const Icon(Icons.verified_user_outlined,
              size: 54, color: XaiColors.success),
          const SizedBox(height: 12),
          const Text('Authenticator saved securely',
              textAlign: TextAlign.center),
          const SizedBox(height: 18),
          XaiButton(label: 'Activate authenticator', onPressed: confirm)
        ],
        if (!busy && enrollmentId == null)
          XaiButton(label: 'Retry enrollment', onPressed: start),
        AuthError(error),
      ]));
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final email = TextEditingController(),
      password = TextEditingController(),
      totp = TextEditingController();
  bool busy = false, mfa = false;
  String? error;
  Future<void> login() async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final state = context.read<AppState>();
      await state.apiService.login(
          email: email.text.trim(),
          password: password.text,
          totpCode: mfa ? totp.text : null);
      password.clear();
      totp.clear();
      state.openAuthenticator();
      if (mounted) _resetTo(context, const HomeScreen());
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          if (e.message == 'MFA_REQUIRED') {
            mfa = true;
            error = null;
          } else {
            error =
                mfa ? 'That authenticator code was not accepted.' : e.message;
          }
        });
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => XaiAuthLayout(
      eyebrow: mfa ? 'Additional verification' : 'XAI secure identity',
      title: mfa ? 'Verify your identity' : 'Welcome back',
      subtitle: mfa
          ? 'Enter the current 6-digit code from your authenticator.'
          : 'Sign in to your XAI account.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (!mfa) ...[
          XaiTextField(
              controller: email, label: 'Email', email: true, enabled: !busy),
          const SizedBox(height: 12),
          XaiTextField(
              controller: password,
              label: 'Password',
              password: true,
              enabled: !busy)
        ] else
          XaiTextField(
              controller: totp,
              label: 'Authenticator code',
              code: true,
              enabled: !busy),
        const SizedBox(height: 18),
        XaiButton(
            label: busy
                ? 'Signing in…'
                : mfa
                    ? 'Verify and login'
                    : 'Login',
            onPressed: busy ? null : login),
        if (mfa)
          TextButton(
              onPressed: busy
                  ? null
                  : () => setState(() {
                        mfa = false;
                        totp.clear();
                        error = null;
                      }),
              child: const Text('Back')),
        if (!mfa) ...[
          TextButton(
              onPressed: busy
                  ? null
                  : () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const ForgotPasswordScreen())),
              child: const Text('Forgot password?')),
          TextButton(
              onPressed: busy
                  ? null
                  : () => _replace(context, const RegistrationScreen()),
              child: const Text('New to XAI? Create account'))
        ],
        AuthError(error),
        if (busy) const LinearProgressIndicator(),
      ]));
  @override
  void dispose() {
    email.dispose();
    password.dispose();
    totp.dispose();
    super.dispose();
  }
}

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});
  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final email = TextEditingController(),
      code = TextEditingController(),
      password = TextEditingController(),
      confirm = TextEditingController();
  int step = 1, cooldown = 0;
  bool busy = false;
  String? error, resetToken;
  Timer? timer;
  void startCooldown() {
    timer?.cancel();
    setState(() => cooldown = 60);
    timer = Timer.periodic(const Duration(seconds: 1), (value) {
      if (!mounted) return value.cancel();
      setState(() => cooldown--);
      if (cooldown <= 0) value.cancel();
    });
  }

  Future<void> send() async {
    if (busy || email.text.trim().isEmpty) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await context
          .read<AppState>()
          .apiService
          .requestPasswordReset(email.text.trim());
      if (mounted) {
        setState(() => step = 2);
        startCooldown();
      }
    } catch (_) {
      if (mounted) {
        setState(() => step = 2);
        startCooldown();
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> verify() async {
    if (busy || code.text.length != 6) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      resetToken = await context
          .read<AppState>()
          .apiService
          .verifyPasswordResetCode(email.text.trim(), code.text);
      if (mounted) setState(() => step = 3);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => error = e.status == 410
            ? 'This reset code expired. Request a new code.'
            : 'That reset code is invalid or expired.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> reset() async {
    if (password.text.length < 10 || utf8.encode(password.text).length > 72) {
      setState(() => error = 'Use a password between 10 and 72 UTF-8 bytes.');
      return;
    }
    if (password.text != confirm.text) {
      setState(() => error = 'Passwords do not match.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await context
          .read<AppState>()
          .apiService
          .resetPassword(resetToken!, password.text);
      clearTemporary();
      if (mounted) setState(() => step = 4);
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void clearTemporary() {
    resetToken = null;
    code.clear();
    password.clear();
    confirm.clear();
    timer?.cancel();
    cooldown = 0;
  }

  @override
  Widget build(BuildContext context) => XaiAuthLayout(
      eyebrow: 'Account recovery',
      title: step == 4 ? 'Password reset' : 'Reset password',
      subtitle: step == 1
          ? 'Enter your account email.'
          : step == 2
              ? 'If the account is eligible, a 6-digit code was sent by email.'
              : step == 3
                  ? 'Choose a new password. Your authenticator enrollment remains unchanged.'
                  : 'Your password was reset. Sign in with the new password.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (step == 1) ...[
          XaiTextField(
              controller: email, label: 'Email', email: true, enabled: !busy),
          const SizedBox(height: 18),
          XaiButton(label: 'Send reset code', onPressed: busy ? null : send)
        ],
        if (step == 2) ...[
          XaiTextField(
              controller: code,
              label: 'Reset code',
              code: true,
              enabled: !busy),
          const SizedBox(height: 18),
          XaiButton(label: 'Verify code', onPressed: busy ? null : verify),
          TextButton(
              onPressed: busy || cooldown > 0 ? null : send,
              child:
                  Text(cooldown > 0 ? 'Resend in ${cooldown}s' : 'Resend code'))
        ],
        if (step == 3) ...[
          XaiTextField(
              controller: password,
              label: 'New password',
              password: true,
              enabled: !busy),
          const SizedBox(height: 12),
          XaiTextField(
              controller: confirm,
              label: 'Confirm new password',
              password: true,
              enabled: !busy),
          const SizedBox(height: 18),
          XaiButton(label: 'Reset password', onPressed: busy ? null : reset)
        ],
        if (step == 4) ...[
          const Icon(Icons.check_circle_outline,
              size: 54, color: XaiColors.success),
          const SizedBox(height: 16),
          XaiButton(
              label: 'Return to Login',
              onPressed: () => _resetTo(context, const LoginScreen()))
        ],
        if (step != 4)
          TextButton(
              onPressed: busy
                  ? null
                  : () {
                      clearTemporary();
                      _resetTo(context, const LoginScreen());
                    },
              child: const Text('Back to Login')),
        AuthError(error),
        if (busy) const LinearProgressIndicator(),
      ]));
  @override
  void dispose() {
    timer?.cancel();
    resetToken = null;
    for (final item in [email, code, password, confirm]) {
      item.dispose();
    }
    super.dispose();
  }
}
