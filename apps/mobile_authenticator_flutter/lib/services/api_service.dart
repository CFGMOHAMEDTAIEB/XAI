import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'deployment_config.dart';

class ApiException implements Exception {
  const ApiException(this.message, [this.status]);
  final String message;
  final int? status;
  @override
  String toString() => message;
}

class ApiService {
  ApiService({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ?? configuredApiUrl(), _client = client ?? http.Client();
  final http.Client _client;
  final String baseUrl;
  String? accessToken;
  String? _refreshToken;
  Future<void>? _refreshing;
  int _generation = 0;

  Future<void> logout() async {
    final refresh = _refreshToken;
    _generation++;
    accessToken = null;
    _refreshToken = null;
    if (refresh == null) return;
    try {
      await _request('/auth/logout', body: {'refresh_token': refresh});
    } on ApiException {
      // Local sign-out is complete even when server revocation is unavailable.
    }
  }

  Future<void> _refresh() => _refreshing ??= _rotate().whenComplete(() => _refreshing = null);
  Future<void> _rotate() async {
    final generation = _generation;
    try {
      final data = await _request('/auth/refresh', body: {'refresh_token': _refreshToken});
      if (generation != _generation) throw const ApiException('Session changed. Sign in again.', 401);
      accessToken = data['access_token'] as String;
      _refreshToken = data['refresh_token'] as String;
    } catch (_) {
      if (generation == _generation) { accessToken = null; _refreshToken = null; }
      throw const ApiException('Session expired. Sign in again.', 401);
    }
  }

  Future<Map<String, dynamic>> _request(String path, {Map<String, dynamic>? body, bool retry = true}) async {
    try {
      final headers = {'content-type': 'application/json',
        if (accessToken != null) 'authorization': 'Bearer $accessToken'};
      final uri = Uri.parse('$baseUrl$path');
      final response = await (body == null
          ? _client.get(uri, headers: headers)
          : _client.post(uri, headers: headers, body: jsonEncode(body)))
          .timeout(const Duration(seconds: 40));
      if (response.statusCode >= 400) {
        if (response.statusCode == 401 && retry && _refreshToken != null &&
            path != '/auth/login' && path != '/auth/register' && path != '/auth/refresh' && path != '/auth/logout') {
          await _refresh();
          return await _request(path, body: body, retry: false);
        }
        // Never display arbitrary response bodies, validation input or proxy errors.
        final message = switch (response.statusCode) {
          401 => 'Sign in again. Check your password and, if MFA is enabled, your current TOTP.',
          400 => 'Invalid or expired code. Check the code and device time, then retry.',
          409 => 'Account or enrollment state changed. Refresh status to continue or restart setup.',
          410 => 'Code or enrollment expired. Resend the email code or restart setup.',
          422 => 'Check your email, password (at least 10 characters), and six-digit code.',
          429 => 'Too many attempts. Wait before resending; after five emails, wait one hour.',
          _ => 'Backend or email service unavailable. Retry or refresh status shortly.',
        };
        if (response.statusCode == 401) accessToken = null;
        throw ApiException(message, response.statusCode);
      }
      return jsonDecode(response.body) as Map<String, dynamic>;
    } on ApiException { rethrow;
    } on TimeoutException {
      throw const ApiException('Request timed out. Refresh status before retrying setup.');
    } catch (_) {
      throw const ApiException('Cannot reach the backend. Check your connection and retry.');
    }
  }

  Future<void> login({required String email, required String password, String? totpCode}) async {
    final generation = _generation;
    final data = await _request('/auth/login', body: {
      'email': email, 'password': password, 'totp_code': totpCode});
    if (generation != _generation) throw const ApiException('Session changed. Sign in again.', 401);
    accessToken = data['access_token'] as String;
    _refreshToken = data['refresh_token'] as String?;
  }
  Future<void> register({required String email, required String password}) async {
    final generation = _generation;
    final data = await _request('/auth/register', body: {'email': email, 'password': password});
    if (generation != _generation) throw const ApiException('Session changed. Sign in again.', 401);
    accessToken = data['access_token'] as String;
    _refreshToken = data['refresh_token'] as String?;
  }
  Future<Map<String, dynamic>> mfaStatus() => _request('/auth/totp/status');
  Future<Map<String, dynamic>> enrollTotp({bool restart = false}) =>
      _request('/auth/totp/enroll', body: {'restart': restart});
  Future<Map<String, dynamic>> resendCode() => _request('/auth/totp/resend', body: {});
  Future<Map<String, dynamic>> confirmEmail(String enrollmentId, String code) =>
      _request('/auth/totp/email/confirm', body: {'enrollment_id': enrollmentId, 'code': code});
  Future<bool> confirmTotp(String enrollmentId, String code) async {
    final data = await _request('/auth/totp/confirm', body: {'enrollment_id': enrollmentId, 'code': code});
    return data['enabled'] == true;
  }
  void dispose() => _client.close();
}
