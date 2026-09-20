import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_desktop/core/app_state.dart';
import 'package:xai_compress_desktop/models/account_display.dart';
import 'package:xai_compress_desktop/screens/app_shell.dart';
import 'package:xai_compress_desktop/services/api_service.dart';
import 'package:xai_compress_desktop/services/history_service.dart';
import 'package:xai_compress_desktop/services/local_engine_service.dart';
import 'package:xai_compress_desktop/services/settings_service.dart';

void main() {
  test('account initials cover empty, one-character, and normal names', () {
    expect(accountInitials(null), 'XU');
    expect(accountInitials({'display_name': ''}), 'XU');
    expect(accountInitials({'display_name': 'Q'}), 'Q');
    expect(accountInitials({'display_name': '  Ada   Lovelace  '}), 'AL');
    expect(accountInitials({'display_name': '', 'email': 'a@example.invalid'}),
        'A');
  });

  testWidgets('authenticated shell handles an empty account display name',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1220, 780));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final state = AppState(
      engine: LocalEngineService(),
      api: ApiService(client: MockClient((request) async {
        if (request.url.path == '/auth/me') {
          return http.Response('{}', 200);
        }
        return http.Response('[]', 200);
      })),
      history: HistoryService(),
      settings: SettingsService(),
    )
      ..authStage = AuthStage.authenticated
      ..account = {
        'email': '',
        'display_name': '',
        'email_verified': true,
        'mfa_enabled': true,
        'account_status': 'ACTIVE',
      }
      ..config = DesktopSettings();
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(
      value: state,
      child: const MaterialApp(home: AppShell()),
    ));
    expect(tester.takeException(), isNull);
  });
}
