import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/authenticator_account.dart';
import '../models/totp_enrollment.dart';
import '../services/api_service.dart';
import '../services/biometric_service.dart';
import '../services/secure_account_store.dart';
import '../services/totp_service.dart';

class AppState extends ChangeNotifier {
  AppState({
    required this.accountStore,
    required this.biometricService,
    required this.apiService,
  });

  final SecureAccountStore accountStore;
  final BiometricService biometricService;
  final ApiService apiService;
  final TotpService totpService = TotpService();

  bool loading = true;
  bool unlocked = false;
  List<AuthenticatorAccount> accounts = [];
  DateTime now = DateTime.now();
  Timer? _timer;
  String? startupError;
  bool unlocking = false;
  String? unlockError;

  Future<void> initialize() async {
    loading = true;
    startupError = null;
    try {
      accounts = await accountStore.loadAccounts().timeout(const Duration(seconds: 15));
      _timer ??= Timer.periodic(const Duration(seconds: 1), (_) {
        now = DateTime.now();
        notifyListeners();
      });
    } catch (_) {
      startupError = 'Secure storage could not be opened. Unlock your phone and retry.';
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> unlock() async {
    if (unlocking) return;
    unlocking = true;
    unlockError = null;
    notifyListeners();
    try {
      unlocked = await biometricService.authenticate().timeout(const Duration(seconds: 90));
      if (!unlocked) unlockError = 'Authentication was not completed. Tap Unlock to retry.';
    } catch (_) {
      unlockError = 'Authentication unavailable. Retry with your device credential.';
    } finally {
      unlocking = false;
      notifyListeners();
    }
  }

  void lock() {
    unlocked = false;
    unawaited(apiService.logout());
    notifyListeners();
  }

  Future<void> addFromUri(String uri) async {
    final enrollment = TotpEnrollment.parse(uri);
    if(accounts.any((a)=>a.issuer.toLowerCase()==enrollment.issuer.toLowerCase()&&a.accountName.toLowerCase()==enrollment.accountName.toLowerCase())){
      throw const FormatException('This account is already enrolled.');
    }
    final id = DateTime.now().microsecondsSinceEpoch.toString();
    final updated = [...accounts, enrollment.toAccount(id)];
    await accountStore.saveAccounts(updated).timeout(const Duration(seconds: 15));
    accounts = updated;
    notifyListeners();
  }

  Future<void> provision(String uri, String enrollmentId) async {
    final enrollment = TotpEnrollment.parse(uri);
    final account = enrollment.toAccount('xai-$enrollmentId');
    final updated = [...accounts.where((a) => a.id != account.id &&
        !(a.id.startsWith('xai-') && a.accountName == account.accountName)), account];
    await accountStore.saveAccounts(updated).timeout(const Duration(seconds: 15));
    accounts = updated;
    notifyListeners();
  }

  Future<void> remove(String id) async {
    final updated = accounts.where((account) => account.id != id).toList();
    await accountStore.saveAccounts(updated).timeout(const Duration(seconds: 15));
    accounts = updated;
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    apiService.dispose();
    super.dispose();
  }
}
