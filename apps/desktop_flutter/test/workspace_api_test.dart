import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_desktop/services/api_service.dart';

void main() {
  test('files and history use authenticated backend response', () async {
    final api = ApiService(client: MockClient((request) async {
      expect(request.url.path, '/history');
      expect(request.headers['authorization'], 'Bearer access');
      return http.Response(
          '[{"id":7,"name":"owned.bin","status":"completed"}]', 200);
    }));
    api.token = 'access';
    final rows = await api.history();
    expect(rows.single['name'], 'owned.bin');
  });

  test('file download writes only returned authenticated bytes', () async {
    final api = ApiService(client: MockClient((request) async {
      expect(request.url.path, '/files/7/download');
      expect(request.headers['authorization'], 'Bearer access');
      return http.Response.bytes([88, 65, 73, 67], 200);
    }));
    api.token = 'access';
    final directory =
        await Directory.systemTemp.createTemp('xai-desktop-test-');
    addTearDown(() => directory.delete(recursive: true));
    final output = '${directory.path}${Platform.pathSeparator}artifact.xaic';
    await api.downloadFile(7, output);
    expect(await File(output).readAsBytes(), [88, 65, 73, 67]);
  });

  test('share create/list/revoke use existing authenticated contracts',
      () async {
    final calls = <String>[];
    final api = ApiService(client: MockClient((request) async {
      calls.add(request.url.path);
      expect(request.headers['authorization'], 'Bearer access');
      if (request.url.path == '/shares' && request.method == 'POST') {
        final body = jsonDecode(request.body);
        expect(body['file_id'], 7);
        expect(body['expires_minutes'], 1440);
        return http.Response('{"share_code":"shown-once"}', 200);
      }
      if (request.url.path == '/shares') {
        return http.Response('[{"id":3,"status":"active"}]', 200);
      }
      return http.Response('{"status":"revoked"}', 200);
    }));
    api.token = 'access';
    expect(
        (await api.createShare(7, 'recipient@example.com', 1440))['share_code'],
        'shown-once');
    expect(await api.shares(), hasLength(1));
    await api.revokeShare(3);
    expect(calls, ['/shares', '/shares', '/shares/3/revoke']);
  });

  test('share redeem returns metadata and download writes exact XAIC bytes',
      () async {
    final api = ApiService(client: MockClient((request) async {
      expect(request.headers['authorization'], 'Bearer access');
      expect(jsonDecode(request.body)['code'], 'XC-SAFE-CODE');
      if (request.url.path == '/shares/redeem') {
        return http.Response(
            '{"file":{"name":"owned.bin.xaic","size":4},"sender":{"name":"Test Sender","email":"sender@example.com"},"expires_at":"2026-10-01T18:30:00","remaining_downloads":1,"max_downloads":1}',
            200);
      }
      expect(request.url.path, '/shares/download');
      return http.Response.bytes([88, 65, 73, 67], 200);
    }));
    api.token = 'access';
    final share = await api.redeem('XC-SAFE-CODE');
    expect(share['file']['name'], 'owned.bin.xaic');
    expect(share['remaining_downloads'], 1);
    final directory =
        await Directory.systemTemp.createTemp('xai-share-test-');
    addTearDown(() => directory.delete(recursive: true));
    final output = '${directory.path}${Platform.pathSeparator}owned.bin.xaic';
    await api.downloadShare('XC-SAFE-CODE', output);
    expect(await File(output).readAsBytes(), [88, 65, 73, 67]);
  });

  for (final state in <(int, String)>[
    (403, 'forbidden'),
    (404, 'not_found'),
    (409, 'conflict'),
    (410, 'gone')
  ]) {
    test('share redemption maps HTTP ${state.$1} to ${state.$2}', () async {
      final api = ApiService(client: MockClient((_) async =>
          http.Response('{"detail":"sensitive backend detail"}', state.$1)));
      api.token = 'access';
      await expectLater(
          api.redeem('XC-SAFE-CODE'),
          throwsA(isA<ApiException>()
              .having((error) => error.kind, 'kind', state.$2)
              .having((error) => error.message, 'message',
                  isNot(contains('sensitive')))));
    });
  }

  test('security device list and revoke expose no secret fields', () async {
    final api = ApiService(client: MockClient((request) async {
      if (request.method == 'GET') {
        return http.Response(
            '[{"device_id":"device-public-id","platform":"ios","status":"active"}]',
            200);
      }
      expect(request.url.path, '/auth/devices/device-public-id/revoke');
      return http.Response('{"status":"revoked"}', 200);
    }));
    api.token = 'access';
    final devices = await api.devices();
    expect(devices.single.keys, isNot(contains('private_key')));
    expect(devices.single.keys, isNot(contains('totp_secret')));
    await api.revokeDevice('device-public-id');
  });

  test('backend failures remain sanitized', () async {
    final api = ApiService(
        client: MockClient(
            (_) async => http.Response('private database response', 503)));
    expect(
        api.history(),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', isNot(contains('private')))));
  });
}
