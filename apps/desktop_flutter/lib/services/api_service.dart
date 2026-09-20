import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'deployment_config.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.kind});
  final String message;
  final String? kind;
  @override
  String toString() => message;
}

class ApiService {
  ApiService({http.Client? client, Duration? requestTimeout})
      : _client = client ?? http.Client(),
        requestTimeout = requestTimeout ?? const Duration(seconds: 40);
  final http.Client _client;
  final Duration requestTimeout;
  String baseUrl = configuredApiUrl();
  String? token, _refreshToken;
  Future<void>? _refreshing;
  int _generation = 0;
  String? get refreshToken => _refreshToken;

  Future<Map<String, dynamic>> login(String email, String password,
      {String? totp}) async {
    validateEmail(email);
    final generation = _generation;
    final r = await _post(
        '/auth/login',
        {
          'email': email,
          'password': password,
          'totp_code': totp?.isEmpty == true ? null : totp
        },
        auth: false,
        detectAuth: true);
    if (generation != _generation) {
      throw const ApiException('Session changed. Sign in again.');
    }
    final data = Map<String, dynamic>.from(jsonDecode(r.body));
    token = data['access_token'];
    _refreshToken = data['refresh_token'];
    return me();
  }

  Future<void> restore(String refresh) async {
    _refreshToken = refresh;
    await _rotate();
    await me();
  }

  Future<void> register(String name, String email, String password) {
    validateEmail(email);
    return _public('/auth/register',
        {'full_name': name, 'email': email, 'password': password});
  }

  Future<Map<String, dynamic>> me() async =>
      Map<String, dynamic>.from(jsonDecode((await _get('/auth/me')).body));
  Future<List<dynamic>> devices() async =>
      jsonDecode((await _get('/auth/devices')).body);
  Future<void> sendEmailVerification(String email) {
    validateEmail(email);
    return _public('/auth/verification/email/send', {'identifier': email});
  }

  Future<void> confirmEmail(String email, String code) {
    validateEmail(email);
    return _public('/auth/verification/email/confirm',
        {'identifier': email, 'code': code});
  }

  Future<void> forgotPassword(String email) {
    validateEmail(email);
    return _public('/auth/password/forgot', {'identifier': email});
  }

  Future<String> verifyResetCode(String email, String code) async {
    validateEmail(email);
    return jsonDecode((await _post(
            '/auth/password/verify-code', {'identifier': email, 'code': code},
            auth: false))
        .body)['reset_token'];
  }

  Future<void> resetPassword(String reset, String password) => _public(
      '/auth/password/reset', {'reset_token': reset, 'new_password': password});
  Future<void> _public(String path, Map<String, dynamic> body) async {
    await _post(path, body, auth: false);
  }

  Future<void> logout() async {
    final refresh = _refreshToken;
    _generation++;
    token = null;
    _refreshToken = null;
    if (refresh != null) {
      try {
        await _post('/auth/logout', {'refresh_token': refresh}, auth: false);
      } on ApiException {/* cleared locally */}
    }
  }

  Future<void> _refresh() =>
      _refreshing ??= _rotate().whenComplete(() => _refreshing = null);
  Future<void> _rotate() async {
    final g = _generation;
    try {
      if (_refreshToken == null) throw const ApiException('Sign in again.');
      final r = await _post('/auth/refresh', {'refresh_token': _refreshToken},
          auth: false);
      if (g != _generation) throw const ApiException('Session changed.');
      final d = jsonDecode(r.body);
      token = d['access_token'];
      _refreshToken = d['refresh_token'];
    } catch (_) {
      if (g == _generation) {
        token = null;
        _refreshToken = null;
      }
      throw const ApiException('Session expired. Sign in again.');
    }
  }

  Future<http.Response> _send(Future<http.Response> Function() call,
      {bool auth = true, bool detectAuth = false}) async {
    try {
      var r = await call().timeout(requestTimeout);
      if (r.statusCode == 401 && auth && _refreshToken != null) {
        await _refresh();
        r = await call();
      }
      if (r.statusCode >= 400) {
        throw _mapHttpError(r, authenticated: auth, detectAuth: detectAuth);
      }
      return r;
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException('Request timed out. Please retry.');
    } on SocketException {
      throw const ApiException('Could not connect securely. Please retry.');
    } on HandshakeException {
      throw const ApiException('Could not connect securely. Please retry.');
    } on http.ClientException {
      throw const ApiException('Could not connect securely. Please retry.');
    } catch (_) {
      throw const ApiException(
          'Service is temporarily unavailable. Please try again.');
    }
  }

  ApiException _mapHttpError(http.Response response,
      {required bool authenticated, required bool detectAuth}) {
    final detail = _safeDetail(response.body);
    if (detectAuth &&
        response.statusCode == 401 &&
        detail == 'Valid TOTP code required') {
      return const ApiException(
          'Enter the current code from XAI Authenticator.',
          kind: 'mfa_required');
    }
    if (detectAuth &&
        response.statusCode == 403 &&
        detail == 'Account verification required') {
      return const ApiException('Verify your email to continue.',
          kind: 'verification_required');
    }
    final status = response.statusCode;
    if (status == 400 || status == 422) {
      return const ApiException('Please check the information you entered.',
          kind: 'invalid_input');
    }
    if (status == 401) {
      return ApiException(
          authenticated
              ? 'Your session has expired. Please sign in again.'
              : 'Email, password, or authentication code is incorrect.',
          kind: 'authentication');
    }
    if (status == 403) {
      return const ApiException('This action is not allowed.',
          kind: 'forbidden');
    }
    if (status == 409) {
      return const ApiException(
          'This request conflicts with the current account or resource state.',
          kind: 'conflict');
    }
    if (status == 429) {
      return const ApiException('Too many attempts. Please try again later.',
          kind: 'rate_limited');
    }
    if (status >= 500) {
      return const ApiException(
          'Service is temporarily unavailable. Please try again.',
          kind: 'server');
    }
    return const ApiException('The requested operation could not be completed.',
        kind: 'http');
  }

