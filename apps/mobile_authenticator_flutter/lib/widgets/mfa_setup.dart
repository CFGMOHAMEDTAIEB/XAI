import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../services/api_service.dart';

class MfaSetup extends StatefulWidget {
  const MfaSetup({super.key});
  @override
  State<MfaSetup> createState() => _MfaSetupState();
}

class _MfaSetupState extends State<MfaSetup> {
  final email = TextEditingController();
  final password = TextEditingController();
  final loginTotp = TextEditingController();
  final emailCode = TextEditingController();
  final totp = TextEditingController();
  bool busy = false;
  bool registering = false;
  String? error;
  String? stage;
  String? enrollmentId;
  String? pendingUri;
  String accountEmail = '';

  AppState get app => context.read<AppState>();
  ApiService get api => app.apiService;

  Future<void> run(Future<void> Function() action) async {
    if (busy) return;
    setState(() { busy = true; error = null; });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) {
        error = e.message;
        if (e.status == 401) stage = null;
      }
    } catch (_) {
      if (mounted) error = 'Secure provisioning failed. Retry saving, or refresh status and restart setup.';
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void acceptStatus(Map<String, dynamic> data) {
    if (!mounted) return;
    final nextId = data['enrollment_id'] as String?;
    if (nextId != enrollmentId) pendingUri = null;
    stage = data['state'] as String;
    enrollmentId = nextId;
    accountEmail = data['email'] as String;
  }

  Future<void> refresh() async => acceptStatus(await api.mfaStatus());

  Future<void> signIn() async {
    final client = api;
    final enteredPassword = password.text;
    password.clear();
    if (registering) {
      await client.register(email: email.text.trim(), password: enteredPassword);
    } else {
      await client.login(email: email.text.trim(), password: enteredPassword,
          totpCode: loginTotp.text.trim().isEmpty ? null : loginTotp.text.trim());
    }
    loginTotp.clear();
    if (mounted) await refresh();
  }

  Future<void> saveProvisioning() async {
    await app.provision(pendingUri!, enrollmentId!);
    pendingUri = null;
    stage = 'awaiting_totp';
  }

  Future<void> verifyEmail() async {
    final data = await api.confirmEmail(enrollmentId!, emailCode.text.trim());
    if (!mounted) return;
    emailCode.clear();
    pendingUri = data['otpauth_uri'] as String;
    // Retain in memory on storage failure so Retry does not replay the email code.
    stage = 'saving';
    await saveProvisioning();
  }

  Widget field(TextEditingController controller, String label, {bool secret = false, bool numeric = false}) =>
      Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: TextField(
        controller: controller, obscureText: secret, enabled: !busy,
        autocorrect: false, enableSuggestions: false,
        keyboardType: numeric ? TextInputType.number : TextInputType.text,
        maxLength: numeric ? 6 : null,
        decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
      ));

  Widget button(String label, Future<void> Function() action) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: FilledButton(onPressed: busy ? null : () => run(action), child: Text(label)));

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final current = state.accounts.where((a) => a.id == 'xai-$enrollmentId').firstOrNull;
    final provisioned = current != null;
    return Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('XAI account & MFA', style: Theme.of(context).textTheme.titleLarge),
        if (stage == null) ...[
          const Text('Sign in or create your XAI account to set up this authenticator. Existing codes remain available below.'),
          field(email, 'Email'),
          field(password, 'Password (at least 10 characters)', secret: true),
          if (!registering) ...[
            const Text('MFA enabled: enter a current code. MFA disabled or setup pending: leave this blank.'),
            field(loginTotp, 'TOTP for MFA-enabled accounts', numeric: true),
          ],
          button(registering ? 'Create account' : 'Sign in', signIn),
          TextButton(onPressed: busy ? null : () => setState(() { registering = !registering; error = null; }),
            child: Text(registering ? 'Already registered? Sign in' : 'Create a new XAI account')),
          if (api.accessToken != null) button('Refresh status', refresh),
        ] else ...[
          Text(accountEmail),
          if (stage == 'not_configured') ...[
            const Text('MFA not configured. XAI will generate your secret; never invent one.'),
            button('Setup Authenticator', () async => acceptStatus(await api.enrollTotp())),
          ],
          if (stage == 'awaiting_email') ...[
            const Text('Enter email verification code. Codes expire after 10 minutes. Resend is available after 60 seconds.'),
            field(emailCode, 'Email verification code', numeric: true),
            button('Verify email & provision authenticator', verifyEmail),
            button('Resend email code', () async { acceptStatus(await api.resendCode()); emailCode.clear(); }),
          ],
          if (stage == 'saving') ...[
            const Text('Save the verified enrollment securely before enabling MFA.'),
            button('Retry secure storage', saveProvisioning),
          ],
          if (stage == 'awaiting_totp') ...[
            if (provisioned) ...[
              const Text('Authenticator provisioned securely. Enter this enrollment’s current six-digit code:'),
              Text(state.totpService.generate(current, now: state.now).code,
                style: Theme.of(context).textTheme.headlineMedium),
              field(totp, 'Generated TOTP code', numeric: true),
              button('Verify TOTP & enable MFA', () async {
                final enabled = await api.confirmTotp(enrollmentId!, totp.text.trim());
                if (!enabled) throw const ApiException('MFA was not enabled. Refresh status and retry.');
                totp.clear();
                stage = 'enabled';
              }),
            ] else const Text('This enrollment was already delivered, but its secret is not on this phone. Restart setup to securely provision a new enrollment.'),
          ],
          if (stage == 'expired') const Text('Enrollment expired. Restart setup and use the new email code.'),
          if (stage == 'enabled') const Text('MFA ENABLED. Future sign-ins require your current authenticator code.'),
          if (stage != 'enabled' && stage != 'not_configured')
            button('Restart setup with a new secret', () async {
              final data = await api.enrollTotp(restart: true);
              acceptStatus(data);
              emailCode.clear(); totp.clear();
            }),
          button('Refresh status', refresh),
          TextButton(onPressed: busy ? null : () => run(() async {
            final client = api;
            stage = null; pendingUri = null; enrollmentId = null; accountEmail = '';
            emailCode.clear(); totp.clear(); loginTotp.clear(); password.clear();
            await client.logout();
          }), child: const Text('Sign out')),
        ],
        if (busy) const Padding(padding: EdgeInsets.all(8), child: LinearProgressIndicator()),
        if (error != null) Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ],
    )));
  }

  @override
  void dispose() {
    for (final controller in [email, password, loginTotp, emailCode, totp]) { controller.dispose(); }
    pendingUri = null;
    super.dispose();
  }
}
