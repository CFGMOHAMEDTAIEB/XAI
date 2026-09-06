import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_authenticator/main.dart';
import 'package:xai_compress_authenticator/core/app_state.dart';
import 'package:xai_compress_authenticator/services/api_service.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';
import 'package:xai_compress_authenticator/services/secure_account_store.dart';

void main() {
  testWidgets('Authenticator starts locked and does not expose account codes', (tester) async {
    final state = AppState(accountStore: SecureAccountStore(),
      biometricService: BiometricService(), apiService: ApiService())..loading = false;
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<AppState>.value(
      value: state, child: const XaiAuthenticatorApp()));
    expect(find.text('Unlock'), findsOneWidget);
    expect(find.text('XAI-Compress Authenticator'), findsOneWidget);
    expect(find.text('Add account'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
