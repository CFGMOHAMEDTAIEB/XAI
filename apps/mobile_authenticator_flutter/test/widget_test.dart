import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_authenticator/core/app_state.dart';
import 'package:xai_compress_authenticator/main.dart';
import 'package:xai_compress_authenticator/models/authenticator_account.dart';
import 'package:xai_compress_authenticator/services/api_service.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';
import 'package:xai_compress_authenticator/services/secure_account_store.dart';

class TestBiometricService extends BiometricService {
  bool result = false;
  @override
  Future<bool> authenticate() async => result;
}

void main() {
  testWidgets('stored authenticator remains behind biometric unlock',
      (tester) async {
    final biometrics = TestBiometricService();
    final state = AppState(
        accountStore: SecureAccountStore(),
        biometricService: biometrics,
        apiService: ApiService())
      ..loading = false
      ..accounts = [
        const AuthenticatorAccount(
            id: '1',
            issuer: 'XAI',
            accountName: 'test@example.com',
            secret: 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ')
      ];
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state, child: const XaiAuthenticatorApp()));
    expect(find.text('Unlock'), findsOneWidget);
    expect(find.byKey(const ValueKey('totp-code')), findsNothing);
    biometrics.result = true;
    await tester.tap(find.text('Unlock'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('totp-code')), findsOneWidget);
    await tester.tap(find.byTooltip('Lock'));
    await tester.pumpAndSettle();
    expect(find.text('Unlock'), findsOneWidget);
  });

  testWidgets('fresh install opens auth landing without dashboard',
      (tester) async {
    final state = AppState(
        accountStore: SecureAccountStore(),
        biometricService: BiometricService(),
        apiService: ApiService())
      ..loading = false
      ..unlocked = true;
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state, child: const XaiAuthenticatorApp()));
    expect(find.text('Authentication, simplified'), findsOneWidget);
    expect(find.byKey(const ValueKey('totp-code')), findsNothing);
  });
}
