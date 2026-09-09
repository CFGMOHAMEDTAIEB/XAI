import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';
import '../models/authenticator_account.dart';

class AccountCodeCard extends StatelessWidget {
  const AccountCodeCard({super.key, required this.account});

  final AuthenticatorAccount account;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final snapshot = state.totpService.generate(account, now: state.now);
    final groupedCode = snapshot.code.length == 6
        ? '${snapshot.code.substring(0, 3)} ${snapshot.code.substring(3)}'
        : snapshot.code;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(child: Text(account.issuer.isEmpty ? 'X' : account.issuer[0].toUpperCase())),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(account.issuer, style: Theme.of(context).textTheme.titleMedium),
                      Text(account.accountName, overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
                PopupMenuButton<String>(
                  onSelected: (value) async {
                    if (value != 'delete') return;
                    final state = context.read<AppState>();
                    final confirmed = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
                      title: const Text('Delete local authenticator?'),
                      content: const Text('This does not disable MFA on XAI. Without another copy you may lose access to your account.'),
                      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
                        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete'))],
                    ));
                    if (confirmed != true) return;
                    try { await state.remove(account.id); }
                    catch (_) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Secure storage could not be updated. Retry deletion.')));
                      }
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(value: 'delete', child: Text('Delete account')),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 22),
            InkWell(
              onTap: () async {
                await Clipboard.setData(ClipboardData(text: snapshot.code));
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Code copied')));
                }
              },
              child: Text(
                groupedCode,
                style: Theme.of(context).textTheme.displaySmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      letterSpacing: 5,
                    ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: LinearProgressIndicator(
                    value: snapshot.remainingSeconds / account.period,
                    minHeight: 8,
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                const SizedBox(width: 12),
                Text('${snapshot.remainingSeconds}s'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
