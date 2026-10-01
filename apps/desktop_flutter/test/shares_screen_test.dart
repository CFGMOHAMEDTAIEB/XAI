import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_desktop/core/app_state.dart';
import 'package:xai_compress_desktop/screens/workspace_screens.dart';
import 'package:xai_compress_desktop/services/api_service.dart';
import 'package:xai_compress_desktop/services/history_service.dart';
import 'package:xai_compress_desktop/services/local_engine_service.dart';
import 'package:xai_compress_desktop/services/settings_service.dart';

void main() {
  testWidgets('Share screen redeems and displays recipient-authorized metadata',
      (tester) async {
    var redeemed = false;
    tester.view.physicalSize = const Size(1400, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = ApiService(client: MockClient((request) async {
      if (request.url.path == '/history' || request.url.path == '/shares') {
        if (request.method == 'GET') return http.Response('[]', 200);
      }
      if (request.url.path == '/shares/redeem') {
        redeemed = true;
        expect(jsonDecode(request.body)['code'], 'XC-SAFE-CODE');
        return http.Response(
            '{"file":{"name":"owned.bin.xaic","size":2048},"sender":{"name":"Test Sender","email":"sender@example.com"},"expires_at":"2026-10-01T18:30:00","remaining_downloads":1,"max_downloads":1}',
            200);
      }
      return http.Response('{}', 404);
    }))..token = 'access';
    final state = AppState(
        engine: LocalEngineService(),
        api: api,
        history: HistoryService(),
        settings: SettingsService());
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: SharesScreen()))));
    await tester.pumpAndSettle();
    expect(find.text('RECEIVE FILE'), findsOneWidget);
    await tester.enterText(
        find.widgetWithText(TextField, 'Share code'), 'XC-SAFE-CODE');
    await tester.pump();
    final receiveButton = find.widgetWithText(FilledButton, 'Receive file');
    expect(tester.widget<FilledButton>(receiveButton).onPressed, isNotNull);
    await tester.tap(receiveButton);
    await tester.pumpAndSettle();
    expect(redeemed, isTrue);
    expect(find.textContaining('owned.bin.xaic'), findsOneWidget);
    expect(find.textContaining('2.0 KiB'), findsOneWidget);
    expect(find.textContaining('Test Sender'), findsOneWidget);
    expect(find.textContaining('Downloads remaining: 1 / 1'), findsOneWidget);
  });
}
