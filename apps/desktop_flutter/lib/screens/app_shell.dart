import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../models/account_display.dart';
import '../theme/xai_theme.dart';
import 'compress_screen.dart';
import 'decompress_screen.dart';
import 'workspace_screens.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key});
  @override
  Widget build(BuildContext c) {
    final s = c.watch<AppState>();
    if (!s.shellVisible) return const SizedBox.shrink();
    final pages = [
      const DashboardScreen(),
      const FilesScreen(),
      const CompressScreen(),
      const DecompressScreen(),
      const BackendHistoryScreen(),
      const SharesScreen(),
      const SecurityScreen()
    ];
    final locked = !s.workspaceUnlocked;
    NavigationRailDestination destination(
            IconData icon, IconData selected, String label,
            {bool dashboard = false}) =>
        NavigationRailDestination(
            icon: Icon(locked && !dashboard ? Icons.lock_outline : icon),
            selectedIcon: Icon(locked && !dashboard ? Icons.lock : selected),
            label: Text(label));
    final destinations = [
      destination(Icons.dashboard_outlined, Icons.dashboard, 'Dashboard',
          dashboard: true),
      destination(Icons.folder_outlined, Icons.folder, 'Files'),
      destination(Icons.compress_outlined, Icons.compress, 'Compress'),
      destination(Icons.unarchive_outlined, Icons.unarchive, 'Decompress'),
      destination(Icons.history_outlined, Icons.history, 'History'),
      destination(Icons.share_outlined, Icons.share, 'Shares'),
      destination(Icons.security_outlined, Icons.security, 'Security'),
    ];
    return Scaffold(
        body: Column(children: [
      Container(
          height: 68,
          padding: const EdgeInsets.symmetric(horizontal: 22),
          decoration: BoxDecoration(
              color: Theme.of(c).colorScheme.surface,
              border: const Border(bottom: BorderSide(color: XaiColors.line))),
          child: Row(children: [
            Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                    gradient: const LinearGradient(
                        colors: [Color(0xff6073f3), XaiColors.accent]),
                    borderRadius: BorderRadius.circular(10)),
                alignment: Alignment.center,
                child: const Text('X',
                    style: TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold))),
            const SizedBox(width: 12),
            const Text('XAICD',
                style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
            const Spacer(),
            Text(accountDisplayName(s.account)),
            const SizedBox(width: 12),
            CircleAvatar(child: Text(accountInitials(s.account)))
          ])),
      Expanded(
          child: Row(children: [
        NavigationRail(
            extended: MediaQuery.sizeOf(c).width > 1080,
            selectedIndex: locked ? 0 : s.page,
            onDestinationSelected: s.setPage,
            destinations: destinations,
            trailing: Expanded(
                child: Align(
                    alignment: Alignment.bottomCenter,
                    child: Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: IconButton(
                            tooltip: 'Logout',
                            onPressed: s.logout,
                            icon: const Icon(Icons.logout)))))),
        const VerticalDivider(width: 1),
        Expanded(child: locked ? pages.first : pages[s.page])
      ]))
    ]));
  }
}
