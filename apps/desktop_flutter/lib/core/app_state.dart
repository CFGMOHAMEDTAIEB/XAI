import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/app_models.dart';
import '../services/api_service.dart';
import '../services/deployment_config.dart';
import '../services/history_service.dart';
import '../services/local_engine_service.dart';
import '../services/secure_session_store.dart';
import '../services/settings_service.dart';

enum AuthStage { loading, login, mfa, verifyEmail, authenticated }

class AppState extends ChangeNotifier {
  AppState(
      {required this.engine,
      required this.api,
      required this.history,
      required this.settings,
      SessionStore? sessionStore})
      : sessionStore = sessionStore ?? SecureSessionStore();
  final LocalEngineService engine;
  final ApiService api;
  final HistoryService history;
  final SettingsService settings;
  final SessionStore sessionStore;
  AuthStage authStage = AuthStage.loading;
  bool loading = true, processing = false, darkMode = false;
  int page = 0;
  double progress = 0;
  String status = 'Ready';
  String? inputPath, outputPath, pendingEmail;
  String? _pendingMfaPassword;
  String mode = 'cloud';
  EngineResult? lastResult;
  List<HistoryItem> items = [];
  Map<String, dynamic>? account;
  late DesktopSettings config;
  bool get authenticated => authStage == AuthStage.authenticated;
  bool get mfaPending => authStage == AuthStage.mfa;
  bool get shellVisible => authenticated || mfaPending;
  bool get workspaceUnlocked => authenticated;
  Future<void> initialize() async {
    config = DesktopSettings();
    try {
      config = await settings.load().timeout(const Duration(seconds: 15));
      api.baseUrl = configuredApiUrl();
      darkMode = config.darkMode;
      final refresh = await sessionStore.readRefreshToken();
      if (refresh != null) {
        try {
          await api.restore(refresh);
          account = await api.me();
          await _persistSession();
          authStage = AuthStage.authenticated;
        } catch (_) {
          await sessionStore.clear();
          authStage = AuthStage.login;
        }
      } else {
        authStage = AuthStage.login;
      }
    } catch (_) {
      authStage = AuthStage.login;
      status = 'Local settings could not be restored.';
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> login(String email, String password, {String? totp}) async {
    _pendingMfaPassword = null;
    pendingEmail = email;
    try {
      account = await api.login(email, password, totp: totp);
      _pendingMfaPassword = null;
      await _persistSession();
      pendingEmail = null;
      authStage = AuthStage.authenticated;
      page = 0;
    } on ApiException catch (e) {
      if (e.kind == 'mfa_required') {
        _pendingMfaPassword = password;
        authStage = AuthStage.mfa;
        page = 0;
      } else if (e.kind == 'verification_required') {
        _pendingMfaPassword = null;
        authStage = AuthStage.verifyEmail;
      }
      rethrow;
    } finally {
      notifyListeners();
    }
  }

  Future<void> verifyMfa(String code) async {
    if (!RegExp(r'^\d{6}$').hasMatch(code)) {
      throw const ApiException('Enter exactly 6 numeric digits.',
          kind: 'invalid_input');
    }
    final email = pendingEmail;
    final password = _pendingMfaPassword;
    if (!mfaPending || email == null || password == null) {
      throw const ApiException('Sign in again to verify MFA.',
          kind: 'authentication');
    }
    try {
      account = await api.login(email, password, totp: code);
      await _persistSession();
      _pendingMfaPassword = null;
      pendingEmail = null;
      authStage = AuthStage.authenticated;
      page = 0;
    } on ApiException catch (error) {
      authStage = AuthStage.mfa;
      if (error.kind == 'mfa_required' || error.kind == 'authentication') {
        throw const ApiException('The code is invalid or expired.',
            kind: 'invalid_mfa');
      }
      rethrow;
    } finally {
      notifyListeners();
    }
  }

  Future<void> completeEmailVerification(String code) async {
    await api.confirmEmail(pendingEmail!, code);
    _pendingMfaPassword = null;
    authStage = AuthStage.login;
    notifyListeners();
  }

  void backToLogin() {
    authStage = AuthStage.login;
    pendingEmail = null;
    _pendingMfaPassword = null;
    notifyListeners();
  }

  void requireEmailVerification(String email) {
    _pendingMfaPassword = null;
    pendingEmail = email;
    authStage = AuthStage.verifyEmail;
    notifyListeners();
  }

  Future<void> logout() async {
    await api.logout();
    await sessionStore.clear();
    account = null;
    pendingEmail = null;
    _pendingMfaPassword = null;
    page = 0;
    authStage = AuthStage.login;
    notifyListeners();
  }

  Future<void> _persistSession() async {
    final refresh = api.refreshToken;
    if (refresh != null) await sessionStore.writeRefreshToken(refresh);
  }

  void setPage(int x) {
    if (!workspaceUnlocked || x < 0 || x > 6) return;
    page = x;
    notifyListeners();
  }

  void selectInput(String? x) {
    inputPath = x;
    notifyListeners();
  }

  void selectOutput(String? x) {
    outputPath = x;
    notifyListeners();
  }

  void setMode(String x) {
    mode = x;
    notifyListeners();
  }

  Future<void> compress() async {
    if (!authenticated || processing) return;
    if (mode == 'cloud') {
      await _cloud(false);
      return;
    }
    if (inputPath == null || outputPath == null) return;
    await _consume(
        engine.compress(
            python: config.python,
            workingDirectory: config.engineDirectory,
            input: inputPath!,
            output: outputPath!,
            mode: mode,
            checkpoint: config.checkpoint),
        'compress');
  }

  Future<void> decompress() async {
    if (!authenticated || processing) return;
    if (mode == 'cloud') {
      await _cloud(true);
      return;
    }
    if (inputPath == null || outputPath == null) return;
    await _consume(
        engine.decompress(
            python: config.python,
            workingDirectory: config.engineDirectory,
            input: inputPath!,
            output: outputPath!,
            checkpoint: config.checkpoint),
        'decompress');
  }

  Future<void> _cloud(bool restore) async {
    if (processing || inputPath == null || outputPath == null) return;
    processing = true;
    lastResult = null;
    status = 'Processing securely...';
    notifyListeners();
    try {
      final result = restore
          ? await api.decompress(inputPath!, outputPath!)
          : await api.compress(inputPath!, outputPath!);
      lastResult = EngineResult.fromJson(result);
      status = 'Completed';
      final item = HistoryItem(
          id: DateTime.now().microsecondsSinceEpoch.toString(),
          action: restore ? 'decompress' : 'compress',
          inputPath: inputPath!,
          outputPath: outputPath!,
          mode: 'cloud',
          createdAt: DateTime.now(),
          success: true,
          result: lastResult);
      items = [item, ...items];
      await history.save(items);
    } catch (e) {
      status = e is ApiException ? e.message : 'Operation failed safely.';
      lastResult = null;
    } finally {
      processing = false;
      notifyListeners();
    }
  }

  Future<void> _consume(Stream<ProcessUpdate> s, String action) async {
    processing = true;
    status = 'Starting...';
    progress = .15;
    lastResult = null;
    notifyListeners();
    String? error;
    try {
      await for (final u in s.timeout(const Duration(minutes: 10))) {
        status = u.message;
        progress = u.done ? 1 : (progress + .08).clamp(0.0, .9);
        lastResult = u.result;
        error = u.error ?? error;
        notifyListeners();
      }
      final item = HistoryItem(
          id: DateTime.now().microsecondsSinceEpoch.toString(),
          action: action,
          inputPath: inputPath!,
          outputPath: outputPath!,
          mode: mode,
          createdAt: DateTime.now(),
          success: error == null && lastResult != null,
          result: lastResult,
          error: error ??
              (lastResult == null ? 'No verified result returned' : null));
      items = [item, ...items];
      await history.save(items);
    } catch (_) {
      engine.cancel();
      status = 'Local operation failed or timed out.';
      lastResult = null;
    } finally {
      processing = false;
      notifyListeners();
    }
  }

  void cancel() {
    engine.cancel();
    processing = false;
    status = 'Cancelled';
    notifyListeners();
  }

  Future<void> clearHistory() async {
    items = [];
    await history.clear();
    notifyListeners();
  }

  Future<void> saveSettings() async {
    config.darkMode = darkMode;
    api.baseUrl = configuredApiUrl();
    await settings.save(config);
    notifyListeners();
  }

  void toggleDark(bool x) {
    darkMode = x;
    notifyListeners();
  }

  @override
  void dispose() {
    _pendingMfaPassword = null;
    api.dispose();
    engine.cancel();
    super.dispose();
  }
}
