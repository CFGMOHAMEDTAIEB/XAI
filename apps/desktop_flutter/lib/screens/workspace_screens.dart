import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../core/app_state.dart';
import '../services/api_service.dart';
import '../theme/xai_theme.dart';

class WorkspacePage extends StatelessWidget {
  const WorkspacePage(this.title, this.child,
      {this.actions = const [], super.key});
  final String title;
  final Widget child;
  final List<Widget> actions;
  @override
  Widget build(BuildContext c) => Padding(
      padding: const EdgeInsets.all(30),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(title,
              style: Theme.of(c)
                  .textTheme
                  .headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w700)),
          const Spacer(),
          ...actions
        ]),
        const SizedBox(height: 24),
        Expanded(child: child)
      ]));
}

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});
  @override
  Widget build(BuildContext c) {
    final s = c.watch<AppState>();
    if (s.mfaPending) return const MfaDashboardGate();
    return WorkspacePage(
        'Dashboard',
        Wrap(spacing: 18, runSpacing: 18, children: [
          _card(Icons.lock_outline, 'Authenticated', 'Private workspace'),
          _card(Icons.verified_user_outlined, 'MFA',
              s.account?['mfa_enabled'] == true
                  ? 'Verified'
                  : 'Authenticator not enrolled'),
          _card(Icons.cloud_done_outlined, 'Processing', 'Scanner-backed')
        ]));
  }

  Widget _card(IconData i, String a, String b) => SizedBox(
      width: 260,
      height: 120,
      child: Card(
          child:
              ListTile(leading: Icon(i), title: Text(a), subtitle: Text(b))));
}

class MfaDashboardGate extends StatefulWidget {
  const MfaDashboardGate({super.key});
  @override
  State<MfaDashboardGate> createState() => _MfaDashboardGateState();
}

class _MfaDashboardGateState extends State<MfaDashboardGate> {
  final code = TextEditingController();
  final focus = FocusNode();
  bool busy = false;
  String? error;

  Future<void> verify() async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await context.read<AppState>().verifyMfa(code.text.trim());
    } on ApiException catch (exception) {
      code.clear();
      if (mounted) {
        setState(() => error = exception.message);
        focus.requestFocus();
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => WorkspacePage(
      'Dashboard locked',
      Center(
          child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Card(
                  child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.phonelink_lock_outlined,
                            size: 48, color: XaiColors.brand),
                        const SizedBox(height: 18),
                        Text('Mobile Authenticator verification',
                            style: Theme.of(context)
                                .textTheme
                                .titleLarge
                                ?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 10),
                        const Text(
                            'Enter the 6-digit code shown in XAI Authenticator on your phone.',
                            textAlign: TextAlign.center),
                        const SizedBox(height: 22),
                        TextField(
                            key: const Key('dashboard-mfa-code'),
                            controller: code,
                            focusNode: focus,
                            autofocus: true,
                            enabled: !busy,
                            keyboardType: TextInputType.number,
                            textAlign: TextAlign.center,
                            maxLength: 6,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                              LengthLimitingTextInputFormatter(6)
                            ],
                            onSubmitted: (_) => verify(),
                            style: const TextStyle(
                                fontSize: 28,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 8),
                            decoration: const InputDecoration(
                                labelText: 'Authenticator code',
                                counterText: '')),
                        if (error != null) ...[
                          const SizedBox(height: 10),
                          Text(error!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: XaiColors.danger))
                        ],
                        const SizedBox(height: 18),
                        SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                                onPressed: busy ? null : verify,
                                icon: busy
                                    ? const SizedBox.square(
                                        dimension: 18,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2))
                                    : const Icon(Icons.verified_user_outlined),
                                label: const Text('Verify code'))),
                        const SizedBox(height: 12),
                        const Text(
                            'Open XAI Authenticator on your phone. Codes refresh automatically.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: XaiColors.muted))
                      ]))))));

  @override
  void dispose() {
    code.dispose();
    focus.dispose();
    super.dispose();
  }
}

