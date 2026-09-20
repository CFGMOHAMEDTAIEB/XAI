import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';
import '../models/authenticator_account.dart';
import '../theme/xai_colors.dart';
import '../theme/xai_spacing.dart';
import 'xai_button.dart';

class XaiOtpCircle extends StatelessWidget {
  const XaiOtpCircle({super.key, required this.account});
  final AuthenticatorAccount account;
  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final snapshot = state.totpService.generate(account, now: state.now);
    final grouped = snapshot.code.length == 6
        ? '${snapshot.code.substring(0, 3)} ${snapshot.code.substring(3)}'
        : snapshot.code;
    final progress = snapshot.remainingSeconds / account.period;
    return Semantics(
        label:
            'Current one-time password. ${snapshot.remainingSeconds} seconds remaining.',
        liveRegion: true,
        child: Column(children: [
          SizedBox(
              width: 250,
              height: 250,
              child: Stack(alignment: Alignment.center, children: [
                SizedBox.expand(
                    child: TweenAnimationBuilder<double>(
                        tween: Tween(end: progress),
                        duration: const Duration(milliseconds: 450),
                        builder: (_, value, __) => CircularProgressIndicator(
                            value: value,
                            strokeWidth: 11,
                            backgroundColor: Theme.of(context)
                                .colorScheme
                                .primary
                                .withValues(alpha: .12),
                            color: value < .2
                                ? XaiColors.warning
                                : Theme.of(context).colorScheme.primary,
                            strokeCap: StrokeCap.round))),
                Container(
                    width: 204,
                    height: 204,
                    decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Theme.of(context).colorScheme.surface,
                        boxShadow: const [
                          BoxShadow(
                              color: Color(0x1526345A),
                              blurRadius: 32,
                              offset: Offset(0, 14))
                        ]),
                    child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(grouped,
                              key: const ValueKey('totp-code'),
                              maxLines: 1,
                              style: Theme.of(context)
                                  .textTheme
                                  .headlineLarge
                                  ?.copyWith(
                                      fontSize: 38,
                                      letterSpacing: 4,
                                      fontWeight: FontWeight.w800)),
                          const SizedBox(height: XaiSpacing.sm),
                          Text('${snapshot.remainingSeconds} sec',
                              key: const ValueKey('totp-remaining'),
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                        ])),
              ])),
          const SizedBox(height: XaiSpacing.lg),
          SizedBox(
              width: 210,
              child: XaiButton(
                  label: 'Copy code',
                  icon: Icons.copy_rounded,
                  secondary: true,
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: snapshot.code));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Code copied')));
                    }
                  })),
        ]));
  }
}
