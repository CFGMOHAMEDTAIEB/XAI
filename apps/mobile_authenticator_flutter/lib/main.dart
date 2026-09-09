import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/app_state.dart';
import 'screens/home_screen.dart';
import 'screens/lock_screen.dart';
import 'services/api_service.dart';
import 'services/biometric_service.dart';
import 'services/secure_account_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(
        accountStore: SecureAccountStore(),
        biometricService: BiometricService(),
        apiService: ApiService(),
      )..initialize(),
      child: const XaiAuthenticatorApp(),
    ),
  );
}

class XaiAuthenticatorApp extends StatelessWidget {
  const XaiAuthenticatorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'XAI-Compress Authenticator',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF4054D6)),
        useMaterial3: true,
        cardTheme: const CardThemeData(margin: EdgeInsets.zero),
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF8C9BFF),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: Consumer<AppState>(
        builder: (context, state, _) {
          if (state.loading) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          if (!state.unlocked) {
            if (state.startupError != null) {
              return Scaffold(body: Center(child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [Text(state.startupError!),
                  FilledButton(onPressed: state.initialize, child: const Text('Retry secure storage'))],
              )));
            }
            return const LockScreen();
          }
          return const HomeScreen();
        },
      ),
    );
  }
}
