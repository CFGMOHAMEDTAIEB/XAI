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

  Future<void> initialize() async {
    accounts = await accountStore.loadAccounts();
    loading = false;
    notifyListeners();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      now = DateTime.now();
      notifyListeners();
    });
  }

  Future<void> unlock() async {
    unlocked = await biometricService.authenticate();
    notifyListeners();
  }

  void lock() {
    unlocked = false;
    notifyListeners();
  }

  Future<void> addFromUri(String uri) async {
    final enrollment = TotpEnrollment.parse(uri);
    final id = DateTime.now().microsecondsSinceEpoch.toString();
    accounts = [...accounts, enrollment.toAccount(id)];
    await accountStore.saveAccounts(accounts);
    notifyListeners();
  }

  Future<void> addManual({
    required String issuer,
    required String accountName,
    required String secret,
  }) async {
    final id = DateTime.now().microsecondsSinceEpoch.toString();
    accounts = [
      ...accounts,
      AuthenticatorAccount(
        id: id,
        issuer: issuer,
        accountName: accountName,
        secret: secret.replaceAll(' ', '').toUpperCase(),
      ),
    ];
    await accountStore.saveAccounts(accounts);
    notifyListeners();
  }

  Future<void> remove(String id) async {
    accounts = accounts.where((account) => account.id != id).toList();
    await accountStore.saveAccounts(accounts);
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
