import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../widgets/account_code_card.dart';
import '../widgets/mfa_setup.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(title: const Text('XAI Authenticator'), actions: [
        IconButton(onPressed: state.lock, icon: const Icon(Icons.lock_outline), tooltip: 'Lock'),
      ]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const ExpansionTile(title: Text('Privacy and data use — draft'), children: [Padding(padding: EdgeInsets.all(12), child: Text('TOTP secrets and account names are stored in device secure storage. Enrollment sends account credentials and verification codes to the configured backend; email verification uses its email provider. Removing a local account does not delete the server account or disable server MFA. Operator contact, retention and deletion procedures are not finalized.'))]),
        const MfaSetup(),
        const SizedBox(height: 16),
        if (state.accounts.isEmpty) const Text('No accounts enrolled'),
        for (final account in state.accounts)
          Padding(padding: const EdgeInsets.only(bottom: 12), child: AccountCodeCard(account: account)),
      ]),
    );
  }
}