abstract class ReloadingState<T extends StatefulWidget> extends State<T> {
  bool loading = true;
  String? error;
  List<dynamic> rows = [];
  Future<List<dynamic>> loadRemote();
  Future<void> reload() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      rows = await loadRemote();
    } on ApiException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'Content could not be loaded.';
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Widget states(String empty) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null) {
      return Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(error!),
        const SizedBox(height: 12),
        OutlinedButton.icon(
            onPressed: reload,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'))
      ]));
    }
    if (rows.isEmpty) return Center(child: Text(empty));
    return const SizedBox.shrink();
  }
}

class FilesScreen extends StatefulWidget {
  const FilesScreen({super.key});
  @override
  State<FilesScreen> createState() => _FilesScreenState();
}

class _FilesScreenState extends ReloadingState<FilesScreen> {
  final downloaded = <int, String>{};
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      reload();
    });
  }

  @override
  Future<List<dynamic>> loadRemote() => context.read<AppState>().api.history();
  Future<void> download(Map<String, dynamic> row) async {
    final path = await FilePicker.platform.saveFile(
        dialogTitle: 'Save compressed artifact',
        fileName: '${row['name']}.xaic');
    if (path == null || !mounted) return;
    try {
      await context.read<AppState>().api.downloadFile(row['id'] as int, path);
      setState(() => downloaded[row['id'] as int] = path);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'Download complete. Use Open only if you trust the selected application.')));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> open(int id) async {
    final path = downloaded[id];
    if (path == null) return;
    final ok =
        await launchUrl(Uri.file(path), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No application is available to open this file.')));
    }
  }

  @override
  Widget build(BuildContext c) => WorkspacePage(
          'Files',
          loading || error != null || rows.isEmpty
              ? states('No files yet. Compress a file to get started.')
              : ListView.builder(
                  itemCount: rows.length,
                  itemBuilder: (c, i) {
                    final row = Map<String, dynamic>.from(rows[i]);
                    final id = row['id'] as int;
                    return Card(
                        child: ListTile(
                            leading:
                                const Icon(Icons.insert_drive_file_outlined),
                            title: Text('${row['name']}'),
                            subtitle: Text([
                              row['codec'],
                              row['status'],
                              _date(row['created_at'])
                            ]
                                .where(
                                    (x) => x != null && x.toString().isNotEmpty)
                                .join(' • ')),
                            trailing: Wrap(children: [
                              IconButton(
                                  tooltip: 'Download',
                                  onPressed: () => download(row),
                                  icon: const Icon(Icons.download_outlined)),
                              IconButton(
                                  tooltip: 'Open downloaded file',
                                  onPressed: downloaded.containsKey(id)
                                      ? () => open(id)
                                      : null,
                                  icon: const Icon(Icons.open_in_new))
                            ])));
                  }),
          actions: [
            IconButton(
                tooltip: 'Refresh files',
                onPressed: reload,
                icon: const Icon(Icons.refresh))
          ]);
}

class BackendHistoryScreen extends StatefulWidget {
  const BackendHistoryScreen({super.key});
  @override
  State<BackendHistoryScreen> createState() => _BackendHistoryScreenState();
}

class _BackendHistoryScreenState extends ReloadingState<BackendHistoryScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      reload();
    });
  }

  @override
  Future<List<dynamic>> loadRemote() => context.read<AppState>().api.history();
  @override
  Widget build(BuildContext c) => WorkspacePage(
          'History',
          loading || error != null || rows.isEmpty
              ? states('No server operations yet.')
              : ListView.builder(
                  itemCount: rows.length,
                  itemBuilder: (c, i) {
                    final row = Map<String, dynamic>.from(rows[i]);
                    return Card(
                        child: ListTile(
                            leading: Icon(
                                row['status'] == 'completed'
                                    ? Icons.check_circle_outline
                                    : Icons.pending_outlined,
                                color: row['status'] == 'completed'
                                    ? XaiColors.success
                                    : null),
                            title: Text('${row['name']}'),
                            subtitle: Text(
                                '${row['codec']} • ${_date(row['created_at']) ?? 'Date unavailable'}'),
                            trailing: Text('${row['status']}')));
                  }),
          actions: [
            IconButton(
                tooltip: 'Refresh history',
                onPressed: reload,
                icon: const Icon(Icons.refresh))
          ]);
}

