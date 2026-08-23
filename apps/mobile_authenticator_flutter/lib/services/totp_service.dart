import 'package:otp/otp.dart';

import '../models/authenticator_account.dart';

class TotpSnapshot {
  const TotpSnapshot({required this.code, required this.remainingSeconds});

  final String code;
  final int remainingSeconds;
}

class TotpService {
  TotpSnapshot generate(AuthenticatorAccount account, {DateTime? now}) {
    final timestamp = (now ?? DateTime.now()).millisecondsSinceEpoch;
    final algorithm = switch (account.algorithm.toUpperCase()) {
      'SHA256' => Algorithm.SHA256,
      'SHA512' => Algorithm.SHA512,
      _ => Algorithm.SHA1,
    };

    final code = OTP.generateTOTPCodeString(
      account.secret,
      timestamp,
      interval: account.period,
      length: account.digits,
      algorithm: algorithm,
      isGoogle: true,
    );

    final currentSeconds = timestamp ~/ 1000;
    final remaining = account.period - (currentSeconds % account.period);
    return TotpSnapshot(code: code, remainingSeconds: remaining);
  }
}
