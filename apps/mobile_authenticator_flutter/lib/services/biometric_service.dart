import 'package:local_auth/local_auth.dart';
import 'package:flutter/foundation.dart';

class BiometricService {
  BiometricService({LocalAuthentication? authentication})
      : _auth = authentication ?? LocalAuthentication();
  final LocalAuthentication _auth;

  Future<bool> authenticate() async {
    try {
      final supported = await _auth.isDeviceSupported();
      if (kDebugMode) debugPrint('[XAI startup] local_auth supported=$supported');
      if (!supported) return false;
      return await _auth.authenticate(
        localizedReason: 'Unlock XAI-Compress Authenticator',
        biometricOnly: false,
        persistAcrossBackgrounding: true,
      );
    } catch (_) {
      if (kDebugMode) debugPrint('[XAI startup] local_auth failed; retry device authentication');
      return false;
    }
  }
}