class SharesScreen extends StatefulWidget {
  const SharesScreen({super.key});
  @override
  State<SharesScreen> createState() => _SharesScreenState();
}

class _SharesScreenState extends ReloadingState<SharesScreen> {
  List<dynamic> files = [];
  int? selected;
  int expiry = 60;
  final recipient = TextEditingController();
  bool creating = false;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      reload();
    });
  }

  @override
  Future<List<dynamic>> loadRemote() async {
    final api = context.read<AppState>().api;
    final result = await Future.wait([api.shares(), api.history()]);
    files = result[1];
    return result[0];
  }

  Future<void> create() async {
    if (selected == null || recipient.text.trim().isEmpty) return;
    setState(() => creating = true);
    try {
      final result = await context
          .read<AppState>()
          .api
          .createShare(selected!, recipient.text.trim(), expiry);
      if (mounted) {
        await showDialog<void>(
            context: context,
            barrierDismissible: false,
            builder: (d) => AlertDialog(
                    title: const Text('Share created'),
                    content: SelectableText(
                        'Share code: ${result['share_code']}\n\nThis code is shown once. Copy it now; XAI Desktop will not store it.'),
                    actions: [
                      FilledButton(
                          onPressed: () => Navigator.pop(d),
                          child: const Text('I saved the code'))
                    ]));
      }
      recipient.clear();
      selected = null;
      await reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => creating = false);
    }
  }

  Future<void> revoke(int id) async {
    final api = context.read<AppState>().api;
    final yes = await showDialog<bool>(
            context: context,
            builder: (d) => AlertDialog(
                    title: const Text('Revoke share?'),
                    content: const Text(
                        'Recipients will no longer be able to use this share.'),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(d, false),
                          child: const Text('Cancel')),
                      FilledButton(
                          onPressed: () => Navigator.pop(d, true),
                          child: const Text('Revoke'))
                    ])) ??
        false;
    if (!yes) return;
    try {
      await api.revokeShare(id);
      await reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Widget shareTile(dynamic raw) {
    final row = Map<String, dynamic>.from(raw);
    return Card(
        child: ListTile(
            leading: const Icon(Icons.share_outlined),
            title: Text('${row['file_name']}'),
            subtitle: Text(
                '${row['recipient_email']} • expires ${_date(row['expires_at']) ?? 'unknown'}'),
            trailing:
                Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
              Chip(label: Text('${row['status']}')),
              if (row['status'] == 'active')
                IconButton(
                    tooltip: 'Revoke share',
                    onPressed: () => revoke(row['id'] as int),
                    icon: const Icon(Icons.link_off))
            ])));
  }

  @override
  Widget build(BuildContext c) => WorkspacePage(
          'Shares',
          Column(children: [
            Card(
                child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          SizedBox(
                              width: 240,
                              child: DropdownButtonFormField<int>(
                                  initialValue: selected,
                                  decoration: const InputDecoration(
                                      labelText: 'Owned file'),
                                  items: [
                                    for (final f in files)
                                      DropdownMenuItem(
                                          value: f['id'] as int,
                                          child: Text('${f['name']}'))
                                  ],
                                  onChanged: (v) =>
                                      setState(() => selected = v))),
                          SizedBox(
                              width: 260,
                              child: TextField(
                                  controller: recipient,
                                  decoration: const InputDecoration(
                                      labelText: 'Recipient email'))),
                          SizedBox(
                              width: 150,
                              child: DropdownButtonFormField<int>(
                                  initialValue: expiry,
                                  decoration: const InputDecoration(
                                      labelText: 'Expires'),
                                  items: const [
                                    DropdownMenuItem(
                                        value: 15, child: Text('15 minutes')),
                                    DropdownMenuItem(
                                        value: 60, child: Text('1 hour')),
                                    DropdownMenuItem(
                                        value: 1440, child: Text('1 day')),
                                    DropdownMenuItem(
                                        value: 10080, child: Text('7 days'))
                                  ],
                                  onChanged: (v) =>
                                      setState(() => expiry = v ?? 60))),
                          FilledButton.icon(
                              onPressed: creating ? null : create,
                              icon: const Icon(Icons.add_link),
                              label: const Text('Create'))
                        ]))),
            const SizedBox(height: 16),
            Expanded(
                child: loading || error != null || rows.isEmpty
                    ? states('No shares created.')
                    : ListView.builder(
                        itemCount: rows.length,
                        itemBuilder: (c, i) => shareTile(rows[i])))
          ]),
          actions: [
            IconButton(
                tooltip: 'Refresh shares',
                onPressed: reload,
                icon: const Icon(Icons.refresh))
          ]);
  @override
  void dispose() {
    recipient.dispose();
    super.dispose();
  }
}

