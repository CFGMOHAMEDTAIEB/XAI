import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../theme/xai_spacing.dart';
import '../widgets/xai_card.dart';
import '../widgets/xai_otp_circle.dart';
import 'auth_screens.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(title: const Text('XAI Authenticator'), actions: [
        IconButton(
            onPressed: () async {
              await state.logout();
              if (context.mounted) _goLanding(context);
            },
            icon: const Icon(Icons.logout),
            tooltip: 'Logout'),
        IconButton(
            onPressed: state.lock,
            icon: const Icon(Icons.lock_outline),
            tooltip: 'Lock'),
      ]),
      body: SafeArea(
          child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 36),
              children: [
            if (state.accounts.isNotEmpty) ...[
              const SizedBox(height: XaiSpacing.md),
              Center(child: XaiOtpCircle(account: state.accounts.first)),
              const SizedBox(height: XaiSpacing.xl),
              XaiCard(
                  child: Row(children: [
                CircleAvatar(
                    backgroundColor: Theme.of(context)
                        .colorScheme
                        .primary
                        .withValues(alpha: .12),
                    child: const Icon(Icons.person_outline)),
                const SizedBox(width: 14),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text(
                          state.accounts.first.displayName?.isNotEmpty == true
                              ? state.accounts.first.displayName!
                              : 'XAI account',
                          style: Theme.of(context).textTheme.titleMedium),
                      Text(state.accounts.first.accountName,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodyMedium),
                    ])),
              ])),
              const SizedBox(height: 14),
              Text(
                  'Codes are generated securely on this device. No network request is made when the code changes.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium),
            ] else
              XaiCard(
                  child: Column(children: [
                const Icon(Icons.key_off_outlined, size: 44),
                const SizedBox(height: 12),
                const Text('No authenticator is stored on this device.'),
                const SizedBox(height: 16),
                FilledButton(
                    onPressed: () => Navigator.push(context,
                        MaterialPageRoute(builder: (_) => const LoginScreen())),
                    child: const Text('Login to enroll'))
              ])),
          ])),
    );
  }

  void _goLanding(BuildContext context) =>
      Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const LandingScreen()),
          (_) => false);
}
