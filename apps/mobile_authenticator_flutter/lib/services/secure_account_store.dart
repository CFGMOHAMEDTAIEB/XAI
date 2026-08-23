import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/authenticator_account.dart';

class SecureAccountStore {
  static const _accountsKey = 'xai_authenticator_accounts_v1';
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  Future<List<AuthenticatorAccount>> loadAccounts() async {
    final value = await _storage.read(key: _accountsKey);
    if (value == null || value.isEmpty) return [];
    final decoded = jsonDecode(value) as List<dynamic>;
    return decoded
        .map((item) => AuthenticatorAccount.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<void> saveAccounts(List<AuthenticatorAccount> accounts) {
    return _storage.write(
      key: _accountsKey,
      value: jsonEncode(accounts.map((account) => account.toJson()).toList()),
    );
  }

  Future<void> clear() => _storage.delete(key: _accountsKey);
}