class SecurityScreen extends StatefulWidget {
  const SecurityScreen({super.key});
  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends ReloadingState<SecurityScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      reload();
    });
  }

  @override
  Future<List<dynamic>> loadRemote() => context.read<AppState>().api.devices();
  Future<void> revoke(String id) async {
    final api = context.read<AppState>().api;
    final yes = await showDialog<bool>(
            context: context,
            builder: (d) => AlertDialog(
                    title: const Text('Revoke device?'),
                    content: const Text(
                        'This authenticator device will no longer be authorized.'),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(d, false),
                          child: const Text('Cancel')),
                      FilledButton(
                          onPressed: () => Navigator.pop(d, true),
                          child: const Text('Revoke'))
                    ])) ??
        false;
    if (!yes) return;
    try {
      await api.revokeDevice(id);
      await reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext c) {
    final s = c.watch<AppState>();
    return WorkspacePage(
        'Account & Security',
        ListView(children: [
          Card(
              child: Column(children: [
            ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text('${s.account?['email'] ?? ''}'),
                subtitle: Text(
                    'Account ${s.account?['account_status'] ?? 'unknown'}')),
            ListTile(
                leading: const Icon(Icons.email_outlined),
                title: const Text('Email verification'),
                trailing: Text(s.account?['email_verified'] == true
                    ? 'Verified'
                    : 'Not verified')),
            ListTile(
                leading: const Icon(Icons.phonelink_lock_outlined),
                title: const Text('Authenticator MFA'),
                trailing: Text(s.account?['mfa_enabled'] == true
                    ? 'Enabled'
                    : 'Not enabled'))
          ])),
          const SizedBox(height: 18),
          Row(children: [
            Text('Registered devices',
                style: Theme.of(c).textTheme.titleMedium),
            const Spacer(),
            IconButton(
                tooltip: 'Refresh devices',
                onPressed: reload,
                icon: const Icon(Icons.refresh))
          ]),
          SizedBox(
              height: 260,
              child: loading || error != null || rows.isEmpty
                  ? states('No registered authenticator devices.')
                  : ListView(children: [
                      for (final raw in rows)
                        Builder(builder: (c) {
                          final d = Map<String, dynamic>.from(raw);
                          return Card(
                              child: ListTile(
                                  leading: const Icon(Icons.devices_other),
                                  title: Text(
                                      '${d['platform']} • ${d['app_version']}'),
                                  subtitle: Text(
                                      '${d['status']} • registered ${_date(d['registered_at']) ?? 'date unavailable'}'),
                                  trailing: d['status'] == 'active'
                                      ? IconButton(
                                          tooltip: 'Revoke device',
                                          onPressed: () =>
                                              revoke('${d['device_id']}'),
                                          icon:
                                              const Icon(Icons.phonelink_erase))
                                      : null));
                        })
                    ])),
          const SizedBox(height: 18),
          OutlinedButton.icon(
              onPressed: s.logout,
              icon: const Icon(Icons.logout),
              label: const Text('Logout'))
        ]));
  }
}

String? _date(dynamic value) {
  if (value == null) return null;
  final parsed = DateTime.tryParse('$value');
  return parsed == null
      ? '$value'
      : DateFormat.yMMMd().add_jm().format(parsed.toLocal());
}
