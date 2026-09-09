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
        const MfaSetup(),
        const SizedBox(height: 16),
        if (state.accounts.isEmpty) const Text('No accounts enrolled'),
        for (final account in state.accounts)
          Padding(padding: const EdgeInsets.only(bottom: 12), child: AccountCodeCard(account: account)),
      ]),
    );
  }
}
