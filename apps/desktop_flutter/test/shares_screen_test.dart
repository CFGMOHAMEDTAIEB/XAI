import 'dart:convert';
import 'dart:io';
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

class _RecordingShareApi extends ApiService {
  _RecordingShareApi(this.filename, this.expectedPath);
  final String filename;
  final String expectedPath;
  final calls = <String>[];

  @override
  Future<List<dynamic>> shares() async => [{
    'id': 3, 'file_name': filename,
    'recipient_email': 'recipient@example.com',
    'expires_at': '2026-10-02T18:30:00', 'status': 'active'
  }];

  @override
  Future<Map<String, dynamic>> importArtifact(String path) async {
    calls.add('import');
    expect(path, expectedPath);
    return {'id': 42, 'name': filename};
  }

  @override
  Future<Map<String, dynamic>> createShare(
      int fileId, String email, int minutes) async {
    calls.add('share');
    expect(fileId, 42);
    expect(email, 'recipient@example.com');
    expect(minutes, 1440);
    return {
      'share_code': 'XC-TEST-SHARE',
      'recipient_email': email,
      'expires_at': '2026-10-02T18:30:00',
      'email_delivery': 'not_configured'
    };
  }
}

void main() {
  testWidgets('Browse accepts a local XAIC artifact and sends its real file id',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final directory = Directory.systemTemp.createTempSync('xai-share-picker-');
    addTearDown(() => directory.deleteSync(recursive: true));
    const filename =
        'xai_compress-0.2.0-python-package-demo-very-long-name.xaic';
    final artifact = File('${directory.path}${Platform.pathSeparator}$filename');
    artifact.writeAsBytesSync([88, 65, 73, 67, 6, 1, 2, 3]);
    var pickerOpened = false;
    final api = _RecordingShareApi(filename, artifact.path);
    final state = AppState(engine: LocalEngineService(), api: api,
        history: HistoryService(), settings: SettingsService());
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(value: state,
        child: MaterialApp(home: Scaffold(body: SharesScreen(
            pickFile: () async { pickerOpened = true; return artifact.path; })))));
    await tester.pumpAndSettle();
    final send = find.widgetWithText(FilledButton, 'Send file');
    expect(tester.widget<FilledButton>(send).onPressed, isNull);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Browse'));
    await tester.pumpAndSettle();
    expect(pickerOpened, isTrue);
    expect(find.text(filename), findsWidgets);
    expect(tester.widget<FilledButton>(send).onPressed, isNull);
    for (final width in [1200.0, 800.0, 440.0]) {
      tester.view.physicalSize = Size(width, 1000);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull,
          reason: 'selected filename overflow at width $width');
    }
    tester.view.physicalSize = const Size(1400, 1000);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Recipient email'),
        'not-an-email');
    await tester.pump();
    expect(tester.widget<FilledButton>(send).onPressed, isNull);
    await tester.enterText(find.widgetWithText(TextField, 'Recipient email'),
        'recipient@example.com');
    await tester.pump();
    expect(tester.widget<FilledButton>(send).onPressed, isNotNull);
    await tester.tap(find.text('1 hour').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('1 day').last);
    await tester.pumpAndSettle();
    await tester.tap(send);
    await tester.pumpAndSettle();
    expect(api.calls, ['import', 'share']);
    expect(find.text('XC-TEST-SHARE'), findsOneWidget);
    expect(find.text('File: $filename'), findsOneWidget);
    expect(find.text('Recipient: recipient@example.com'), findsOneWidget);
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    for (final width in [1200.0, 800.0, 440.0]) {
      tester.view.physicalSize = Size(width, 1000);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'overflow at width $width');
      expect(find.text('Send file'), findsOneWidget);
    }
  });

  testWidgets('rejects other extensions and accepts xaic files without header checks',
      (tester) async {
    tester.view.physicalSize = const Size(900, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final directory = Directory.systemTemp.createTempSync('xai-share-invalid-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final invalid = File('${directory.path}${Platform.pathSeparator}fake.xaic');
    invalid.writeAsBytesSync([80, 75, 3, 4, 10]);
    final paths = ['${directory.path}${Platform.pathSeparator}wrong.txt',
      invalid.path];
    var index = 0;
    final api = ApiService(client: MockClient((request) async =>
        http.Response('[]', request.url.path == '/shares' ? 200 : 404)))
      ..token = 'access';
    final state = AppState(engine: LocalEngineService(), api: api,
        history: HistoryService(), settings: SettingsService());
    addTearDown(state.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(value: state,
        child: MaterialApp(home: Scaffold(body: SharesScreen(
            pickFile: () async => paths[index++])))));
    await tester.pumpAndSettle();
    for (var attempt = 0; attempt < 2; attempt++) {
      await tester.tap(find.widgetWithText(OutlinedButton, 'Browse'));
      await tester.pumpAndSettle();
      if (attempt == 0) {
        expect(find.text('Select a file with the .xaic extension.'), findsOneWidget);
      } else {
        expect(find.text('fake.xaic'), findsOneWidget);
        expect(find.textContaining('is not a supported XAIC archive'), findsNothing);
      }
      expect(tester.widget<FilledButton>(
          find.widgetWithText(FilledButton, 'Send file')).onPressed, isNull);
    }
  });

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
    for (final size in [const Size(1107, 630), const Size(440, 630)]) {
      tester.view.physicalSize = size;
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'receive overflow at $size');
      final download = find.widgetWithText(FilledButton, 'Download');
      await tester.ensureVisible(download);
      await tester.pumpAndSettle();
      expect(download, findsOneWidget);
    }
  });
}
