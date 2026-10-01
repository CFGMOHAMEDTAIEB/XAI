import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:window_manager/window_manager.dart';
import 'core/app_state.dart';
import 'screens/app_shell.dart';
import 'screens/auth_flow.dart';
import 'services/api_service.dart';
import 'services/history_service.dart';
import 'services/local_engine_service.dart';
import 'services/settings_service.dart';
import 'theme/xai_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  const options = WindowOptions(
      size: Size(1220, 780),
      minimumSize: Size(900, 620),
      center: true,
      title: 'XAICD');
  windowManager.waitUntilReadyToShow(options, () async {
    await windowManager.show();
    await windowManager.focus();
  });
  runApp(ChangeNotifierProvider(
      create: (_) => AppState(
          engine: LocalEngineService(),
          api: ApiService(),
          history: HistoryService(),
          settings: SettingsService())
        ..initialize(),
      child: const DesktopApp()));
}

class DesktopApp extends StatelessWidget {
  const DesktopApp({super.key});
  @override
  Widget build(BuildContext c) => Consumer<AppState>(
      builder: (c, s, _) => MaterialApp(
          debugShowCheckedModeBanner: false,
          title: 'XAICD',
          themeMode: s.darkMode ? ThemeMode.dark : ThemeMode.light,
          theme: XaiTheme.light,
          darkTheme: XaiTheme.dark,
          home: s.loading
              ? const Scaffold(body: Center(child: CircularProgressIndicator()))
              : s.shellVisible
                  ? const AppShell()
                  : const AuthFlow()));
}