  String? _safeDetail(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic> && decoded['detail'] is String) {
        return decoded['detail'] as String;
      }
    } catch (_) {
      // Provider bodies are never shown directly.
    }
    return null;
  }

  static void validateEmail(String value) {
    final email = value.trim();
    final valid = email.length <= 254 &&
        RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email);
    if (!valid) {
      throw const ApiException('Please check the information you entered.',
          kind: 'invalid_input');
    }
  }

  Map<String, String> get _headers => {
        'content-type': 'application/json',
        if (token != null) 'authorization': 'Bearer $token'
      };
  Future<http.Response> _post(String path, Map<String, dynamic> body,
      {bool auth = true, bool detectAuth = false}) {
    if (auth && token == null) {
      return Future.error(const ApiException(
          'Complete authentication before accessing the workspace.',
          kind: 'authentication_required'));
    }
    final uri = Uri.parse('$baseUrl$path');
    final diagnose = kDebugMode && path == '/auth/password/forgot';
    if (diagnose) {
      debugPrint('DESKTOP_API_SCHEME=${uri.scheme}');
      debugPrint('DESKTOP_API_HOST=${uri.host}');
      debugPrint('DESKTOP_API_ENDPOINT=$path');
    }
    return _send(() async {
      try {
        final response =
            await _client.post(uri, headers: _headers, body: jsonEncode(body));
        if (diagnose) debugPrint('HTTP_STATUS=${response.statusCode}');
        return response;
      } catch (error) {
        if (diagnose) debugPrint('EXCEPTION_TYPE=${error.runtimeType}');
        rethrow;
      }
    }, auth: auth, detectAuth: detectAuth);
  }

  Future<http.Response> _get(String path) {
    if (token == null) {
      return Future.error(const ApiException(
          'Complete authentication before accessing the workspace.',
          kind: 'authentication_required'));
    }
    return _send(
        () => _client.get(Uri.parse('$baseUrl$path'), headers: _headers));
  }

  Future<List<dynamic>> history() async =>
      jsonDecode((await _get('/history')).body);
  Future<List<dynamic>> shares() async =>
      jsonDecode((await _get('/shares')).body);
  Future<Map<String, dynamic>> createShare(
          int fileId, String email, int minutes) async =>
      Map<String, dynamic>.from(jsonDecode((await _post('/shares', {
        'file_id': fileId,
        'recipient_email': email,
        'expires_minutes': minutes,
        'max_downloads': 1,
        'anonymous_sender': false
      }))
          .body));
  Future<void> revokeShare(int id) async {
    await _post('/shares/$id/revoke', {});
  }

  Future<void> revokeDevice(String deviceId) async {
    await _post('/auth/devices/$deviceId/revoke', {});
  }

  Future<Map<String, dynamic>> redeem(String code) async =>
      Map<String, dynamic>.from(
          jsonDecode((await _post('/shares/redeem', {'code': code})).body));
  Future<http.Response> _upload(String path, String input) => _send(() async {
        if (token == null) {
          throw const ApiException(
              'Complete authentication before accessing the workspace.',
              kind: 'authentication_required');
        }
        final q = http.MultipartRequest('POST', Uri.parse('$baseUrl$path'));
        q.headers['authorization'] = 'Bearer $token';
        q.files.add(await http.MultipartFile.fromPath('upload', input));
        return http.Response.fromStream(await _client.send(q));
      });
  Future<void> downloadFile(int id, String output) async {
    if (token == null) {
      throw const ApiException(
          'Complete authentication before accessing the workspace.',
          kind: 'authentication_required');
    }
    final r = await _send(() => _client
        .get(Uri.parse('$baseUrl/files/$id/download'), headers: _headers));
    await File(output).writeAsBytes(r.bodyBytes);
  }

  Future<Map<String, dynamic>> compress(String input, String output) async {
    final r = await _upload('/compression/jobs', input);
    final j = Map<String, dynamic>.from(jsonDecode(r.body));
    await downloadFile(j['id'], output);
    return {
      'original_size': j['original_size'],
      'artifact_size': j['compressed_size'],
      'mode': j['codec'],
      'sha256': j['sha256']
    };
  }

  Future<Map<String, dynamic>> decompress(String input, String output) async {
    final r = await _upload('/compression/decompress', input);
    await File(output).writeAsBytes(r.bodyBytes);
    return {
      'restored_size': r.bodyBytes.length,
      'mode': 'cloud-decompress',
      'sha256': r.headers['x-content-sha256']
    };
  }

  Future<void> downloadShare(String code, String output) async {
    final r = await _post('/shares/download', {'code': code});
    await File(output).writeAsBytes(r.bodyBytes);
  }

  void dispose() => _client.close();
}
